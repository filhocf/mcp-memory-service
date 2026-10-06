"""
RED tests for server-side hostname stamping on the MCP store path.

Spec: docs/rfc/planned/rfc-mcp-hostname-stamping.md

Problem: MCP_MEMORY_INCLUDE_HOSTNAME is honored ONLY by the Web API
(web/api/memories.py). The MCP store handler reads client_hostname only from the
client argument; it never resolves socket.gethostname() nor consults the flag.
So memories stored via MCP (how Kiro writes) carry no host.

Requirements (RFC §3):
- R1: flag ON + no client_hostname → handler resolves socket.gethostname().
- R2: explicit client_hostname wins over server resolution.
- R3: flag OFF → no hostname (unchanged).
- R4: resolved host persisted in metadata.hostname + source:{host} tag.
- R5: gethostname() failure → store still succeeds, no host (best-effort).

These target handle_store_memory, which does NOT resolve host yet → MUST fail RED.
"""

import os
import shutil
import tempfile

import pytest
import pytest_asyncio

try:
    import sqlite_vec  # noqa: F401
    SQLITE_VEC_AVAILABLE = True
except ImportError:
    SQLITE_VEC_AVAILABLE = False

if SQLITE_VEC_AVAILABLE:
    from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage
from mcp_memory_service.services.memory_service import MemoryService
from mcp_memory_service.server.handlers.memory import handle_store_memory

pytestmark = pytest.mark.skipif(
    not SQLITE_VEC_AVAILABLE, reason="sqlite-vec not available"
)


class _Server:
    """Minimal stand-in for the MCP server object handle_store_memory expects."""
    def __init__(self, storage):
        self.storage = storage
        self.memory_service = MemoryService(storage)

    async def _ensure_storage_initialized(self):
        return self.storage


@pytest_asyncio.fixture
async def server():
    temp_dir = tempfile.mkdtemp()
    storage = SqliteVecMemoryStorage(os.path.join(temp_dir, "host.db"))
    await storage.initialize()
    try:
        yield _Server(storage)
    finally:
        try:
            await storage.close()
        except Exception:
            pass
        shutil.rmtree(temp_dir, ignore_errors=True)


async def _fetch_latest(storage, content):
    from mcp_memory_service.utils.hashing import generate_content_hash
    return await storage.get_by_hash(generate_content_hash(content))


@pytest.mark.asyncio
async def test_flag_on_resolves_server_hostname(server, monkeypatch):
    """R1: flag ON + no client_hostname → metadata.hostname = socket.gethostname()."""
    import socket
    monkeypatch.setenv("MCP_MEMORY_INCLUDE_HOSTNAME", "true")
    # Config reads the env at import; patch the module-level flag too.
    monkeypatch.setattr("mcp_memory_service.config.INCLUDE_HOSTNAME", True, raising=False)
    monkeypatch.setattr(
        "mcp_memory_service.server.handlers.memory.INCLUDE_HOSTNAME", True, raising=False
    )
    content = "host stamping flag on test"
    await handle_store_memory(server, {"content": content})
    stored = await _fetch_latest(server.storage, content)
    assert stored is not None
    assert (stored.metadata or {}).get("hostname") == socket.gethostname(), (
        f"flag ON must stamp server hostname, got {stored.metadata}"
    )


@pytest.mark.asyncio
async def test_explicit_client_hostname_wins(server, monkeypatch):
    """R2: explicit client_hostname is used unchanged even with flag ON."""
    monkeypatch.setattr(
        "mcp_memory_service.server.handlers.memory.INCLUDE_HOSTNAME", True, raising=False
    )
    content = "host stamping explicit wins test"
    await handle_store_memory(server, {"content": content, "client_hostname": "custom-host"})
    stored = await _fetch_latest(server.storage, content)
    assert (stored.metadata or {}).get("hostname") == "custom-host"


@pytest.mark.asyncio
async def test_flag_off_no_hostname(server, monkeypatch):
    """R3: flag OFF → no hostname (unchanged behavior)."""
    monkeypatch.setattr(
        "mcp_memory_service.server.handlers.memory.INCLUDE_HOSTNAME", False, raising=False
    )
    content = "host stamping flag off test"
    await handle_store_memory(server, {"content": content})
    stored = await _fetch_latest(server.storage, content)
    assert (stored.metadata or {}).get("hostname") is None, (
        f"flag OFF must not stamp host, got {stored.metadata}"
    )


@pytest.mark.asyncio
async def test_resolved_host_adds_source_tag(server, monkeypatch):
    """R4: resolved host also becomes a source:{host} tag."""
    import socket
    monkeypatch.setattr(
        "mcp_memory_service.server.handlers.memory.INCLUDE_HOSTNAME", True, raising=False
    )
    content = "host stamping source tag test"
    await handle_store_memory(server, {"content": content})
    stored = await _fetch_latest(server.storage, content)
    assert f"source:{socket.gethostname()}" in (stored.tags or []), (
        f"resolved host must add source tag, got {stored.tags}"
    )


@pytest.mark.asyncio
async def test_gethostname_failure_is_best_effort(server, monkeypatch):
    """R5: gethostname() raising → store still succeeds, no host."""
    monkeypatch.setattr(
        "mcp_memory_service.server.handlers.memory.INCLUDE_HOSTNAME", True, raising=False
    )

    def _boom():
        raise OSError("no hostname")

    monkeypatch.setattr("socket.gethostname", _boom)
    content = "host stamping best effort test"
    result = await handle_store_memory(server, {"content": content})
    # Store must not fail
    assert result and "Error storing memory" not in result[0].text
    stored = await _fetch_latest(server.storage, content)
    assert stored is not None
    assert (stored.metadata or {}).get("hostname") is None


@pytest.mark.asyncio
async def test_store_session_also_stamps_host(server, monkeypatch):
    """R1 (store_session): session stored via MCP also gets the server host.

    Closes the gap flagged in review (handle_store_session shared the same
    missing resolution as handle_store_memory).
    """
    import socket
    from mcp_memory_service.server.handlers.memory import handle_store_session
    monkeypatch.setattr(
        "mcp_memory_service.server.handlers.memory.INCLUDE_HOSTNAME", True, raising=False
    )
    result = await handle_store_session(
        server,
        {"turns": [{"role": "user", "content": "hello host"},
                   {"role": "assistant", "content": "hi from the session path"}]},
    )
    assert result and "Error" not in result[0].text
    # Find the session memory and assert host stamped
    import sqlite3, json
    rows = server.storage.conn.execute(
        "SELECT metadata FROM memories WHERE memory_type='session'"
    ).fetchall()
    assert rows, "a session memory should have been stored"
    assert any(
        (json.loads(r[0]) if r[0] else {}).get("hostname") == socket.gethostname()
        for r in rows
    ), "session memory must carry the server hostname"


@pytest.mark.asyncio
async def test_empty_client_hostname_resolves_server(server, monkeypatch):
    """Edge case: client_hostname='' is treated as absent → server resolves."""
    import socket
    monkeypatch.setattr(
        "mcp_memory_service.server.handlers.memory.INCLUDE_HOSTNAME", True, raising=False
    )
    content = "host stamping empty client hostname test"
    await handle_store_memory(server, {"content": content, "client_hostname": ""})
    stored = await _fetch_latest(server.storage, content)
    assert (stored.metadata or {}).get("hostname") == socket.gethostname()

