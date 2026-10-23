#!/usr/bin/env python3
"""EXP-1602 — service-path reranker bench (spec G0, 98421f84). Medição por HTTP do caminho real do serviço.

Régua: eval/recall_case
s_v3.json (120 casos, documento-level, gold_hashes).
Dump congelado: /tmp/cands40.json (sha256 gravado na saída).
Come (harness offline) ver eval/onnx_rerank.py. Aqui: nada de caminho offline —
tudo via memory_search (MCP streamable HTTP, /mcp) na instância efêmera.

Uso:
    python eval/service_rerank_bench.py --port 3217 --pid <pid> \
        --cases eval/recall_cases_v3.json --dump /tmp/cands40.json \
        --out eval/lab_rerank_service_base.json \
        [--fail-open-model does-not-exist] [--probe-queries 10]

Config A (base): rerank off  -> env MCP_RERANK_ENABLED unset + sem rerank na chamada.
Config B/C: env MCP_RERANK_ENABLED=true + model; recusado per-call com rerank=true.
Probe fail-open: env MCP_RERANK_ENABLED=true + MCP_RERANK_MODEL=does-not-exist ->
    baseline order (igual config A), 200, um warning, sem erro.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HASH_RE = re.compile(r"Hash: ([0-9a-f]{64})")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def call_search(port: int, arguments: dict, timeout: float = 90.0):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "memory_search", "arguments": arguments},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    t0 = time.time()
    raw = urllib.request.urlopen(req, timeout=timeout).read().decode()
    elapsed = (time.time() - t0) * 1000.0
    text = ""
    for line in raw.splitlines():
        if line.startswith("data: "):
            try:
                body = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if "result" in body:
                content = body["result"].get("content") or []
                if content:
                    text = content[0].get("text") or ""
                    break
    return text, elapsed


def rss_of(pid: int, field: str) -> int:
    """field: 'VmRSS' or 'VmHWM' -> KB."""
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith(field + ":"):
                    return int(line.split()[1])
    except FileNotFoundError:
        return -1
    return -1


def loadavg() -> dict:
    la1, la5, la15 = os.getloadavg()
    return {"l1": round(la1, 2), "l5": round(la5, 2), "l15": round(la15, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--cases", default="eval/recall_cases_v3.json")
    ap.add_argument("--dump", default="/tmp/cands40.json")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--rerank", choices=["off", "on"], required=True)
    ap.add_argument("--probe-queries", type=int, default=0,
                    help=">0: só roda N consultas (probe fail-open)")
    ap.add_argument("--probe-baseline", default="",
                    help="artifact JSON do config A p/ comparar ordem (probe)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cases = json.load(open(args.cases))["cases"]
    dump = json.load(open(args.dump))
    baseline: dict = {}
    if args.probe_baseline and os.path.exists(args.probe_baseline):
        for entry in json.load(open(args.probe_baseline))["detail"]:
            baseline[entry["id"]] = entry["ranques"]

    rerank_arg = {"rerank": True} if args.rerank == "on" else {}
    remaining = cases if args.probe_queries == 0 else cases[: args.probe_queries]

    detail, lat = [], []
    rss_start = rss_of(args.pid, "VmRSS")
    load_start = loadavg()
    t_run0 = time.time()
    for c in remaining:
        arguments = {
            "query": c["pergunta"],
            "mode": "semantic",
            "limit": args.limit,
        }
        arguments.update(rerank_arg)
        text = ""
        ms = None
        erro = None
        for attempt in (1, 2):
            try:
                text, ms = call_search(args.port, arguments)
                erro = None
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                erro = f"{type(exc).__name__}: {exc}"
                if attempt == 2:
                    text = ""
        hashes = HASH_RE.findall(text) if text else []
        pos = hashes.index(c["gold_hashes"][0]) + 1 if c["gold_hashes"][0] in hashes else None
        detail.append({
            "id": c["id"],
            "pos_gold": pos,
            "ranques": hashes,
            "lat_ms": round(ms, 1) if ms is not None else None,
            "round": 3 if erro else 0,
            "erro": erro,
        })
        lat.append(ms or 0.0)
    t_run1 = time.time()
    load_end = loadavg()
    rss_end = rss_of(args.pid, "VmRSS")

    k_values = (5, 10, 30)
    pos_list = [d["pos_gold"] for d in detail]
    recall_d = {f"documento@{k}": round(sum(1 for p in pos_list if p and p <= k) / len(pos_list), 4) for k in k_values}
    sorted_lat = sorted(lat)
    p50 = statistics.median(sorted_lat)
    p95 = statistics.quantiles(sorted_lat, n=100, method="inclusive")[94] if len(sorted_lat) > 1 else sorted_lat[0]

    order_match_probe = None
    if args.probe_baseline and baseline:
        match = all(
            d["id"] not in baseline or d["ranques"] == baseline[d["id"]]
            for d in detail
        )
        order_match_probe = match

    report = {
        "meta": {
            "commit": subprocess.run(
                ["git", "-C", os.path.dirname(os.path.dirname(os.path.abspath(args.cases))), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True,
            ).stdout.strip() if os.path.isdir(os.path.dirname(os.path.dirname(os.path.abspath(args.cases)))) else None,
            "dump": args.dump,
            "dump_sha256": sha256_file(args.dump),
            "casos": len(detail),
            "limit": args.limit,
            "rerank_flag": args.rerank,
            "ran_at": datetime.now(timezone.utc).isoformat(),
        },
        "env": {
            "rerank_enabled": os.getenv("MCP_RERANK_ENABLED"),
            "model": os.getenv("MCP_RERANK_MODEL"),
            "candidates": os.getenv("MCP_RERANK_CANDIDATES"),
            "max_length": os.getenv("MCP_RERANK_MAX_LENGTH"),
        },
        "recall": recall_d,
        "latency": {
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
        },
        "rss": {
            "start_kb": rss_start,
            "end_kb": rss_end,
            "peak_hwm_kb": rss_of(args.pid, "VmHWM"),
        },
        "machine_load": {
            "start": load_start,
            "end": load_end,
            "note": "serial, machine solo - one ephemeral instance at a time",
        },
        "detail": detail,
    }
    if order_match_probe is not None:
        report["fail_open"] = {"order_match": order_match_probe}
    payload = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        tmp = args.out + ".tmp"
        with open(tmp, "w") as fh:
            fh.write(payload + "\n")
        os.replace(tmp, args.out)
        print(f"== gravado em {args.out}")
    print(json.dumps({k: v for k, v in report.items() if k != "detail"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
