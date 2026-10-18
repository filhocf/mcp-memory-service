"""Ferramentas de régua e regressão por identificador.

Dois subcomandos, ambos read-only por padrão:

  remap   — reescreve gold_hashes mortos (soft-deleted por dedup) para o
            sobrevivente indicado em `superseded_by`. Sem isso, qualquer limpeza
            futura invalida silenciosamente a régua: foi o que aconteceu quando
            a dedup tombou 9 dos 120 golds e o número caiu 5,8 p.p. por artefato.

  identifiers — regressão de utilidade da triagem: para cada #N citado de fato
            pelo usuário, o banco sabe o estado do item e esse estado bate com o
            `gh`? Mede cobertura, acerto de estado e latência.

Uso:
    python eval/ruler_tools.py remap --cases eval/recall_cases_v2.json \
        --db ~/local-data/mcp/sqlite_vec.db --out eval/recall_cases_v3.json
    python eval/ruler_tools.py identifiers --refs eval/perguntas_triagem_reais.json \
        --db ~/local-data/mcp/bench/triagem-upstream.db --repo doobidoo/mcp-memory-service
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import subprocess
import sys
import time
import urllib.request


def cmd_remap(args) -> int:
    con = sqlite3.connect(f"file:{os.path.expanduser(args.db)}?mode=ro", uri=True)
    cases = json.load(open(args.cases))["cases"]
    remapped, dead_no_successor, alive = 0, 0, 0
    for c in cases:
        h = c["gold_hashes"][0]
        row = con.execute(
            "SELECT deleted_at, superseded_by FROM memories WHERE content_hash = ?", (h,)
        ).fetchone()
        if row is None:
            c["gold_ausente_no_banco"] = True
            continue
        if row[0] is None:
            alive += 1
            continue
        if row[1]:
            c.setdefault("gold_hash_original", h)
            c["gold_hashes"] = [row[1]]
            remapped += 1
        else:
            c["gold_morto_sem_sucessor"] = True
            dead_no_successor += 1
    con.close()
    json.dump({"cases": cases}, open(args.out, "w"), ensure_ascii=False, indent=1)
    print(
        json.dumps(
            {"casos": len(cases), "golds_vivos": alive, "remapeados": remapped,
             "mortos_sem_sucessor": dead_no_successor, "out": args.out},
            ensure_ascii=False,
        )
    )
    return 0


def _mcp(port: int, name: str, arguments: dict) -> tuple[str, float]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
    )
    t0 = time.time()
    raw = urllib.request.urlopen(req, timeout=30).read().decode()
    elapsed = (time.time() - t0) * 1000
    for line in raw.splitlines():
        if line.startswith("data: "):
            d = json.loads(line[6:])
            if "result" in d:
                return d["result"]["content"][0]["text"], elapsed
    return "", elapsed


def cmd_identifiers(args) -> int:
    refs = json.load(open(args.refs))
    numbers = refs.get("referencias") or []
    results, lat = [], []
    for n in numbers:
        # Filtro por tag é exato por construção: busca textual por "#1097" devolve
        # qualquer memória que MENCIONE o número, não o item 1097 em si.
        txt, ms = _mcp(args.port, "memory_search",
                       {"query": str(n), "mode": "semantic", "limit": 1,
                        "store": args.store, "tags": [f"number:{n}"]})
        lat.append(ms)
        encontrado = f"#{n} " in txt or f"#{n}—" in txt or f"#{n} —" in txt
        item = {"numero": n, "no_banco": encontrado, "latencia_ms": round(ms)}
        if encontrado and args.check_gh:
            raw = subprocess.run(
                ["gh", "api", f"/repos/{args.repo}/issues/{n}", "-q", "[.state,.title]|@tsv"],
                capture_output=True, text=True,
            )
            if raw.returncode == 0:
                estado_gh = raw.stdout.split("\t")[0].strip()
                item["estado_gh"] = estado_gh
                item["estado_banco_correto"] = f"Estado: {estado_gh}" in txt
        results.append(item)
    cobertos = sum(1 for r in results if r["no_banco"])
    corretos = sum(1 for r in results if r.get("estado_banco_correto"))
    verificados = sum(1 for r in results if "estado_banco_correto" in r)
    out = {
        "referencias": len(numbers),
        "cobertura": f"{cobertos}/{len(numbers)}",
        "estado_correto": f"{corretos}/{verificados}" if verificados else "n/d",
        "latencia_p50_ms": round(statistics.median(lat)) if lat else None,
        "faltando": [r["numero"] for r in results if not r["no_banco"]],
        "detalhe": results,
    }
    print(json.dumps({k: v for k, v in out.items() if k != "detalhe"}, ensure_ascii=False, indent=1))
    if args.out:
        json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=1)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("remap")
    r.add_argument("--cases", required=True)
    r.add_argument("--db", required=True)
    r.add_argument("--out", required=True)
    r.set_defaults(func=cmd_remap)

    i = sub.add_parser("identifiers")
    i.add_argument("--refs", required=True)
    i.add_argument("--db", required=True)
    i.add_argument("--repo", default="doobidoo/mcp-memory-service")
    i.add_argument("--port", type=int, default=3205)
    i.add_argument("--store", default="triage")
    i.add_argument("--check-gh", action="store_true")
    i.add_argument("--out", default=None)
    i.set_defaults(func=cmd_identifiers)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
