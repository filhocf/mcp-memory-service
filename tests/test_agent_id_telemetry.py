"""
RED tests for agent_id on the telemetry hot path (retrieve / feedback / injection).

Context: ADR-0006 — the passive quality recompute (L4) ships dormant because
agent_id is None on retrieve(), so usage_events from different sessions fall into
one bucket and reaccess(+)/retry_failed(-) contaminate each other cross-session.
derive_signals ALREADY partitions by agent_id (treats None as its own bucket);
the only missing link is the call sites writing agent_id into usage_events.

RFC #1100 precedence (reused): explicit arg > MCP_AGENT_ID env > metadata > null.
On the telemetry read path there is no explicit arg nor reader-metadata, so the
source is MCP_AGENT_ID (env). null (unset env) must stay a valid no-op bucket.

Each test maps to a requirement:
- REQ-A1: retrieval event persists agent_id from MCP_AGENT_ID.
- REQ-A2: feedback event persists agent_id from MCP_AGENT_ID.
- REQ-A3: injection event persists agent_id from MCP_AGENT_ID.
- REQ-A4: unset MCP_AGENT_ID => agent_id stays NULL (graceful, unchanged).
- REQ-A5: anti-contamination — two agents reading the same hash do NOT create
  cross-agent reaccess/retry signals (buckets stay separate).

These target production code that does NOT pass agent_id yet and MUST fail RED.
"""

import os
import json
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

pytestmark = pytest.mark.skipif(
    not SQLITE_VEC_AVAILABLE, reason="sqlite-vec not available"
)


@pytest_asyncio.fixture
async def storage(monkeypatch):
    """Real sqlite-vec storage in a tmp dir, telemetry ON."""
    monkeypatch.setenv("MCP_USAGE_TELEMETRY", "true")
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_agent_id_telemetry.db")
    store = SqliteVecMemoryStorage(db_path)
    await store.initialize()
    try:
        yield store
    finally:
        try:
            store.close()
        except Exception:
            pass
        shutil.rmtree(temp_dir, ignore_errors=True)


def _agent_ids_for(storage, event_type):
    cur = storage.conn.execute(
        "SELECT agent_id FROM usage_events WHERE event_type = ?", (event_type,)
    )
    return [row[0] for row in cur.fetchall()]


@pytest.mark.asyncio
async def test_retrieval_event_persists_agent_id(storage, monkeypatch):
    """REQ-A1: a retrieval telemetry event carries agent_id from MCP_AGENT_ID."""
    monkeypatch.setenv("MCP_AGENT_ID", "zero")
    from mcp_memory_service.models.memory import Memory
    from mcp_memory_service.utils.hashing import generate_content_hash

    content = "Agent-id telemetry retrieval test memory about async patterns"
    mem = Memory(content=content, content_hash=generate_content_hash(content),
                 tags=["test"], memory_type="note")
    await storage.store(mem)

    await storage.retrieve("async patterns", n_results=3)

    agent_ids = _agent_ids_for(storage, "retrieval")
    assert agent_ids, "a retrieval event should have been written"
    assert all(a == "zero" for a in agent_ids), (
        f"retrieval events must carry agent_id='zero', got {agent_ids}"
    )


@pytest.mark.asyncio
async def test_feedback_event_persists_agent_id(storage, monkeypatch):
    """REQ-A2: a feedback telemetry event carries agent_id from MCP_AGENT_ID."""
    monkeypatch.setenv("MCP_AGENT_ID", "zero")
    await storage.record_feedback_event(
        content_hash="abc123", rating=1, source="explicit"
    )
    agent_ids = _agent_ids_for(storage, "feedback")
    assert agent_ids, "a feedback event should have been written"
    assert all(a == "zero" for a in agent_ids), (
        f"feedback events must carry agent_id='zero', got {agent_ids}"
    )


@pytest.mark.asyncio
async def test_injection_event_persists_agent_id(storage, monkeypatch):
    """REQ-A3: an injection telemetry event carries agent_id from MCP_AGENT_ID."""
    monkeypatch.setenv("MCP_AGENT_ID", "zero")
    monkeypatch.setenv("MCP_CONTEXT_INJECTION_ENABLED", "true")
    from mcp_memory_service.storage import context_injection

    await context_injection.memory_context(storage, task="anything")

    agent_ids = _agent_ids_for(storage, "injection")
    assert agent_ids, "an injection event should have been written"
    assert all(a == "zero" for a in agent_ids), (
        f"injection events must carry agent_id='zero', got {agent_ids}"
    )


@pytest.mark.asyncio
async def test_unset_env_keeps_agent_id_null(storage, monkeypatch):
    """REQ-A4: unset MCP_AGENT_ID => agent_id NULL (graceful, unchanged)."""
    monkeypatch.delenv("MCP_AGENT_ID", raising=False)
    from mcp_memory_service.models.memory import Memory
    from mcp_memory_service.utils.hashing import generate_content_hash

    content = "No-agent telemetry memory about database indexes"
    mem = Memory(content=content, content_hash=generate_content_hash(content),
                 tags=["test"], memory_type="note")
    await storage.store(mem)
    await storage.retrieve("database indexes", n_results=3)

    agent_ids = _agent_ids_for(storage, "retrieval")
    assert agent_ids, "a retrieval event should still be written"
    assert all(a is None for a in agent_ids), (
        f"with MCP_AGENT_ID unset, agent_id must be NULL, got {agent_ids}"
    )


@pytest.mark.asyncio
async def test_two_agents_do_not_cross_contaminate(storage, monkeypatch):
    """REQ-A5: two agents retrieving the same hash keep separate buckets.

    With agent_id written per event, derive_signals partitions by agent, so a
    read by agent 'alpha' and a read by agent 'beta' of the SAME hash must not
    be counted as a reaccess of each other (that was the ADR-0006 contamination).
    """
    from mcp_memory_service.models.memory import Memory
    from mcp_memory_service.utils.hashing import generate_content_hash
    from mcp_memory_service.storage.usage_telemetry import derive_signals

    content = "Shared memory read by two different agents in two sessions"
    h = generate_content_hash(content)
    mem = Memory(content=content, content_hash=h, tags=["test"], memory_type="note")
    await storage.store(mem)

    # Agent alpha reads once; agent beta reads once. Same hash, different agents.
    monkeypatch.setenv("MCP_AGENT_ID", "alpha")
    await storage.retrieve("two different agents", n_results=3)
    monkeypatch.setenv("MCP_AGENT_ID", "beta")
    await storage.retrieve("two different agents", n_results=3)

    signals = await derive_signals(storage)
    # Each agent read the hash exactly once => no reaccess for either agent.
    # If buckets were merged (contamination), the hash would show reaccess>=1.
    slot = signals.get(h, {"reaccess": 0, "retry_failed": 0})
    assert slot.get("reaccess", 0) == 0, (
        "cross-agent reads of the same hash must NOT count as reaccess "
        f"(got {slot}); buckets are contaminated"
    )


@pytest.mark.asyncio
async def test_empty_agent_id_env_becomes_null(storage, monkeypatch):
    """REQ-A6: MCP_AGENT_ID='' (empty string) => agent_id NULL in usage_event.

    Parity with the store path (test_agent_id.py: empty env → no agent_id).
    resolve_telemetry_agent_id does `os.environ.get(...) or None`, so '' → None.
    """
    monkeypatch.setenv("MCP_AGENT_ID", "")
    from mcp_memory_service.models.memory import Memory
    from mcp_memory_service.utils.hashing import generate_content_hash

    content = "Empty-env telemetry memory for edge case test"
    mem = Memory(content=content, content_hash=generate_content_hash(content),
                 tags=["test"], memory_type="note")
    await storage.store(mem)
    await storage.retrieve("edge case empty env", n_results=3)

    agent_ids = _agent_ids_for(storage, "retrieval")
    assert agent_ids, "a retrieval event should still be written"
    assert all(a is None for a in agent_ids), (
        f"MCP_AGENT_ID='' must result in NULL agent_id, got {agent_ids}"
    )
