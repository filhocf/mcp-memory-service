"""Sonda de valor para o cliente: quanto do top-10 é slot útil.

Mede, sobre o mesmo snapshot e gabarito do harness, três coisas que o consumidor
sente e que recall@k não mostra:

1. slots redundantes: resultados quase-idênticos ocupando o top-10 (o 6º resultado
   repetir o 2º não é informação nova);
2. custo do ruído: quantos casos teriam o gold dentro do top-10 se os redundantes
   fossem colapsados antes do corte;
3. latência por consulta (p50/p95), que é o que decide se dá para usar no turno.

Uso:
    PYTHONPATH=src ~/git/mcp-memory-service/.venv/bin/python \
        eval/client_value_probe.py --db <snapshot> --cases eval/recall_cases_v2.json \
        --embedding-model all-MiniLM-L6-v2 --out eval/lab_client_probe.json
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

from recall_harness import load_cases, make_runner  # noqa: E402

import numpy as np  # noqa: E402


def _embed(texts, model):
    vecs = model.encode(texts)
    arr = np.asarray(vecs, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def collapse(items, threshold):
    """Colapsa quase-duplicados preservando a ordem original."""
    kept = []
    kept_vecs = []
    for item, vec in items:
        if not kept_vecs:
            kept.append(item)
            kept_vecs.append(vec)
            continue
        sims = np.asarray(kept_vecs) @ vec
        if float(sims.max()) < threshold:
            kept.append(item)
            kept_vecs.append(vec)
    return kept


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--cases", default="eval/recall_cases_v2.json")
    ap.add_argument("--embedding-model", default=None)
    ap.add_argument("--mode", default="semantic")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--wide", type=int, default=40, help="janela larga para medir resgate")
    ap.add_argument("--threshold", type=float, default=0.95)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from mcp_memory_service.embeddings.onnx_embeddings import get_onnx_embedding_model

    model_name = args.embedding_model or "all-MiniLM-L6-v2"
    model = get_onnx_embedding_model(model_name)
    runner = make_runner(args.db, embedding_model=args.embedding_model)
    cases = load_cases(args.cases)

    latencies = []
    redundant = []
    rescued = 0
    gold_in_wide = 0
    positions_wide = {}
    per_case = []

    for case in cases:
        gold = set(case["gold_hashes"])
        t0 = time.perf_counter()
        res = runner(case["pergunta"], args.mode, args.wide)
        latencies.append((time.perf_counter() - t0) * 1000)

        contents = [r.get("content") or "" for r in res]
        hashes = [r.get("content_hash") for r in res]
        if not contents:
            continue
        vecs = _embed(contents, model)
        pairs = [(r, v) for r, v in zip(res, vecs)]

        top = pairs[: args.limit]
        kept = collapse(top, args.threshold)
        redundant.append(len(top) - len(kept))

        pos_wide = next((i + 1 for i, h in enumerate(hashes) if h in gold), None)
        positions_wide[case["id"]] = pos_wide
        if pos_wide:
            gold_in_wide += 1

        # resgate: se o gold estiver na janela larga e, ao colapsar os
        # redundantes, entrar no top-k -> ganho atribuível à deduplicação
        kept_wide = collapse(pairs, args.threshold)
        pos_kept = next(
            (i + 1 for i, r in enumerate(kept_wide) if r.get("content_hash") in gold), None
        )
        if pos_kept and pos_kept <= args.limit and not (pos_wide and pos_wide <= args.limit):
            rescued += 1

        per_case.append(
            {
                "id": case["id"],
                "categoria": case.get("categoria"),
                "idioma": case.get("idioma"),
                "slots_redundantes": redundant[-1],
                "pos_gold_janela": pos_wide,
                "pos_gold_pos_dedupe": pos_kept,
            }
        )

    lat_sorted = sorted(latencies)
    report = {
        "meta": {
            "db": args.db,
            "cases": args.cases,
            "mode": args.mode,
            "limit": args.limit,
            "wide": args.wide,
            "threshold": args.threshold,
            "embedding_model": model_name,
        },
        "slots": {
            "media_uteis": round(args.limit - statistics.mean(redundant), 2),
            "redundantes_media": round(statistics.mean(redundant), 2),
            "casos_com_redundancia": sum(1 for r in redundant if r),
            "distribuicao_redundantes": {
                str(k): redundant.count(k) for k in sorted(set(redundant))
            },
        },
        "resgate_por_dedupe_no_top_k": rescued,
        "gold_na_janela_larga": f"{gold_in_wide}/{len(cases)}",
        "latencia_ms": {
            "p50": round(statistics.median(lat_sorted), 1),
            "p95": round(lat_sorted[int(len(lat_sorted) * 0.95) - 1], 1),
            "max": round(lat_sorted[-1], 1),
        },
        "casos": per_case,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
