"""Reranking com cross-encoder multilíngue, medido pela régua por documento.

Pergunta: o índice uniforme entrega o documento gold no top-100 em 77,5% dos casos,
mas no top-10 só em 59,2%. Um cross-encoder multilíngue (bge-reranker-v2-m3), que
relê pergunta + candidato, recupera parte desses 18 p.p.?

Roda em CPU de propósito: a GPU desta máquina não tem kernel compatível com o build
do torch (`CUDA error: no kernel image is available`).

Uso:
    ~/venvs/reranker/bin/python eval/rerank_bge.py \
        --db ~/local-data/mcp/lab/snapshot-pos-dedup-20261018.db \
        --cases eval/recall_cases_v3.json --out eval/lab_rerank_bge.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "benchmarks"))


def recall_at(pos, k):
    return round(sum(1 for p in pos if p and p <= k) / len(pos), 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--cases", default="eval/recall_cases_v3.json")
    ap.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2")
    ap.add_argument("--ranker", default="BAAI/bge-reranker-v2-m3")
    ap.add_argument("--model-embedding", default=None,
                    help="modelo do cross-encoder; use --ranker para o nome")
    ap.add_argument("--kmax", type=int, default=100)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from recall_harness import load_cases, make_runner
    from sentence_transformers import CrossEncoder

    cases = load_cases(args.cases)
    runner = make_runner(args.db, embedding_model=args.model)
    ranker = CrossEncoder(args.ranker, max_length=512, device="cpu")

    pos_before, pos_after, gaps = [], [], 0
    lat = []
    t0 = time.time()
    for i, case in enumerate(cases, 1):
        res = runner(case["pergunta"], "semantic", args.kmax)
        gold = set(case.get("gold_hashes") or [])
        pos_before.append(
            next((j + 1 for j, r in enumerate(res) if r.get("content_hash") in gold), None)
        )
        pairs = [(case["pergunta"], (r.get("content") or "")[:1500]) for r in res]
        ts = time.time()
        scores = ranker.predict(pairs, batch_size=32, show_progress_bar=False)
        lat.append((time.time() - ts) * 1000)
        order = sorted(range(len(scores)), key=lambda j: -float(scores[j]))
        pos_after.append(
            next((j + 1 for j, idx in enumerate(order) if res[idx].get("content_hash") in gold), None)
        )
        if i % 20 == 0:
            print(f"  {i}/{len(cases)} · {time.time()-t0:.0f}s", flush=True)

    report = {
        "meta": {"db": args.db, "cases": args.cases, "embedding": args.model,
                 "reranker": args.ranker, "device": "cpu", "kmax": args.kmax},
        "antes": {f"documento@{k}": recall_at(pos_before, k) for k in (10, 30, 100)},
        "depois": {f"documento@{k}": recall_at(pos_after, k) for k in (10, 30, 100)},
        "mudancas": {
            "subiu_para_top10": sum(
                1 for a, b in zip(pos_before, pos_after)
                if (a is None or a > 10) and b and b <= 10
            ),
            "saiu_do_top10": sum(
                1 for a, b in zip(pos_before, pos_after)
                if a and a <= 10 and (b is None or b > 10)
            ),
        },
        "custo": {
            "segundos_totais": round(time.time() - t0, 1),
            "ms_por_consulta_p50": round(statistics.median(lat)),
        },
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        open(args.out, "w").write(payload + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
