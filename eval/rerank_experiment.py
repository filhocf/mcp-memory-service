"""Reranking e sinal de ausência medidos sobre o índice migrado.

Duas perguntas do cliente, uma passagem de dados:

F4 (reranking) — o índice uniforme põe o documento gold no top-100 em 77,5% dos
casos, mas no top-10 só em 59,2%. Ordenar os candidatos com o cross-encoder do
próprio produto (`quality/onnx_ranker.py`, ms-marco-MiniLM-L-6-v2) recupera parte
disso? Medido por documento, antes/depois.

F5 (ausência) — quando a resposta não existe, existe score que denuncie? Mede a
separação entre acertos e erros no score de similaridade do top-1 e varre limiares
para a decisão "não tenho isso".

Uso:
    PYTHONPATH=src ~/git/mcp-memory-service/.venv/bin/python eval/rerank_experiment.py \
        --db <migrado> --cases eval/recall_cases_v2.json \
        --model paraphrase-multilingual-MiniLM-L12-v2 --out eval/lab_rerank_abstain.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "benchmarks"))

from recall_harness import load_cases, make_runner  # noqa: E402


def recall_at(positions, k):
    return round(sum(1 for p in positions if p and p <= k) / len(positions), 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--cases", default="eval/recall_cases_v2.json")
    ap.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2")
    ap.add_argument("--kmax", type=int, default=100)
    ap.add_argument("--ranker", default="ms-marco-MiniLM-L-6-v2")
    ap.add_argument("--skip-rerank", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cases = load_cases(args.cases)
    runner = make_runner(args.db, embedding_model=args.model)

    rows = []
    for case in cases:
        res = runner(case["pergunta"], "semantic", args.kmax)
        gold = set(case.get("gold_hashes") or [])
        pos = next((i + 1 for i, r in enumerate(res) if r.get("content_hash") in gold), None)
        sims = []
        for r in res:
            try:
                sims.append(float(r.get("similarity_score") or 0.0))
            except (TypeError, ValueError):
                sims.append(0.0)
        rows.append(
            {
                "id": case["id"],
                "pergunta": case["pergunta"],
                "gold": list(gold),
                "pos": pos,
                "top1_sim": sims[0] if sims else None,
                "topk_sim": max(sims) if sims else None,
                "contents": [r.get("content") or "" for r in res],
                "hashes": [r.get("content_hash") for r in res],
            }
        )

    out = {
        "meta": {"db": args.db, "cases": args.cases, "model": args.model,
                 "kmax": args.kmax, "ranker": args.ranker},
        "antes": {f"documento@{k}": recall_at([r["pos"] for r in rows], k)
                  for k in (10, 30, 100)},
    }

    # ---- F5: sinal de ausência
    hits = [r["top1_sim"] for r in rows if r["pos"] and r["pos"] <= 10]
    misses = [r["top1_sim"] for r in rows if not (r["pos"] and r["pos"] <= 10)]
    hits = [h for h in hits if h is not None]
    misses = [m for m in misses if m is not None]
    sweep = []
    for t in [i / 20 for i in range(1, 20)]:
        tp = sum(1 for m in misses if m < t)          # erro detectado
        fp = sum(1 for h in hits if h < t)            # acerto descartado
        sweep.append(
            {
                "limiar": round(t, 2),
                "erros_detectados": f"{tp}/{len(misses)}",
                "acertos_perdidos": f"{fp}/{len(hits)}",
                "precisao_da_abstencao": round(tp / (tp + fp), 3) if (tp + fp) else None,
                "cobertura_dos_erros": round(tp / len(misses), 3),
            }
        )
    out["ausencia"] = {
        "top1_sim_acertos": {
            "n": len(hits),
            "media": round(statistics.mean(hits), 4) if hits else None,
            "p10": round(sorted(hits)[max(int(len(hits) * 0.1) - 1, 0)], 4) if hits else None,
        },
        "top1_sim_erros": {
            "n": len(misses),
            "media": round(statistics.mean(misses), 4) if misses else None,
            "p90": round(sorted(misses)[min(int(len(misses) * 0.9), len(misses) - 1)], 4) if misses else None,
        },
        "varredura": sweep,
    }

    # ---- F4: reranking
    if not args.skip_rerank:
        from mcp_memory_service.quality.onnx_ranker import ONNXRankerModel

        ranker = ONNXRankerModel(model_name=args.ranker)
        pos_after = []
        for r in rows:
            pairs = [(r["pergunta"], c[:1200]) for c in r["contents"]]
            try:
                scores = ranker.score_quality_batch(pairs)
            except TypeError:
                scores = [ranker.score_quality(q, c) for q, c in pairs]
            if hasattr(scores, "tolist"):
                scores = scores.tolist()
            order = sorted(range(len(scores)), key=lambda i: -float(scores[i]))
            pos_after.append(
                next((i + 1 for i, idx in enumerate(order) if r["hashes"][idx] in set(r["gold"])), None)
            )
        out["depois_rerank"] = {f"documento@{k}": recall_at(pos_after, k) for k in (10, 30, 100)}
        out["mudancas"] = {
            "subiu_para_top10": sum(
                1 for a, b in zip([r["pos"] for r in rows], pos_after)
                if (a is None or a > 10) and b and b <= 10
            ),
            "saiu_do_top10": sum(
                1 for a, b in zip([r["pos"] for r in rows], pos_after)
                if a and a <= 10 and (b is None or b > 10)
            ),
        }

    payload = json.dumps({k: v for k, v in out.items()}, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "ausencia"}, ensure_ascii=False, indent=1))
    print(json.dumps(out["ausencia"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
