"""Manutenção de higiene do acervo: duplicatas e stores corrompidos (plano + aplicação).

O que faz, em duas etapas separadas e auditáveis:

1. **Duplicatas exatas de conteúdo normalizado** (espaços colapsados, caixa baixa).
   Sobrevive a linha com maior `last_accessed` e, no empate, a mais antiga. As demais
   recebem `deleted_at` e `superseded_by` apontando para a sobrevivente — soft delete,
   reversível, sem perder proveniência nem quebrar arestas de grafo.

2. **Stores com nome inválido** (caracteres de controle no nome da partição). São
   vestígios de escrita malfeita, não memória de projeto: recebem `deleted_at`.

Uso:
    # plano (não escreve nada)
    python eval/dedup_maintenance.py --db <sqlite_vec.db> --out plano.json
    # aplicação (exige o plano e --apply)
    python eval/dedup_maintenance.py --db <sqlite_vec.db> --apply --out aplicado.json

Cuidados: o DB deve estar com o serviço parado; faça backup antes. Isto NÃO re-embeda
e NÃO mexe em vetores — só marca linhas como deletadas.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from collections import defaultdict


def norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def plan(db_path: str) -> dict:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cols = [r[1] for r in con.execute("pragma table_info(memories)")]
        access = "last_accessed" if "last_accessed" in cols else None
        rows = con.execute(
            f"SELECT rowid, content_hash, content, created_at, "
            f"{access or '0'}, store FROM memories WHERE deleted_at IS NULL"
        ).fetchall()
        corrupt = con.execute(
            "SELECT rowid, content_hash, store FROM memories "
            "WHERE deleted_at IS NULL AND store GLOB '*[^ -~]*'"
        ).fetchall()
    finally:
        con.close()

    groups: dict[str, list[tuple]] = defaultdict(list)
    for r in rows:
        groups[norm_key(r[2])].append(r)

    dup_plan = []
    for content, members in groups.items():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda r: (-(r[4] or 0), r[3] or 0))
        keeper = ordered[0]
        dup_plan.append(
            {
                "sobrevivente": {"rowid": keeper[0], "hash": keeper[1]},
                "tombar": [{"rowid": m[0], "hash": m[1]} for m in ordered[1:]],
                "store": keeper[5],
                "preview": (keeper[2] or "")[:90],
            }
        )

    return {
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "db": db_path,
        "vivas": len(rows),
        "grupos_duplicados": len(dup_plan),
        "linhas_a_tombar": sum(len(d["tombar"]) for d in dup_plan),
        "stores_corrompidos": [{"rowid": r[0], "hash": r[1], "store": repr(r[2])} for r in corrupt],
        "plano_duplicatas": dup_plan,
    }


def apply(db_path: str, p: dict) -> dict:
    con = sqlite3.connect(db_path)
    applied_dup = applied_bad = 0
    now = time.time()
    try:
        con.execute("BEGIN")
        for entry in p["plano_duplicatas"]:
            keeper_hash = entry["sobrevivente"]["hash"]
            for item in entry["tombar"]:
                con.execute(
                    "UPDATE memories SET deleted_at = ?, superseded_by = ? "
                    "WHERE rowid = ? AND deleted_at IS NULL",
                    (now, keeper_hash, item["rowid"]),
                )
                applied_dup += 1
        for item in p["stores_corrompidos"]:
            con.execute(
                "UPDATE memories SET deleted_at = ? WHERE rowid = ? AND deleted_at IS NULL",
                (now, item["rowid"]),
            )
            applied_bad += 1
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {"tombadas_duplicatas": applied_dup, "tombados_stores_corrompidos": applied_bad}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--apply", action="store_true", help="aplica o plano (padrão: só planeja)")
    args = ap.parse_args()

    p = plan(args.db)
    result = {"plano": {k: v for k, v in p.items() if k != "plano_duplicatas"}}
    result["plano"]["exemplos"] = [
        {k: v for k, v in d.items() if k != "preview"} for d in p["plano_duplicatas"][:5]
    ]
    if args.apply:
        result["aplicado"] = apply(args.db, p)
        after = plan(args.db)
        result["depois"] = {
            "vivas": after["vivas"],
            "grupos_duplicados": after["grupos_duplicados"],
            "stores_corrompidos": len(after["stores_corrompidos"]),
        }

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
