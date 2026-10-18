"""O acervo é o problema? Mede recall num corpus higienizado com um único modelo.

Pergunta do Claudio: um banco zerado, recarregado só com memórias higienizadas,
passaria pelos mesmos problemas?

Este experimento isola a variável "conteúdo". Mantém o modelo (paraphrase, o
configurado) e a régua (120 casos, acerto por documento), e varia apenas o corpus:

  A) completo ........ 20.310 memórias como estão
  B) higienizado ..... sem duplicatas exatas/normalizadas, sem lixo evidente
                       (traceback, saída de git, dump binário, fragmento <40 chars)
  C) higienizado+dedup semântico .... B + colapso de quase-duplicados (cosine >= 0.97)

Nenhuma memória gold é removida (proteção explícita). A indexação é força bruta em
memória, cosseno exato — a mesma de `reembed_experiment.py`, para comparabilidade.

Uso:
    PYTHONPATH=src ~/git/mcp-memory-service/.venv/bin/python eval/clean_corpus_experiment.py \
        --db <snapshot> --cases eval/recall_cases_v2.json \
        --model paraphrase-multilingual-MiniLM-L12-v2 --out eval/lab_clean_corpus.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "benchmarks"))

import numpy as np  # noqa: E402

from recall_harness import load_cases  # noqa: E402

JUNK_PATTERNS = [
    r"Traceback \(most recent call last\)",
    r"^\s*\[Test Cleanup\]",
    r"^\s*diff --git ",
    r"^\s*M\t\S+\s*$",
    r"^[A-Za-z0-9+/]{120,}={0,2}$",
    r"command not found",
    r"^\s*npm (ERR!|error)",
]


def is_junk(text: str) -> bool:
    if len(text.strip()) < 40:
        return True
    for pat in JUNK_PATTERNS:
        if re.search(pat, text, re.I | re.M):
            return True
    return False


def norm_key(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text.strip().lower()).encode()).hexdigest()


def load_corpus(db_path, store="default"):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return con.execute(
            "SELECT content_hash, content, created_at FROM memories "
            "WHERE store = ? AND deleted_at IS NULL AND content IS NOT NULL AND content != ''",
            (store,),
        ).fetchall()
    finally:
        con.close()


def l2(m):
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def recall_at(pos, k):
    return round(sum(1 for p in pos if p and p <= k) / len(pos), 4)


def _cache_path(db, model, tag):
    base = os.path.join(os.path.dirname(__file__), "..", ".cache")
    os.makedirs(base, exist_ok=True)
    key = hashlib.sha256(f"{db}|{model}|{tag}".encode()).hexdigest()[:16]
    return os.path.join(base, f"emb_{key}.npy")


def embed(model, texts, log=None, cache=None):
    if cache and os.path.isfile(cache):
        arr = np.load(cache)
        if arr.shape[0] == len(texts):
            print(f"    cache: {arr.shape}", file=log or sys.stdout, flush=True)
            return arr
    out = []
    t0 = time.perf_counter()
    for i in range(0, len(texts), 64):
        out.append(np.asarray(model.encode(texts[i : i + 64]), dtype=np.float32))
        if log and (i // 64) % 100 == 0:
            print(f"    {min(i+64, len(texts))}/{len(texts)}", file=log, flush=True)
    mat = l2(np.vstack(out))
    if cache:
        np.save(cache, mat)
    return mat


def evaluate(model, doc_vecs, hashes, contents, cases):
    q = embed(model, [c["pergunta"] for c in cases])
    pos = []
    for r in range(len(cases)):
        sims = doc_vecs @ q[r]
        order = np.argsort(-sims)[:100]
        gold = set(cases[r].get("gold_hashes") or [])
        pos.append(next((i + 1 for i, idx in enumerate(order) if hashes[idx] in gold), None))
    return {f"recall@{k}": recall_at(pos, k) for k in (10, 30, 100)}, pos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--cases", default="eval/recall_cases_v2.json")
    ap.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2")
    ap.add_argument("--store", default="default")
    ap.add_argument("--semantic-threshold", type=float, default=0.97)
    ap.add_argument("--skip-full", action="store_true",
                    help="pula a variante A (corpus completo): use quando o número já "
                         "existe de outra execução com o mesmo modelo/método")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from mcp_memory_service.embeddings.onnx_embeddings import get_onnx_embedding_model

    model = get_onnx_embedding_model(args.model)
    cases = load_cases(args.cases)
    gold_all = {h for c in cases for h in (c.get("gold_hashes") or [])}
    corpus = load_corpus(args.db, args.store)
    print(f"corpus completo: {len(corpus)}", flush=True)

    # --- B: higienização determinística
    seen = {}
    clean = []
    drop_dup = drop_junk = drop_gold_protected = 0
    for h, content, created in sorted(corpus, key=lambda r: float(r[2] or 0)):
        if is_junk(content) and h not in gold_all:
            drop_junk += 1
            continue
        key = norm_key(content)
        if key in seen:
            if h not in gold_all:
                drop_dup += 1
                continue
            drop_gold_protected += 1
        else:
            seen[key] = h
        clean.append((h, content))
    print(f"higienizado: {len(clean)} (-{drop_junk} lixo, -{drop_dup} duplicata)", flush=True)

    results = {}
    if args.skip_full:
        print("variante A pulada (--skip-full)", flush=True)
    else:
        hashes = [r[0] for r in corpus]
        contents = [r[1] for r in corpus]
        t0 = time.perf_counter()
        vecs = embed(model, contents, log=sys.stdout,
                     cache=_cache_path(args.db, args.model, f"full{len(contents)}"))
        print(f"  embeddings completos em {time.perf_counter()-t0:.0f}s", flush=True)
        m, pos = evaluate(model, vecs, hashes, contents, cases)
        results["A_completo"] = {"n": len(corpus), **m}

    hashes_c = [h for h, _ in clean]
    contents_c = [c for _, c in clean]
    t0 = time.perf_counter()
    vecs_c = embed(model, contents_c, log=sys.stdout, cache=_cache_path(args.db, args.model, f"clean{len(contents_c)}"))
    print(f"  embeddings higienizados em {time.perf_counter()-t0:.0f}s", flush=True)
    m2, _ = evaluate(model, vecs_c, hashes_c, contents_c, cases)
    results["B_higienizado"] = {"n": len(clean), **m2}

    # --- C: dedup semântico guloso (ordem do mais antigo para o mais novo)
    keep_idx: list[int] = []
    buf = np.zeros_like(vecs_c)  # matriz pré-alocada: view, sem cópia por iteração
    n_keep = 0
    for i in range(len(clean)):
        v = vecs_c[i]
        if n_keep:
            sims = buf[:n_keep] @ v
            if float(sims.max()) >= args.semantic_threshold and clean[i][0] not in gold_all:
                continue
        buf[n_keep] = v
        n_keep += 1
        keep_idx.append(i)
    vecs_cc = vecs_c[keep_idx]
    hashes_cc = [clean[i][0] for i in keep_idx]
    contents_cc = [clean[i][1] for i in keep_idx]
    print(f"higienizado + dedup semântico: {len(keep_idx)}", flush=True)
    m3, _ = evaluate(model, vecs_cc, hashes_cc, contents_cc, cases)
    results["C_higienizado_dedup"] = {"n": len(keep_idx), **m3}

    report = {
        "meta": {"db": args.db, "cases": args.cases, "model": args.model,
                 "store": args.store, "threshold_semantico": args.semantic_threshold,
                 "corpus_original": len(corpus), "removidos_lixo": drop_junk,
                 "removidos_duplicata": drop_dup},
        "resultados": results,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
