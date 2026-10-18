"""Constrói a bancada canônica da trilha UPSTREAM.

Corpus: documentação do repositório upstream, lida de um commit fixo (SHA), em inglês,
com o modelo de embedding padrão do produto (`all-MiniLM-L6-v2`). Grava em um arquivo
SQLite próprio — nunca no acervo pessoal — usando a API de storage do próprio produto,
o que garante schema e tabela vetorial idênticos aos de produção (incluindo a coluna de
partição `store`).

Por que arquivo separado e não partição: o modelo de embedding é configuração de
instância. Vetores de modelos diferentes não podem conviver no mesmo arquivo — foi
exatamente essa violação que partiu o acervo pessoal em três espaços.

Uso:
    PYTHONPATH=src ~/git/mcp-memory-service/.venv/bin/python eval/build_bench_corpus.py \
        --repo ~/git/mcp-memory-service --ref upstream/main \
        --out ~/local-data/mcp/bench/bench-upstream.db
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CHUNK_TARGET = 800      # caracteres por memória
CHUNK_MAX = 1400

PT_MARKERS = {
    "que", "para", "não", "com", "uma", "dos", "das", "por", "como", "mais",
    "você", "isso", "esta", "são", "pode", "quando", "também", "configuração",
}
EN_MARKERS = {
    "the", "and", "with", "that", "this", "from", "for", "are", "you", "your",
    "when", "which", "will", "can", "not", "have", "use", "config", "run",
}


def git(repo: str, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, check=True
    ).stdout


def list_docs(repo: str, ref: str) -> list[str]:
    out = git(repo, "ls-tree", "-r", "--name-only", ref, "docs/")
    paths = [p for p in out.splitlines() if p.endswith(".md")]
    for extra in ("README.md", "CHANGELOG.md"):
        try:
            git(repo, "cat-file", "-e", f"{ref}:{extra}")
            paths.append(extra)
        except subprocess.CalledProcessError:
            pass
    return paths


def is_english(text: str) -> bool:
    words = re.findall(r"[a-zà-ú]+", text.lower())
    if not words:
        return False
    pt = sum(1 for w in words if w in PT_MARKERS)
    en = sum(1 for w in words if w in EN_MARKERS)
    return en >= pt


def split_sections(md: str) -> tuple[str, list[tuple[str, str]]]:
    """Divide um markdown em (título_doc, seção) preservando hierarquia."""
    title = ""
    sections: list[tuple[str, str]] = []
    current_head = ""
    buf: list[str] = []
    for line in md.splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        m = re.match(r"^(#{2,4})\s+(.*)$", line)
        if m:
            if buf and any(b.strip() for b in buf):
                sections.append((current_head, "\n".join(buf).strip()))
            current_head = m.group(2).strip()
            buf = []
        else:
            buf.append(line)
    if buf and any(b.strip() for b in buf):
        sections.append((current_head, "\n".join(buf).strip()))
    return title, sections


def chunk_section(title: str, head: str, body: str) -> list[str]:
    prefix = f"{title} — {head}\n\n" if head else f"{title}\n\n"
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if not body:
        return []
    if len(prefix) + len(body) <= CHUNK_TARGET:
        return [prefix + body]
    chunks, buf = [], ""
    for para in re.split(r"\n\s*\n", body):
        if len(buf) + len(para) + 2 > CHUNK_TARGET and buf:
            chunks.append(prefix + buf.strip())
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
        while len(buf) > CHUNK_MAX:  # parágrafo gigante: corte duro
            chunks.append(prefix + buf[:CHUNK_TARGET])
            buf = buf[CHUNK_TARGET:]
    if buf.strip():
        chunks.append(prefix + buf.strip())
    return chunks


async def main_async(args) -> int:
    from mcp_memory_service.models.memory import Memory
    from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage

    sha = git(args.repo, "rev-parse", args.ref).strip()
    paths = list_docs(args.repo, args.ref)
    print(f"ref {args.ref} = {sha[:12]} · {len(paths)} arquivos markdown", flush=True)

    out = Path(os.path.expanduser(args.out))
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not args.force:
        print(f"erro: {out} já existe (use --force para recriar)", file=sys.stderr)
        return 2
    if out.exists():
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(out) + suffix)
            if p.exists():
                p.unlink()

    storage = SqliteVecMemoryStorage(str(out), embedding_model=args.model)
    await storage.initialize()
    print(f"storage pronto: {out} · modelo {args.model}", flush=True)

    stored = skipped_lang = 0
    per_file: dict[str, int] = {}
    for path in paths:
        try:
            md = git(args.repo, "show", f"{args.ref}:{path}")
        except subprocess.CalledProcessError:
            continue
        title, sections = split_sections(md)
        title = title or Path(path).stem
        file_chunks = []
        for head, body in sections:
            if not is_english(f"{head}\n{body}"):
                continue
            file_chunks.extend(chunk_section(title, head, body))
        if not file_chunks:
            skipped_lang += 1
            continue
        for i, content in enumerate(file_chunks):
            mem = Memory(
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                tags=["bench", "upstream-doc", f"path:{path}"],
                memory_type="document",
                metadata={
                    "source_repo": "doobidoo/mcp-memory-service",
                    "source_ref": args.ref,
                    "source_sha": sha,
                    "source_path": path,
                    "chunk_index": i,
                    "corpus": "bench-upstream-v1",
                },
            )
            ok, _msg = await storage.store(mem, store="bench")
            stored += 1 if ok else 0
        per_file[path] = len(file_chunks)
        if len(per_file) % 40 == 0:
            print(f"  {len(per_file)} arquivos · {stored} memórias", flush=True)

    health = await storage.get_stats() if hasattr(storage, "get_stats") else {}
    await storage.close()
    summary = {
        "db": str(out),
        "model": args.model,
        "ref": args.ref,
        "sha": sha,
        "files": len(per_file),
        "files_skipped_not_english": skipped_lang,
        "memories_stored": stored,
        "stats": health if isinstance(health, dict) else str(health),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.expanduser("~/git/mcp-memory-service"))
    ap.add_argument("--ref", default="upstream/main")
    ap.add_argument("--out", default=os.path.expanduser("~/local-data/mcp/bench/bench-upstream.db"))
    ap.add_argument("--model", default="all-MiniLM-L6-v2")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
