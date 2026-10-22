#!/usr/bin/env python3
"""EXP-1602 — orquestrador da bancada service-path.

Um ciclo = 1 config: cópia de trabalho do snapshot, instância efêmera do
feature-branch em porta livre (env base + override do host, na ordem do
systemd, com consolidação/harvest/agendas desligadas), 120 casos por HTTP
(/mcp, tools/call memory_search), kill, work-copy descartada.

Uso:
    python3 eval/run_service_rerank.py --config base   --port 3217 --out eval/lab_rerank_service_base.json
    python3 eval/run_service_rerank.py --config msmarco --port 3218 --out eval/lab_rerank_service_msmarco.json
    python3 eval/run_service_rerank.py --config bge    --port 3219 --out eval/lab_rerank_service_bge.json
    python3 eval/run_service_rerank.py --config failopen --port 3220 --out eval/lab_rerank_service_failopen.json \
        --probe-queries 10 --probe-baseline eval/lab_rerank_service_base.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # ~/git/mms/lab-recall
SESSAO2_SRC = os.path.expanduser("~/git/mms/sessao-2/src")
VENV_BIN = os.path.expanduser("~/git/mms/mms/.venv/bin")
ENV_DIR = os.path.expanduser("~/dtp/ai-configs/services/env")

SCHEDULE_KEYS = (
    "MCP_SCHEDULE_DAILY", "MCP_SCHEDULE_WEEKLY", "MCP_SCHEDULE_MONTHLY",
    "MCP_HARVEST_SCHEDULE", "MCP_SYNC_SCHEDULE", "MCP_QUALITY_RECOMPUTE_SCHEDULE",
    "MCP_IMPORTANCE_TRIGGER_ENABLED",
)


def load_env_file(path: str) -> dict:
    env = {}
    with open(os.path.expanduser(path)) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.split("  #")[0].strip()
    return env


def free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit("nenhuma porta livre")


def wait_health(port: int, timeout: float = 90.0) -> float:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
                if r.status == 200:
                    return time.monotonic() - started
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    raise SystemExit(f"serviço não respondeu em {timeout:.0f}s na porta {port}")


def effective_env(pid: int, keys: tuple) -> dict:
    try:
        with open(f"/proc/{pid}/environ", "rb") as fh:
            raw = fh.read()
    except FileNotFoundError:
        return {}
    environ = {}
    for item in raw.split(b"\0"):
        if b"=" in item:
            k, _, v = item.partition(b"=")
            environ[k.decode(errors="replace")] = v.decode(errors="replace")
    return {k: environ.get(k, "<unset>") for k in keys}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True,
                    choices=["base", "msmarco", "bge", "failopen"])
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--snapshot", default="/tmp/mms-snap-1602.db")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cases", default=os.path.join(REPO, "eval", "recall_cases_v3.json"))
    ap.add_argument("--dump", default="/tmp/cands40.json")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--probe-queries", type=int, default=0)
    ap.add_argument("--probe-baseline", default="")
    args = ap.parse_args()

    cfg = args.config
    rerank_on = cfg in ("msmarco", "bge", "failopen")
    model = {
        "base": "",
        "msmarco": "Xenova/ms-marco-MiniLM-L-6-v2",
        "bge": "Xenova/bge-reranker-base",
        "failopen": "does-not-exist",
    }[cfg]
    candidates = 40

    port = free_port(args.port)
    work_db = f"/tmp/work-1602-{cfg}-{port}.db"
    shutil.copy2(args.snapshot, work_db)

    # env base + override do host, na ordem em que o systemd carrega
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": SESSAO2_SRC,
        "MCP_MEMORY_STORAGE_BACKEND": "sqlite_vec",
        "MCP_MEMORY_USE_ONNX": "1",
        "MCP_EMBEDDING_MODEL": "paraphrase-multilingual-MiniLM-L12-v2",
        "MCP_EMBEDDING_DIMENSIONS": "384",
        "MCP_SSE_HOST": "127.0.0.1",
        "MCP_STREAMABLE_HTTP_MODE": "1",
    }
    env.update(load_env_file(os.path.join(ENV_DIR, "memory-service.env")))
    env.update(load_env_file(os.path.join(ENV_DIR, "memory-service.DNBSCDC289.env")))
    env["MCP_MEMORY_SQLITE_PATH"] = work_db
    env["MCP_SSE_PORT"] = str(port)
    for key in SCHEDULE_KEYS:
        env.pop(key, None)
    env["MCP_CONSOLIDATION_ENABLED"] = "false"
    env["MCP_HARVEST_TRIAGE"] = "0"
    if rerank_on:
        env["MCP_RERANK_ENABLED"] = "true"
        env["MCP_RERANK_CANDIDATES"] = str(candidates)
        env["MCP_RERANK_MODEL"] = model
    else:
        env.pop("MCP_RERANK_ENABLED", None)
        env.pop("MCP_RERANK_MODEL", None)
        env.pop("MCP_RERANK_CANDIDATES", None)

    log_path = f"/tmp/mmssvc-1602-{cfg}.log"
    started = time.monotonic()
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            [os.path.join(VENV_BIN, "memory-server")],
            env=env, stdout=log, stderr=subprocess.STDOUT,
            cwd=SESSAO2_SRC, start_new_session=True,
        )
    startup = wait_health(port)

    bench_env = dict(os.environ)
    bench_env.update({
        k: env[k] for k in ("MCP_RERANK_ENABLED", "MCP_RERANK_MODEL", "MCP_RERANK_CANDIDATES")
        if k in env
    })
    cmd = [
        sys.executable,
        os.path.join(REPO, "eval", "service_rerank_bench.py"),
        "--port", str(port),
        "--pid", str(proc.pid),
        "--cases", args.cases,
        "--dump", args.dump,
        "--limit", str(args.limit),
        "--rerank", "on" if rerank_on else "off",
        "--out", args.out,
    ]
    if args.probe_queries:
        cmd += ["--probe-queries", str(args.probe_queries)]
    if args.probe_baseline:
        cmd += ["--probe-baseline", args.probe_baseline]

    bench = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, cwd=REPO,
                           env=bench_env)
    if bench.returncode != 0:
        print(bench.stdout[-2000:])
        print(bench.stderr[-2000:])
        raise SystemExit(f"bench falhou ({cfg}): exit {bench.returncode}")

    effective = effective_env(proc.pid, (
        "MCP_MEMORY_SQLITE_PATH", "MCP_SSE_PORT", "MCP_RERANK_ENABLED",
        "MCP_RERANK_MODEL", "MCP_RERANK_CANDIDATES", "MCP_CONSOLIDATION_ENABLED",
        "MCP_HARVEST_SCHEDULE", "MCP_SYNC_SCHEDULE",
    ))

    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait(timeout=15)
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(work_db + suffix)
        except FileNotFoundError:
            pass

    summary = {
        "config": cfg,
        "rerank": rerank_on,
        "model": model,
        "candidates": candidates,
        "port": port,
        "startup_s": round(startup, 2),
        "effective_env": effective,
        "artifact": args.out,
        "server_log": log_path,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
