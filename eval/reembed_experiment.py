"""Re-embedding de bancada: qual modelo serve ao acervo, medido por documento.

O índice vivo foi construído com all-MiniLM-L6-v2 enquanto o serviço consulta com
paraphrase-multilingual. As duas metades do problema só podem ser comparadas
construindo um índice paralelo para cada modelo e medindo com a MESMA régua
(recall por documento, `gold_hashes`).

Método: força bruta em memória (cosseno exato), sem sqlite-vec — mais simples de
auditar e independente do storage. Mesmo truncamento do serviço (o tokenizer do
modelo aplica max_length).

Uso:
    PYTHONPATH=src ~/git/mcp-memory-service/.venv/bin/python eval/reembed_experiment.py \
        --db <snapshot> --cases eval/recall_cases_v2.json \
        --models all-MiniLM-L6-v2,paraphrase-multilingual-MiniLM-L12-v2 \
        --out eval/lab_reembed_models.json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "benchmarks"))

import numpy as np  # noqa: E402

from recall_harness import load_cases  # noqa: E402


def load_corpus(db_path, store="default"):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT content_hash, content FROM memories "
            "WHERE store = ? AND deleted_at IS NULL AND content IS NOT NULL AND content != ''",
            (store,),
        ).fetchall()
    finally:
        con.close()
    return rows


def embed_matrix(model, texts, batch=64, log=None):
    out = []
    t0 = time.perf_counter()
    for i in range(0, len(texts), batch):
        chunk = texts[i : i + batch]
        vecs = np.asarray(model.encode(chunk), dtype=np.float32)
        out.append(vecs)
        if log and (i // batch) % 50 == 0:
            done = min(i + batch, len(texts))
            rate = done / max(time.perf_counter() - t0, 1e-9)
            print(f"    {done}/{len(texts)} ({rate:.0f} docs/s)", file=log, flush=True)
    m = np.vstack(out)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def metrics(positions, k):
    n = len(positions)
    return round(sum(1 for p in positions if p and p <= k) / n, 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--cases", default="eval/recall_cases_v2.json")
    ap.add_argument("--models", default="all-MiniLM-L6-v2,paraphrase-multilingual-MiniLM-L12-v2")
    ap.add_argument("--store", default="default")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from mcp_memory_service.embeddings.onnx_embeddings import get_onnx_embedding_model

    cases = load_cases(args.cases)
    corpus = load_corpus(args.db, args.store)
    print(f"corpus: {len(corpus)} memórias do store {args.store!r}", flush=True)
    hashes = [h for h, _ in corpus]
    contents = [c for _, c in corpus]
    index_of = {h: i for i, h in enumerate(hashes)}

    report = {"meta": {"db": args.db, "cases": args.cases, "store": args.store,
                       "corpus": len(corpus)}, "models": {}}

    for name in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"== {name}", flush=True)
        t0 = time.perf_counter()
        model = get_onnx_embedding_model(name)
        if model is None:
            print(f"  modelo indisponível: {name}", file=sys.stderr)
            continue
        doc_vecs = embed_matrix(model, contents, log=sys.stdout)
        embed_s = round(time.perf_counter() - t0, 1)
        q_vecs = embed_matrix(model, [c["pergunta"] for c in cases])

        hits_doc, hits_term_all = [], []
        per_case = []
        sims_all = q_vecs @ doc_vecs.T
        for row, case in enumerate(sims_all):
            order = np.argsort(-case)[:100]
            gold = set(case_hashes for case_hashes in cases[row].get("gold_hashes") or [])
            pos_doc = next(
                (i + 1 for i, idx in enumerate(order) if hashes[idx] in gold), None
            )
            pos_term = None
            for i, idx in enumerate(order):
                content = contents[idx].lower()
                if all(str(t).lower() in content for t in cases[row].get("gold_terms") or []):
                    pos_term = i + 1
                    break
            hits_doc.append(pos_doc)
            hits_term_all.append(pos_term)
            per_case.append({"id": cases[row]["id"], "hash": pos_doc, "term": pos_term})

        report["models"][name] = {
            "embed_seconds": embed_s,
            "ms_por_documento": round(embed_s * 1000 / max(len(contents), 1), 2),
            "documento": {f"recall@{k}": metrics(hits_doc, k) for k in (10, 30, 100)},
            "termo_all": {f"recall@{k}": metrics(hits_term_all, k) for k in (10, 30, 100)},
            "casos": per_case,
        }
        print(json.dumps({k: v for k, v in report["models"][name].items() if k != "casos"},
                         ensure_ascii=False, indent=1), flush=True)

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    print("ok", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
