"""Chunking honesto: índice por blocos de <=128 tokens com agregação por documento.

O truncamento em 128 tokens (A2) corta a memória longa: o vetor representa só o
começo. O experimento anterior mediu chunking com cosseno puro, sem agregar por
documento, e por isso falhou em escala — o documento gold não era reconstruído.

Aqui cada memória é dividida em blocos de até 126 tokens (limite do tokenizer),
cada bloco recebe um vetor, e a relevância de um documento é o **máximo** entre
seus blocos (max-pool). A métrica é a do cliente: recall por documento
(`gold_hashes`) em @10/@30/@100, comparada com a execução sem chunking do mesmo
índice uniforme.

Uso:
    PYTHONPATH=src ~/git/mcp-memory-service/.venv/bin/python eval/chunking_maxpool.py \
        --db <snapshot> --cases eval/recall_cases_v2.json \
        --model paraphrase-multilingual-MiniLM-L12-v2 --out eval/lab_chunking_maxpool.json
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

MAX_TOKENS = 126


def load_corpus(db_path, store="default"):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return con.execute(
            "SELECT content_hash, content FROM memories "
            "WHERE store = ? AND deleted_at IS NULL AND content IS NOT NULL AND content != ''",
            (store,),
        ).fetchall()
    finally:
        con.close()


def chunk_text(tokenizer, text, stride):
    ids = tokenizer.encode(text).ids
    if len(ids) <= MAX_TOKENS:
        return [text], 1
    chunks = []
    start = 0
    while start < len(ids):
        piece = ids[start : start + MAX_TOKENS]
        chunks.append(tokenizer.decode(piece))
        if start + MAX_TOKENS >= len(ids):
            break
        start += stride
    return chunks, len(ids)


def l2(m):
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def recall_at(positions, k):
    return round(sum(1 for p in positions if p and p <= k) / len(positions), 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--cases", default="eval/recall_cases_v2.json")
    ap.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2")
    ap.add_argument("--stride", type=int, default=96)
    ap.add_argument("--store", default="default")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from mcp_memory_service.embeddings.onnx_embeddings import get_onnx_embedding_model

    model = get_onnx_embedding_model(args.model)
    tokenizer = model._tokenizer
    tokenizer.no_truncation()
    tokenizer.no_padding()

    cases = load_cases(args.cases)
    corpus = load_corpus(args.db, args.store)
    hashes = [h for h, _ in corpus]
    contents = [c for _, c in corpus]
    print(f"corpus {len(corpus)} · modelo {args.model} · stride {args.stride}", flush=True)

    # 1. chunking
    t0 = time.perf_counter()
    all_chunks: list[str] = []
    doc_of_chunk: list[int] = []
    n_tokens = 0
    for i, text in enumerate(contents):
        pieces, ntok = chunk_text(tokenizer, text, args.stride)
        n_tokens += ntok
        all_chunks.extend(pieces)
        doc_of_chunk.extend([i] * len(pieces))
    doc_of_chunk_arr = np.asarray(doc_of_chunk, dtype=np.int32)
    print(
        f"chunks {len(all_chunks)} de {len(contents)} memórias "
        f"(tokens {n_tokens}, razão {len(all_chunks)/len(contents):.2f}, {time.perf_counter()-t0:.1f}s)",
        flush=True,
    )

    # 2. embeddings dos chunks (o modelo aplica truncamento de 128: os blocos já cabem)
    t0 = time.perf_counter()
    vecs = []
    batch = 64
    for i in range(0, len(all_chunks), batch):
        vecs.append(np.asarray(model.encode(all_chunks[i : i + batch]), dtype=np.float32))
        if (i // batch) % 100 == 0:
            done = min(i + batch, len(all_chunks))
            print(f"    {done}/{len(all_chunks)} ({done/(time.perf_counter()-t0):.0f} chunks/s)", flush=True)
    chunk_vecs = l2(np.vstack(vecs))
    embed_s = round(time.perf_counter() - t0, 1)
    print(f"embeddings de chunks: {embed_s}s", flush=True)

    # 3. consultas + max-pool por documento
    q_vecs = l2(np.asarray(model.encode([c["pergunta"] for c in cases]), dtype=np.float32))
    n_docs = len(contents)
    pos_doc, pos_term = [], []
    for row in range(len(cases)):
        sims = chunk_vecs @ q_vecs[row]
        best = np.full(n_docs, -np.inf, dtype=np.float32)
        np.maximum.at(best, doc_of_chunk_arr, sims)
        order = np.argsort(-best)[:100]
        gold = set(cases[row].get("gold_hashes") or [])
        p = next((i + 1 for i, idx in enumerate(order) if hashes[idx] in gold), None)
        pos_doc.append(p)
        pt = None
        for i, idx in enumerate(order):
            c = contents[idx].lower()
            if all(str(t).lower() in c for t in cases[row].get("gold_terms") or []):
                pt = i + 1
                break
        pos_term.append(pt)

    report = {
        "meta": {"db": args.db, "cases": args.cases, "model": args.model,
                 "stride": args.stride, "store": args.store,
                 "corpus": len(contents), "chunks": len(all_chunks),
                 "embed_seconds": embed_s},
        "documento": {f"recall@{k}": recall_at(pos_doc, k) for k in (10, 30, 100)},
        "termo_all": {f"recall@{k}": recall_at(pos_term, k) for k in (10, 30, 100)},
        "posicoes": pos_doc,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "posicoes"},
                     ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
