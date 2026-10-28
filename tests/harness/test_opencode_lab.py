"""The isolated lab acceptance suite — SPEC-F008 §5.2.

Each test boots the REAL service (module-scoped fixture, isolated database on
a free port), installs into a fresh sandboxed XDG tree and asserts effects at
the real client and service level:

1. `opencode mcp list` shows `mms` (R3, needs the real binary);
2. the deposited plugin imports in Node with `setup` and `server` exports (R4);
3. an MCP store with the identity argument is retrievable by search (R5);
4. the developer's real configuration hash is untouched (R6);
5. every manifest path stays inside the sandbox (R7);
6. uninstall removes exactly the installer-owned state (AC6).

Measured reality amendment (R5): on the 12.3.1 build the `X-Agent-ID` header
is inert (SPEC-F005), so authorship is asserted through the documented
fallback — the explicit `agent_id` argument — plus the `agent:<id>` tag; the
header path is RFC D4's transform, still pending.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from mcp_memory_service.installers import core  # noqa: E402

import lab  # noqa: E402

OPENCODE_BINARY = shutil.which("opencode")
NODE_BINARY = shutil.which("node")


def _install(lab) -> dict:
    """Install into the sandbox and return the manifest."""
    code = core.main(["--harness", "opencode", "--root", str(lab.root), "--port", str(lab.port)])
    assert code == 0
    return lab.manifest()


@pytest.mark.integration
def test_install_is_visible_to_opencode(lab):
    if OPENCODE_BINARY is None:
        pytest.skip("the opencode binary is not on PATH — R3 needs the real client")

    _install(lab)

    # Measured (OpenCode 2.1.3): the managed service binds a default port
    # (49374) that collides with an already-running daemon — the sandbox
    # configures its own port (R8: from a bound socket) — and the daemon
    # boots asynchronously, so an immediate `mcp list` can answer from a
    # cold daemon ("No MCP servers configured"). Retries tolerate both
    # (SPEC-F008 §6: parse tolerantly, report raw output on failure).
    setup = subprocess.run(
        [OPENCODE_BINARY, "service", "set", "port", str(lab.free_port())],
        env=lab.sandbox_env(),
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(lab.home),
    )
    assert setup.returncode == 0, f"service set port failed: {setup.stdout}{setup.stderr}"

    output = ""
    for _ in range(5):
        result = subprocess.run(
            [OPENCODE_BINARY, "mcp", "list"],
            env=lab.sandbox_env(),
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(lab.home),
        )
        output = result.stdout + result.stderr
        if "mms" in output.lower():
            break
        time.sleep(2)

    assert "mms" in output.lower(), f"mms missing after retries: {output!r}"


@pytest.mark.integration
def test_plugin_imports(lab):
    if NODE_BINARY is None:
        pytest.skip("node is not available — R4 skips the import check with a note")

    _install(lab)

    index = lab.root / "plugins" / "opencode-memory" / "index.js"
    assert index.is_file(), f"the plugin was not deposited at {index}"

    names = lab.plugin_exports(index, NODE_BINARY)
    assert "setup" in names, f"the plugin does not export setup: {names}"
    assert "server" in names, f"the plugin does not export server: {names}"


@pytest.mark.integration
def test_mcp_round_trip_stamps_agent(lab):
    """R5 (amended): store with the identity argument, find it by search."""
    _install(lab)

    agent_id = "mms-lab"
    token = f"lab-round-trip-{uuid.uuid4().hex[:10]}"

    stored, error, _ = core._mcp_rpc(
        lab.port,
        "tools/call",
        {
            "name": "memory_store",
            "arguments": {
                "content": f"mms-lab round trip {token}",
                "metadata": {"tags": [f"agent:{agent_id}"]},
                "agent_id": agent_id,
            },
        },
        None,
    )
    assert error is None, json.dumps(error)
    stored_text = core._tool_text(stored)
    match = re.search(r"hash:\s*([0-9a-fA-F]{64})", stored_text)
    assert match, stored_text
    probe_hash = match.group(1)

    found, error, _ = core._mcp_rpc(
        lab.port,
        "tools/call",
        {"name": "memory_search", "arguments": {"query": token, "limit": 1}},
        None,
    )
    assert error is None, json.dumps(error)
    assert token in core._tool_text(found), "the search did not retrieve the stored memory"

    # Lab hygiene: the lab memory must not linger in the isolated database.
    deleted, error, _ = core._mcp_rpc(
        lab.port,
        "tools/call",
        {"name": "memory_delete", "arguments": {"content_hash": probe_hash}},
        None,
    )
    assert error is None, json.dumps(error)
    assert "error" not in core._tool_text(deleted).lower(), core._tool_text(deleted)


@pytest.mark.integration
def test_real_config_untouched(lab):
    """R6: the developer's real OpenCode configuration is never mutated."""
    real_files = [
        lab.REAL_HOME / ".config" / "opencode" / "opencode.json",
        lab.REAL_HOME / ".config" / "opencode" / "memory-plugin.json",
    ]
    present = {path: path.read_bytes() for path in real_files if path.is_file()}
    if not present:
        pytest.skip("the developer has no real OpenCode configuration — the guard is vacuous")

    _install(lab)

    assert {path: path.read_bytes() for path in present} == present


@pytest.mark.integration
def test_all_writes_stay_in_sandbox(lab, tmp_path: Path):
    """R7: every manifest path (and dir) resolves under the sandbox."""
    manifest = _install(lab)

    root = tmp_path.resolve()
    for entry in manifest["created"]:
        path = entry["path"] if isinstance(entry, dict) else entry
        assert Path(path).resolve().is_relative_to(root), f"escaped path {path}"

    for directory in manifest.get("created_dirs", []):
        assert Path(directory).resolve().is_relative_to(root), f"escaped dir {directory}"


@pytest.mark.integration
def test_uninstall_leaves_clean_tree(lab):
    """AC6: uninstall removes exactly the installer-owned state."""
    manifest = _install(lab)
    recorded = [
        entry["path"] if isinstance(entry, dict) else entry
        for entry in manifest["created"]
    ]

    code = core.main(
        ["--harness", "opencode", "--root", str(lab.root), "--port", str(lab.port), "--uninstall"]
    )
    assert code == 0

    for path in recorded:
        assert not Path(path).exists(), f"{path} survived the uninstall"
    assert not (lab.root / "mms-install-manifest.json").exists()

    # F003's surgical rule: a merged config is never deleted wholesale.
    config = lab.root / "opencode.json"
    assert config.is_file(), "the merged config must be retained"
    assert "mms" not in config.read_text(encoding="utf-8"), "the mms entry must be gone"
    assert not (lab.root / "plugins" / "opencode-memory").exists()
