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
import re
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


def item_hash(repo: str, kind: str, number) -> str:
    return hashlib.sha256(f"gh:{repo}:{kind}:{number}".encode()).hexdigest()


def gh_graphql(query: str, variables: dict) -> dict:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        cmd += ["-f", f"{k}={v}"]
    raw = subprocess.run(cmd, capture_output=True, text=True)
    if raw.returncode != 0:
        raise RuntimeError(f"gh graphql falhou: {raw.stderr.strip()[:200]}")
    return json.loads(raw.stdout or "{}")


def build_review_comment(rc: dict, repo: str) -> str:
    body = (rc.get("body") or "").strip()
    ctx = rc.get("path") or ""
    if rc.get("line") or rc.get("original_line"):
        ctx = f"{ctx}:{rc.get('line') or rc.get('original_line')}"
    prn = None
    url = rc.get("html_url") or ""
    m = re.search(r"/pull/(\d+)", url)
    if m:
        prn = m.group(1)
    return (
        f"[REVIEW-COMMENT] {repo} PR #{prn} — comentário de review"
        f"{(' em ' + ctx) if ctx else ''}\n"
        f"Autor: {(rc.get('user') or {}).get('login')} · Criado: {rc.get('created_at')}"
        f" · Em resposta a: {rc.get('in_reply_to_id') or '—'}\n"
        f"URL: {url}\n\n{body[:2000]}"
    )


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

    async def _store(kind: str, key, content: str, tags: list[str], meta: dict) -> bool:
        h = item_hash(args.repo, kind, key)
        existente = await storage.get_by_hash(h, store=args.store)
        if existente is not None:
            if (existente.metadata or {}).get("gh_updated_at") == meta.get("gh_updated_at") and not args.force:
                return False
            await storage.delete(h, store=args.store)
        mem = Memory(
            content=content, content_hash=h,
            tags=["triagem", f"repo:{args.repo}", f"kind:{kind}", *tags],
            memory_type="reference",
            metadata={"gh_repo": args.repo, "gh_kind": kind, **meta},
        )
        ok, _ = await storage.store(mem, store=args.store, skip_semantic_dedup=True)
        return ok

    rc_n = disc_n = 0
    if args.with_review_comments:
        rcs = gh_api(f"/repos/{args.repo}/pulls/comments?sort=created&direction=desc")
        print(f"comentarios de review coletados: {len(rcs)}", flush=True)
        for rc in rcs:
            pr_url = rc.get("html_url") or ""
            m = re.search(r"/pull/(\d+)", pr_url)
            prn = m.group(1) if m else "0"
            ok = await _store(
                "review_comment", rc["id"], build_review_comment(rc, args.repo),
                [f"pr:{prn}", f"author:{(rc.get('user') or {}).get('login')}"],
                {"gh_pr": int(prn), "gh_comment_id": rc["id"],
                 "gh_path": rc.get("path"), "gh_line": rc.get("line") or rc.get("original_line"),
                 "gh_author": (rc.get("user") or {}).get("login"),
                 "gh_updated_at": rc.get("updated_at") or rc.get("created_at"),
                 "gh_url": pr_url},
            )
            rc_n += 1 if ok else 0

    if args.with_discussions:
        q = ("query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name){"
             "discussions(first:50,after:$cursor){pageInfo{hasNextPage endCursor}"
             "nodes{number title body createdAt updatedAt url category{name} author{login}}}}}")
        owner, name = args.repo.split("/")
        cursor = ""
        while True:
            data = gh_graphql(q, {"owner": owner, "name": name, "cursor": cursor})
            d = ((data.get("data") or {}).get("repository") or {}).get("discussions") or {}
            nodes = d.get("nodes") or []
            for node in nodes:
                content = (
                    f"[DISCUSSION] {args.repo}#{node['number']} — {node.get('title')}\n"
                    f"Categoria: {(node.get('category') or {}).get('name')} · "
                    f"Autor: {(node.get('author') or {}).get('login')}\n"
                    f"Criado: {node.get('createdAt')} · Atualizado: {node.get('updatedAt')}\n"
                    f"URL: {node.get('url')}\n\n{(node.get('body') or '')[:2500]}"
                )
                ok = await _store(
                    "discussion", node["number"], content,
                    [f"number:{node['number']}", "discussion"],
                    {"gh_number": node["number"],
                     "gh_author": (node.get("author") or {}).get("login"),
                     "gh_updated_at": node.get("updatedAt"), "gh_url": node.get("url")},
                )
                disc_n += 1 if ok else 0
            if not d.get("pageInfo", {}).get("hasNextPage"):
                break
            cursor = d["pageInfo"]["endCursor"]

    await storage.close()
    print(
        json.dumps(
            {"repo": args.repo, "novos": novos, "atualizados": atualizados,
             "ignorados_sem_mudanca": ignorados, "review_comments_novos": rc_n,
             "discussions_novas": disc_n, "store": args.store},
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
    ap.add_argument("--with-review-comments", action="store_true")
    ap.add_argument("--with-discussions", action="store_true")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
