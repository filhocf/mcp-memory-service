"""Importador de issues e PRs do GitHub para a base de TRIAGEM do mms.

Uso interno — vive só no nosso repo, em qualquer máquina. Nunca vai para upstream.

Desenho:
- uma memória por issue/PR, com hash determinístico `sha256("gh:{repo}:{kind}:{n}")`;
- reingestão idempotente: se o item mudou (updatedAt diferente do que está no
  metadata), a versão anterior é removida e a nova gravada — sem acumular duplicata;
- conteúdo autossuficiente: título, estado, autor, labels, datas e corpo truncado,
  com comentários recentes quando pedido;
- procedência em tags (`repo:`, `kind:`, `number:`, `state:`, `label:`) e metadata
  (`updated_at`, `url`), para consulta exata por identificador e para denunciar
  obsolescência.

Uso:
    PYTHONPATH=src python eval/ingest_github_triage.py \
        --repo doobidoo/mcp-memory-service --db ~/local-data/mcp/bench/triagem-upstream.db \
        --state all --limit 200
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def gh_api(path: str, per_page: int = 100) -> list[dict]:
    out: list[dict] = []
    page = 1
    while True:
        sep = "&" if "?" in path else "?"
        url = f"{path}{sep}per_page={per_page}&page={page}"
        raw = subprocess.run(["gh", "api", url], capture_output=True, text=True)
        if raw.returncode != 0:
            raise RuntimeError(f"gh api falhou em {url}: {raw.stderr.strip()[:200]}")
        batch = json.loads(raw.stdout or "[]")
        if not batch:
            break
        out.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return out


def item_hash(repo: str, kind: str, number: int) -> str:
    return hashlib.sha256(f"gh:{repo}:{kind}:{number}".encode()).hexdigest()


def build_content(item: dict, repo: str, kind: str, body_limit: int) -> str:
    labels = ", ".join(l["name"] for l in item.get("labels") or []) or "—"
    body = (item.get("body") or "").strip()
    if len(body) > body_limit:
        body = body[:body_limit] + "\n[... corpo truncado na ingestão ...]"
    comments = item.get("comments") or 0
    return (
        f"[{kind.upper()}] {repo}#{item['number']} — {item.get('title') or ''}\n"
        f"Estado: {item.get('state')}"
        + (f" ({item['state_reason']})" if item.get("state_reason") else "")
        + f" · Autor: {(item.get('user') or {}).get('login')}\n"
        f"Labels: {labels} · Comentários: {comments}\n"
        f"Criado: {item.get('created_at')} · Atualizado: {item.get('updated_at')}\n"
        f"URL: {item.get('html_url')}\n\n{body}"
    )


async def run(args) -> int:
    from mcp_memory_service.models.memory import Memory
    from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage

    db = Path(os.path.expanduser(args.db))
    db.parent.mkdir(parents=True, exist_ok=True)
    storage = SqliteVecMemoryStorage(str(db), embedding_model=args.model)
    await storage.initialize()
    print(f"base de triagem: {db} · modelo {args.model}", flush=True)

    # issues e PRs vêm do mesmo endpoint; `pull_request` distingue
    raw = gh_api(f"/repos/{args.repo}/issues?state={args.state}&sort=updated&direction=desc")
    if args.limit:
        raw = raw[: args.limit]
    print(f"coletados {len(raw)} itens de {args.repo}", flush=True)

    novos = atualizados = ignorados = 0
    for item in raw:
        kind = "pr" if item.get("pull_request") else "issue"
        number = item["number"]
        h = item_hash(args.repo, kind, number)
        content = build_content(item, args.repo, kind, args.body_limit)

        existente = await storage.get_by_hash(h, store=args.store)
        if existente is not None:
            antigo = (existente.metadata or {}).get("gh_updated_at")
            if antigo == item.get("updated_at") and not args.force:
                ignorados += 1
                continue
            await storage.delete(h, store=args.store)
            atualizados += 1
        else:
            novos += 1

        labels = [f"label:{l['name']}" for l in item.get("labels") or []]
        mem = Memory(
            content=content,
            content_hash=h,
            tags=[
                "triagem",
                f"repo:{args.repo}",
                f"kind:{kind}",
                f"number:{number}",
                f"state:{item.get('state')}",
                *labels,
            ],
            memory_type="reference",
            metadata={
                "gh_repo": args.repo,
                "gh_kind": kind,
                "gh_number": number,
                "gh_state": item.get("state"),
                "gh_updated_at": item.get("updated_at"),
                "gh_author": (item.get("user") or {}).get("login"),
                "gh_url": item.get("html_url"),
                "ingested_at": item.get("updated_at"),
            },
        )
        ok, msg = await storage.store(mem, store=args.store, skip_semantic_dedup=True)
        if not ok:
            print(f"  falha em #{number}: {msg}", file=sys.stderr)

    await storage.close()
    print(
        json.dumps(
            {"repo": args.repo, "novos": novos, "atualizados": atualizados,
             "ignorados_sem_mudanca": ignorados, "store": args.store},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/nome, ex. doobidoo/mcp-memory-service")
    ap.add_argument("--db", default=os.path.expanduser("~/local-data/mcp/bench/triagem-upstream.db"))
    ap.add_argument("--store", default="triage")
    ap.add_argument("--model", default="all-MiniLM-L6-v2")
    ap.add_argument("--state", default="all", choices=["all", "open", "closed"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--body-limit", type=int, default=2000)
    ap.add_argument("--force", action="store_true")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
