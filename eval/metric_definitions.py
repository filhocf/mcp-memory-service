"""Compara duas definições de acerto sobre a mesma execução.

O harness mede posição por TERMO (`gold_terms` presentes no conteúdo de algum
resultado). Uma leitura mais estrita é por DOCUMENTO (`gold_hashes`: a memória que
de fato responde à pergunta). As duas não são equivalentes:

- termo  -> crédito se qualquer memória do top-k contiver os termos-chave;
- hash   -> crédito só se a memória gold estiver no top-k.

Este script roda uma vez por caso (limit = k_max), guarda os resultados e calcula
recall@k sob as duas definições, para saber quanto do número depende da régua e não
do sistema.

Uso:
    PYTHONPATH=src ~/git/mcp-memory-service/.venv/bin/python eval/metric_definitions.py \
        --db <snapshot> --cases eval/recall_cases_v2.json \
        --embedding-model all-MiniLM-L6-v2 --out eval/lab_metric_definitions.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "benchmarks"))

from recall_harness import load_cases, make_runner  # noqa: E402


def _pos_term(results, terms):
    if not terms:
        return None
    for i, r in enumerate(results):
        content = str(r.get("content") or "").lower()
        if all(str(t).lower() in content for t in terms):
            return i + 1
    return None


def _pos_hash(results, gold):
    for i, r in enumerate(results):
        if r.get("content_hash") in gold:
            return i + 1
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--cases", default="eval/recall_cases_v2.json")
    ap.add_argument("--embedding-model", default=None)
    ap.add_argument("--mode", default="semantic")
    ap.add_argument("--kmax", type=int, default=100)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    runner = make_runner(args.db, embedding_model=args.embedding_model)
    cases = load_cases(args.cases)

    rows = []
    for case in cases:
        res = runner(case["pergunta"], args.mode, args.kmax)
        gold = set(case.get("gold_hashes") or [])
        rows.append(
            {
                "id": case["id"],
                "categoria": case.get("categoria"),
                "idioma": case.get("idioma"),
                "term": _pos_term(res, case.get("gold_terms") or []),
                "hash": _pos_hash(res, gold),
            }
        )

    out = {"meta": {"mode": args.mode, "kmax": args.kmax, "db": args.db,
                    "cases": args.cases, "embedding_model": args.embedding_model}}
    for k in (10, 30, 100):
        if k > args.kmax:
            continue
        t = [r["term"] for r in rows]
        h = [r["hash"] for r in rows]
        out[str(k)] = {
            "recall_por_termo": round(sum(1 for p in t if p and p <= k) / len(rows), 4),
            "recall_por_documento": round(sum(1 for p in h if p and p <= k) / len(rows), 4),
            "divergentes": sum(
                1
                for a, b in zip(t, h)
                if (a is not None and a <= k) != (b is not None and b <= k)
            ),
        }
    out["so_termo"] = sum(1 for r in rows if r["term"] and not r["hash"])
    out["so_documento"] = sum(1 for r in rows if r["hash"] and not r["term"])
    out["ambos_no_topo100"] = sum(1 for r in rows if r["term"] and r["hash"])
    out["casos"] = rows

    payload = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "casos"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
