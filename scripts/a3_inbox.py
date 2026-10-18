"""Inbox inter-agente sobre o mms — A3 (Alice) v1.

Implementa o essencial da RFC `rfc-inter-agent-inbox.md` para o runtime do Hermes:
mensagem endereçada em três níveis (host / agente / sessão), entregue por gatilho do
lado do servidor (o hook `pre_llm_call` roda a cada turno), sem depender da disciplina
do agente.

Mensagens são memórias no store `inbox` do acervo, com tags de endereçamento e um
`msg_id` estável. O "lido" é um cursor local por agente — não marcamos a memória,
porque o mesmo store pode ser lido por agentes diferentes.

Uso:
    python scripts/a3_inbox.py send --to tpol@sirdata --body "texto" [--thread T]
    python scripts/a3_inbox.py list --agent tpol --host sirdata [--limit 10]
    python scripts/a3_inbox.py ack --agent tpol --upto <ts>
    python scripts/a3_inbox.py hook --agent tpol --host sirdata   # usado pelo hook
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import time
import urllib.request
from pathlib import Path

PORT = int(os.environ.get("A3_PORT", "3202"))
STORE = "inbox"
CURSOR_DIR = Path(os.environ.get("A3_CURSOR_DIR", str(Path.home() / ".hermes" / "a3")))


def mcp(name: str, arguments: dict, timeout: int = 15) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/mcp",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
    )
    raw = urllib.request.urlopen(req, timeout=timeout).read().decode()
    for line in raw.splitlines():
        if line.startswith("data: "):
            d = json.loads(line[6:])
            if "result" in d:
                return d["result"]
    return {}


def texto(result: dict) -> str:
    try:
        return result["content"][0]["text"]
    except (KeyError, IndexError):
        return ""


def send(para: str, corpo: str, de: str, thread: str | None) -> dict:
    agora = time.time()
    msg_id = hashlib.sha256(f"{de}|{para}|{agora}|{corpo}".encode()).hexdigest()[:16]
    alvo_agente, _, alvo_host = para.partition("@")
    thread = thread or hashlib.sha256(f"{de}|{para}".encode()).hexdigest()[:8]
    conteudo = (
        f"[A3] de={de} para={para} thread={thread} msg={msg_id} ts={agora:.0f}\n\n{corpo}"
    )
    tags = [
        "a3", "msg", f"thread:{thread}", f"msgid:{msg_id}", f"de:{de}",
        f"para:{para}", f"para_agente:{alvo_agente}", f"para_host:{alvo_host or socket.gethostname()}",
    ]
    r = mcp("memory_store", {"content": conteudo, "tags": tags,
                             "memory_type": "message", "store": STORE})
    return {"msg_id": msg_id, "thread": thread, "ok": "Memory stored" in texto(r) or "success" in texto(r)}


def _ler_cursor(agent: str) -> float:
    p = CURSOR_DIR / f"cursor-{agent}.json"
    if p.exists():
        try:
            return float(json.loads(p.read_text())["upto"])
        except Exception:
            return 0.0
    return 0.0


def _gravar_cursor(agent: str, upto: float) -> None:
    CURSOR_DIR.mkdir(parents=True, exist_ok=True)
    (CURSOR_DIR / f"cursor-{agent}.json").write_text(json.dumps({"upto": upto, "at": time.time()}))


def _mensagens(agent: str, host: str, limite: int) -> list[dict]:
    """Lê direto do SQLite do acervo — as tags do MCP não são confiáveis para endereço,
    e busca semântica traz ruído. Aqui o endereço está no cabeçalho da mensagem."""
    import sqlite3

    db = os.path.expanduser(os.environ.get("A3_DB", "~/local-data/mcp/sqlite_vec.db"))
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    try:
        rows = con.execute(
            "SELECT content, created_at FROM memories "
            "WHERE store = ? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
            (STORE, max(limite * 12, 120)),
        ).fetchall()
    finally:
        con.close()

    saida = []
    for content, _criado in rows:
        cab = (content or "").split("\n", 1)[0]
        if not cab.startswith("[A3]"):
            continue
        campos = dict(part.split("=", 1) for part in cab.split()[1:] if "=" in part)
        if campos.get("para", "").split("@")[0] != agent:
            continue
        if campos.get("para", "").split("@")[-1] not in (host, "", agent):
            continue
        try:
            ts = float(campos["ts"])
        except (KeyError, ValueError):
            continue
        corpo = (content or "").split("\n\n", 1)[-1].strip()
        saida.append({"ts": ts, "msg": campos.get("msg", ""), "thread": campos.get("thread", ""),
                      "de": campos.get("de", ""), "corpo": corpo[:800]})
    return sorted(saida, key=lambda m: m["ts"])


def listar(agent: str, host: str, limite: int) -> dict:
    upto = _ler_cursor(agent)
    msgs = [m for m in _mensagens(agent, host, limite) if m["ts"] > upto][:limite]
    return {"agent": agent, "host": host, "nao_lidas": len(msgs), "mensagens": msgs}


def hook(agent: str, host: str) -> int:
    """Saída para o hook pre_llm_call: injeta contexto ou não imprime nada."""
    try:
        d = listar(agent, host, limite=5)
    except Exception:
        return 0
    if not d["mensagens"]:
        return 0
    linhas = [f"[A3 INBOX] {d['nao_lidas']} mensagem(ns) de outro agente:"]
    for m in d["mensagens"]:
        linhas.append(f"- de {m['de']} (thread {m['thread']}, {m['msg']}): {m['corpo']}")
    print(json.dumps({"context": "\n".join(linhas)}, ensure_ascii=False))
    _gravar_cursor(agent, max(m["ts"] for m in d["mensagens"]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("send")
    s.add_argument("--to", required=True, help="agente@host")
    s.add_argument("--body", required=True)
    s.add_argument("--from", dest="de", default=f"tpol@{socket.gethostname()}")
    s.add_argument("--thread", default=None)

    l = sub.add_parser("list")
    l.add_argument("--agent", default="tpol")
    l.add_argument("--host", default=socket.gethostname())
    l.add_argument("--limit", type=int, default=10)

    a = sub.add_parser("ack")
    a.add_argument("--agent", default="tpol")
    a.add_argument("--upto", type=float, default=None)

    h = sub.add_parser("hook")
    h.add_argument("--agent", default="tpol")
    h.add_argument("--host", default=socket.gethostname())

    args = ap.parse_args()
    if args.cmd == "send":
        print(json.dumps(send(args.to, args.body, args.de, args.thread), ensure_ascii=False))
    elif args.cmd == "list":
        print(json.dumps(listar(args.agent, args.host, args.limit), ensure_ascii=False, indent=1))
    elif args.cmd == "ack":
        upto = args.upto or time.time()
        _gravar_cursor(args.agent, upto)
        print(json.dumps({"agent": args.agent, "cursor": upto}))
    elif args.cmd == "hook":
        return hook(args.agent, args.host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
