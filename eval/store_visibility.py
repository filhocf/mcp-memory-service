"""Custo e benefício de buscar em todos os stores.

O serviço filtra por `store` e o handler usa `default` quando o cliente não passa
nada (`arguments.get("store", "default")`). Resultado: 26,9% do acervo (mir,
docs-shared, hackathon, docs) nunca aparece numa busca normal.

Aqui a mesma pergunta é feita duas vezes — restrita ao `default` e aberta a todos os
stores — e comparada pela régua por documento. Isso separa "cobertura extra" de
"ruído extra": se a métrica não cai ao abrir os stores, a visibilidade é gratuita.

Uso:
    PYTHONPATH=src ~/git/mcp-memory-service/.venv/bin/python eval/store_visibility.py \
        --db <migrado> --cases eval/recall_cases_v2.json --out eval/lab_store_visibility.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "benchmarks"))

from recall_harness import _make_readonly_storage_class, load_cases  # noqa: E402


def recall_at(positions, k):
    return round(sum(1 for p in positions if p and p <= k) / len(positions), 4)


def run_set(db_path, queries, store, model, kmax):
    storage_cls = _make_readonly_storage_class()

    async def _all():
        storage = storage_cls(db_path, embedding_model=model)
        await storage.initialize(strict_dimension_check=False)
        out = []
        for q in queries:
            res = await storage.search_memories(
                query=q, mode="semantic", limit=kmax, store=store
            )
            out.append(res.get("memories") or [])
        return out

    return asyncio.run(_all())


def positions(results, cases):
    pos = []
    for res, case in zip(results, cases):
        gold = set(case.get("gold_hashes") or [])
        pos.append(next((i + 1 for i, r in enumerate(res) if r.get("content_hash") in gold), None))
    return pos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--cases", default="eval/recall_cases_v2.json")
    ap.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2")
    ap.add_argument("--kmax", type=int, default=100)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cases = load_cases(args.cases)
    queries = [c["pergunta"] for c in cases]

    default_res = run_set(args.db, queries, "default", args.model, args.kmax)
    all_res = run_set(args.db, queries, None, args.model, args.kmax)

    pos_d = positions(default_res, cases)
    pos_a = positions(all_res, cases)

    # Quanto do top-10 aberto vem de fora do default. Os resultados do storage não
    # carregam o campo ``store``: a origem é resolvida no banco pelo content_hash.
    import sqlite3

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        store_of = dict(con.execute("SELECT content_hash, store FROM memories").fetchall())
    finally:
        con.close()
    fora = 0
    total = 0
    for res in all_res:
        for r in res[:10]:
            total += 1
            if store_of.get(r.get("content_hash")) not in (None, "default"):
                fora += 1

    report = {
        "meta": {"db": args.db, "cases": args.cases, "model": args.model, "kmax": args.kmax},
        "default": {f"documento@{k}": recall_at(pos_d, k) for k in (10, 30, 100)},
        "todos_os_stores": {f"documento@{k}": recall_at(pos_a, k) for k in (10, 30, 100)},
        "slots_top10_de_outros_stores": f"{fora}/{total}",
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
