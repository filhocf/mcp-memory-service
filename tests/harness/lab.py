"""The isolated acceptance lab (SPEC-F008).

The lab proves the integration against a REAL service instance, not a scripted
double: an mms server is booted from the working tree on a free loopback port
with its database inside the test tree, and the lab waits for `/api/health`
(the `server --http` dashboard route; `/health` is retried as fallback).
OpenCode reads only the sandboxed XDG tree, and a SHA-256 guard proves the
developer's real configuration was not touched.

Three measured corrections to the spec's first draft, recorded here so the
next session does not rediscover them:

- The database-isolation variable is `MCP_MEMORY_SQLITE_PATH`;
  `MCP_MEMORY_DB_PATH` is the typo the service now rejects (storage.py warns
  on it explicitly).
- The `server` command takes `--http-host/--http-port`, not `--port`.
- The package has no `__main__.py`, so the service is booted through
  `cli.main:main` via `-c` with `PYTHONPATH` pinned to this working tree.

Rollback: delete this file, its conftest and its tests; no production code
depends on the lab.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Captured at import time — before any lab fixture monkeypatches HOME — so the
# R6 guard compares against the developer's genuine configuration files.
REAL_HOME = Path.home()


@dataclass
class Lab:
    """One sandboxed XDG tree, pointed at the shared real service port."""

    REAL_HOME = REAL_HOME

    home: Path
    config_home: Path
    data_home: Path
    state_home: Path
    root: Path  # the OpenCode surface root handed to the installer as --root
    port: int
    env: dict[str, str] = field(default_factory=dict)

    def free_port(self) -> int:
        """R8: the port comes from a bound socket, never hardcoded."""
        return free_port()

    def manifest(self) -> dict:
        from mcp_memory_service.installers.core import MANIFEST_NAME

        return json.loads((self.root / MANIFEST_NAME).read_text(encoding="utf-8"))

    def sandbox_env(self) -> dict[str, str]:
        """R1: subprocesses read the sandboxed user tree."""
        sandbox = dict(os.environ)
        sandbox.update(
            {
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.config_home),
                "XDG_DATA_HOME": str(self.data_home),
                "XDG_STATE_HOME": str(self.state_home),
            }
        )
        return sandbox

    def plugin_exports(self, plugin_path: Path, node: str) -> list[str]:
        """R4: import the deposited plugin in Node and report its exports."""
        script = (
            "(async () => {"
            " const mod = await import('file://' + process.argv[1]);"
            " const names = Object.keys(mod).concat(mod.default ? Object.keys(mod.default) : []);"
            " console.log(JSON.stringify(names));"
            "})().catch(e => { console.error(String(e)); process.exit(1); })"
        )
        result = subprocess.run(
            [node, "-e", script, str(plugin_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"plugin import failed: {result.stdout}{result.stderr}")
        return json.loads(result.stdout.strip().splitlines()[-1])


@dataclass
class ServiceHandle:
    process: subprocess.Popen
    port: int
    db_path: Path
    log_path: Path
    health_route: str


def free_port() -> int:
    """R8: the port comes from a bound socket, never hardcoded."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def spawn_service(port: int, db_path: Path, log_path: Path) -> subprocess.Popen:
    """Boot the real service from the working tree on <port>, DB isolated."""
    env = os.environ | {
        "MCP_ALLOW_ANONYMOUS_ACCESS": "true",
        "MCP_MEMORY_SQLITE_PATH": str(db_path),
        "MCP_HTTP_HOST": "127.0.0.1",
        "MCP_HTTP_PORT": str(port),
        "PYTHONPATH": str(REPO_ROOT / "src"),
    }
    argv = [
        sys.executable,
        "-c",
        "from mcp_memory_service.cli.main import main; main()",
        "server",
        "--http",
        "--http-host",
        "127.0.0.1",
        "--http-port",
        str(port),
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_file:
        return subprocess.Popen(
            argv,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )


def wait_for_health(port: int, timeout: float = 90.0) -> str:
    """R2: wait for the service before installing.

    Polls `/api/health` (the `server --http` dashboard route) with `/health`
    as fallback — the service answers health on different routes depending on
    the mode, which is the measured behaviour behind the installer's own
    retry.
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        for route in ("/api/health", "/health"):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{route}", timeout=2) as resp:
                    if resp.status == 200:
                        return route
            except Exception as exc:  # noqa: BLE001 — poll-tolerant by design
                last_error = exc
        time.sleep(0.5)
    raise RuntimeError(
        f"service did not answer health on :{port} within {timeout:.0f}s ({last_error})"
    )


def boot_service(base_dir: Path, attempts: int = 3) -> ServiceHandle:
    """R8 + §6 edge: retry the whole boot when the port is snatched."""
    last_error: Exception | None = None
    for _ in range(attempts):
        process = None
        port = free_port()
        db_path = base_dir / f"memory-{port}.db"
        log_path = base_dir / f"service-{port}.log"
        try:
            process = spawn_service(port, db_path, log_path)
            route = wait_for_health(port)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    process.kill()
            continue
        return ServiceHandle(process, port, db_path, log_path, route)
    raise RuntimeError(f"could not boot the lab service after {attempts} attempts: {last_error}")
