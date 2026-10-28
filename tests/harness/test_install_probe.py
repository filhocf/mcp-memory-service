"""RED tests for SPEC-F011 — the installation proof probe.

Verification of config effect is not verification of the data path: a service
can pass /health and still refuse writes (401), search nothing (broken
embeddings), or sit on a read-only database. The installer must prove the write
path — store a uniquely tagged probe, read it back, delete it — before reporting
success, and must do so on an idempotent rerun too (RFC §13.2).

A FakeMMS (http.server in a thread, JSON-RPC routed by tool, request log)
exercises the real wiring over HTTP; nothing touches the network or $HOME.
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from mcp_memory_service.installers import core  # noqa: E402


class FakeMMS:
    """Scripted MCP service: /health 200, /mcp JSON-RPC routed by tool."""

    def __init__(self, *, search_text: str | None = None, delete_ok: bool = True):
        self.search_text = search_text
        self.delete_ok = delete_ok
        self.requests: list[tuple[str, dict]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self.port = self._server.server_address[1]

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler(self):
        lab = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                message = json.loads(self.rfile.read(length).decode())
                lab.requests.append((self.path, message))
                data = json.dumps(
                    {"jsonrpc": "2.0", "id": 1, "result": lab._result(message)}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                data = b"{}"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        return Handler

    def _result(self, message: dict) -> dict:
        method = message.get("method", "")
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mcp-memory-service", "version": "12.3.1"},
            }
        if method == "tools/call":
            name = message["params"]["name"]
            arguments = message["params"]["arguments"]
            if name == "memory_store":
                token = arguments["content"].removeprefix("install probe ")
                digest = hashlib.sha256(token.encode()).hexdigest()
                text = f"Memory stored successfully (hash: {digest})"
            elif name == "memory_search":
                token = arguments.get("query", "")
                if self.search_text is not None:
                    text = self.search_text
                else:
                    digest = hashlib.sha256(token.encode()).hexdigest()
                    text = (
                        f"Found 1 memories (mode: semantic) for query: '{token}'"
                        f"\n\n=== Memory 1 ===\n... content ... {token} ...\n"
                        f"Hash: {digest}"
                    )
            elif name == "memory_delete":
                if self.delete_ok:
                    text = f"Successfully deleted memory {arguments['content_hash']}\n\nDeleted 1 memories"
                else:
                    text = "Error: could not delete the memory"
            else:
                text = f"unexpected tool {name}"
            return {"content": [{"type": "text", "text": text}]}
        return {}

    # -- request log helpers ------------------------------------------------

    def tool_calls(self, tool: str) -> list[dict]:
        calls = [
            message["params"]["arguments"]
            for path, message in self.requests
            if path == "/mcp"
            and message.get("method") == "tools/call"
            and message["params"]["name"] == tool
        ]
        return calls

    @property
    def mcp_count(self) -> int:
        return sum(1 for path, _ in self.requests if path == "/mcp")


@pytest.fixture
def lab():
    server = FakeMMS()
    server.start()
    yield server
    server.stop()


def _install(port: int, root: Path, *extra: str) -> int:
    return core.main(
        ["--harness", "opencode", "--root", str(root), "--port", str(port), *extra]
    )


# --- R1/R2/R3: install proves the write path ---------------------------------


def test_install_probes_the_write_path(lab, tmp_path, capsys):
    rc = _install(lab.port, tmp_path / "opencode")
    out = capsys.readouterr().out

    assert rc == 0
    assert "probe:" in out, f"no probe report:\n{out}"
    stored = lab.tool_calls("memory_store")
    assert len(stored) == 1, "the probe must be exactly one store per run"
    content = stored[0]["content"]
    assert content.startswith("install probe "), content
    token = content.removeprefix("install probe ")
    assert len(token) > 8 and token.startswith("probe-"), "the token must be unique per run"
    metadata = stored[0].get("metadata", {})
    assert "mms-install-probe" in json.dumps(metadata)
    searched = lab.tool_calls("memory_search")
    assert searched and searched[0]["query"] == token, "the search must look for THIS run's token"
    deleted = lab.tool_calls("memory_delete")
    assert deleted and deleted[0]["content_hash"], "the probe must be deleted by hash"


# --- R3: a service that stores but does not retrieve fails the install --------


def test_probe_failure_blocks_success(lab, tmp_path, capfd):
    lab.search_text = "No memories found for the query"

    rc = _install(lab.port, tmp_path / "opencode")
    captured = capfd.readouterr()

    assert rc == 1
    assert "OK:" not in captured.out, "a failed probe must not report success"
    assert "retrieving" in captured.err + captured.out


# --- R4: a failed delete is loud ----------------------------------------------


def test_failed_delete_prints_the_probe_hash(lab, tmp_path, capfd):
    rc = _install(lab.port, tmp_path / "opencode")
    assert rc == 0  # the failure is injected only for the rerun below
    capfd.readouterr()
    lab.delete_ok = False

    rc = _install(lab.port, tmp_path / "opencode")
    captured = capfd.readouterr()

    # The rerun's probe is the LAST store call; the first run's probe
    # succeeded and was deleted.
    token = lab.tool_calls("memory_store")[-1]["content"].removeprefix("install probe ")
    probe_hash = hashlib.sha256(token.encode()).hexdigest()

    assert rc == 1
    assert probe_hash in captured.err + captured.out, "the orphan probe hash must be printed"


# --- R5: an idempotent rerun still probes -------------------------------------


def test_rerun_is_a_no_op_but_still_probes(lab, tmp_path, capsys):
    root = tmp_path / "opencode"
    assert _install(lab.port, root) == 0
    first_count = lab.mcp_count
    capsys.readouterr()

    rc = _install(lab.port, root)
    out = capsys.readouterr().out

    assert rc == 0
    assert "nothing to do" in out
    assert "probe:" in out, "the rerun must still prove the round trip"
    assert lab.mcp_count > first_count


# --- R6: the probe is not recorded in the manifest -----------------------------


def test_probe_is_not_recorded_in_the_manifest(lab, tmp_path):
    root = tmp_path / "opencode"
    assert _install(lab.port, root) == 0

    manifest = json.loads((root / "mms-install-manifest.json").read_text(encoding="utf-8"))
    # The deposited paths embed the tmp root, whose own name contains "probe"
    # here; compare against the manifest with that path stripped out.
    body = json.dumps(manifest).lower().replace(str(root).lower(), "")
    assert "probe" not in body


# --- R7: --skip-health skips the probe and says so -----------------------------


def test_skip_health_skips_the_probe(lab, tmp_path, capsys):
    rc = _install(lab.port, tmp_path / "opencode", "--skip-health")
    out = capsys.readouterr().out

    assert rc == 0
    assert lab.mcp_count == 0, "--skip-health must not talk to /mcp"
    assert "probe" in out, "the skip must be reported"
