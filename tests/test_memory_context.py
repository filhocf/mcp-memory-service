"""
RED tests for proactive theme-based context injection: memory_context(task).

Feature (L3 learning-loop): today bootstrap injects the top-N GLOBAL active
beliefs (server_impl.py get_beliefs status=active min_conf=0.6, no theme
filter). memory_context does NOT exist yet. Given a task/theme it must return
beliefs RELEVANT TO THE THEME (similarity x confidence) + relevant memories,
expose confidence, stay within a token budget, and record an 'injection' event
in usage_events.

Target interface (decided at G0, mirrors the usage_telemetry module style —
module-level async functions that take `storage`):

    from mcp_memory_service.storage.context_injection import memory_context

    result = await memory_context(storage, task, budget_tokens=None, limit=None)
    # result -> dict:
    #   {
    #     "items":   [ {content, confidence, relevance|score, belief_hash?}, ... ],
    #     "beliefs": [...],          # subset / alias of items that are beliefs
    #     "truncated": bool,         # True when budget forced a cut
    #     "injected":  bool,         # False when killswitch off
    #     "belief_hashes": [...],    # hashes of injected beliefs
    #     "count": int,              # number of injected items
    #     "budget_tokens": int,      # effective budget used
    #   }

Decisions under test:
- Opt-in-ish killswitch: MCP_CONTEXT_INJECTION_ENABLED (default on; 'false' -> off).
- Budget: MCP_CONTEXT_MAX_TOKENS default 2048; budget_tokens overrides.
- Respects MCP_USAGE_TELEMETRY for the 'injection' event logging.

ALL tests are RED: the target module/function does not exist, so the import or
the attribute access or the behavioral asserts fail with real errors.
"""

import json
import os
import shutil
import tempfile

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

# Skip tests if sqlite-vec is not available
try:
    import sqlite_vec  # noqa: F401
    SQLITE_VEC_AVAILABLE = True
except ImportError:
    SQLITE_VEC_AVAILABLE = False

from mcp_memory_service.models.memory import Memory
from mcp_memory_service.utils.hashing import generate_content_hash

if SQLITE_VEC_AVAILABLE:
    from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage

pytestmark = pytest.mark.skipif(
    not SQLITE_VEC_AVAILABLE, reason="sqlite-vec not available"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def enable_injection(monkeypatch):
    """Enable injection + telemetry by default for all tests in this module.

    Individual tests override MCP_CONTEXT_INJECTION_ENABLED to exercise the
    killswitch.
    """
    monkeypatch.setenv("MCP_CONTEXT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("MCP_USAGE_TELEMETRY", "true")


@pytest_asyncio.fixture
async def storage():
    """Fresh sqlite-vec storage instance."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_context.db")

    store = SqliteVecMemoryStorage(db_path)
    await store.initialize()

    yield store

    if store.conn:
        store.conn.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


def _seed_belief(storage, belief_hash, content, confidence, status="active"):
    """Insert a belief row directly (mirrors BeliefService._create_belief)."""
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    storage.conn.execute(
        "INSERT OR REPLACE INTO beliefs "
        "(belief_hash, content, confidence, status, created_at, updated_at, "
        " derived_from, contradicted_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            belief_hash, content, confidence, status, now_iso, now_iso,
            json.dumps([]), json.dumps([]),
        ),
    )
    storage.conn.commit()


@pytest_asyncio.fixture
async def storage_with_beliefs(storage):
    """Storage seeded with beliefs where the THEME-relevant belief is NOT the
    one with the highest global confidence.

    Theme under test: "database connection pooling".
    - 'pool' belief     -> relevant, LOWER confidence (0.65)
    - 'async' belief     -> irrelevant, HIGHEST confidence (0.95)
    - 'logging' belief   -> irrelevant, mid confidence (0.80)
    A blind top-N-by-confidence would surface 'async'/'logging' first; a
    theme-aware ranker must surface 'pool'.
    """
    _seed_belief(
        storage, "pool01",
        "Always size the database connection pool to match worker concurrency",
        confidence=0.65,
    )
    _seed_belief(
        storage, "async1",
        "Prefer async/await for all I/O bound operations in the service",
        confidence=0.95,
    )
    _seed_belief(
        storage, "log001",
        "Emit structured JSON logs for every microservice request",
        confidence=0.80,
    )
    return storage


async def _store_memory(storage, content, tags):
    mem = Memory(
        content=content,
        content_hash=generate_content_hash(content),
        tags=tags,
        metadata={},
    )
    await storage.store(mem)
    return mem


# ---------------------------------------------------------------------------
# REQ-1: theme-relevant beliefs, not blind top-N global
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_returns_theme_relevant_beliefs(storage_with_beliefs):
    """REQ-1: beliefs returned are the ones RELEVANT to the task, not the
    globally highest-confidence belief."""
    from mcp_memory_service.storage.context_injection import memory_context

    result = await memory_context(
        storage_with_beliefs,
        task="How should I configure the database connection pool?",
        limit=1,
    )

    items = result["items"]
    assert len(items) >= 1, "Expected at least one injected item"
    contents = " ".join(i["content"].lower() for i in items)
    hashes = result.get("belief_hashes", [])

    # The theme-relevant (lower-confidence) belief must be present...
    assert "pool01" in hashes or "connection pool" in contents, (
        f"Theme-relevant belief not injected. Got hashes={hashes} contents={contents!r}"
    )
    # ...and the blind highest-confidence (irrelevant) belief must NOT crowd it
    # out as the single top pick.
    assert "async1" not in hashes[:1], (
        "Blind top-confidence belief ('async') was injected instead of the "
        "theme-relevant one — ranking is not theme-aware."
    )


# ---------------------------------------------------------------------------
# REQ-2: each item exposes content + confidence (+ relevance/score)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_exposes_confidence_and_relevance(storage_with_beliefs):
    """REQ-2: every injected item carries content, confidence and a
    relevance/score field."""
    from mcp_memory_service.storage.context_injection import memory_context

    result = await memory_context(
        storage_with_beliefs,
        task="database connection pool sizing",
        limit=3,
    )

    items = result["items"]
    assert items, "Expected injected items"
    for item in items:
        assert "content" in item and item["content"], "item missing content"
        assert "confidence" in item, "item missing confidence"
        assert isinstance(item["confidence"], (int, float))
        assert ("relevance" in item) or ("score" in item), (
            f"item missing relevance/score: {item!r}"
        )


# ---------------------------------------------------------------------------
# REQ-3: ordering by relevance x confidence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_ordered_by_relevance_x_confidence(storage_with_beliefs):
    """REQ-3: items are ordered by a combined relevance x confidence score
    (descending)."""
    from mcp_memory_service.storage.context_injection import memory_context

    result = await memory_context(
        storage_with_beliefs,
        task="database connection pool configuration",
        limit=3,
    )

    items = result["items"]
    assert len(items) >= 2, "Need >=2 items to assert ordering"

    def _rank(item):
        rel = item.get("relevance", item.get("score"))
        assert rel is not None, f"missing relevance/score on {item!r}"
        return rel * item["confidence"]

    ranks = [_rank(i) for i in items]
    assert ranks == sorted(ranks, reverse=True), (
        f"items not ordered by relevance x confidence: {ranks}"
    )
    # The theme-relevant belief should rank first.
    assert "pool" in items[0]["content"].lower(), (
        f"top item is not the theme-relevant belief: {items[0]['content']!r}"
    )


# ---------------------------------------------------------------------------
# REQ-4: respects token budget and signals truncation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_respects_token_budget(storage_with_beliefs):
    """REQ-4: a tiny budget truncates the injected context and the result
    flags truncation."""
    from mcp_memory_service.storage.context_injection import memory_context

    # Add several more beliefs so the full set would exceed a tiny budget.
    for i in range(8):
        _seed_belief(
            storage_with_beliefs, f"extra{i}",
            f"Database pooling guideline number {i}: tune max connections "
            f"carefully to avoid exhausting the server side limits in prod",
            confidence=0.7 + i * 0.01,
        )

    tiny = await memory_context(
        storage_with_beliefs,
        task="database connection pool",
        budget_tokens=20,  # ~80 chars — forces a cut
    )
    large = await memory_context(
        storage_with_beliefs,
        task="database connection pool",
        budget_tokens=4096,
    )

    assert tiny["budget_tokens"] == 20
    assert tiny["truncated"] is True, "tiny budget must signal truncation"
    assert len(tiny["items"]) < len(large["items"]), (
        "tiny budget should inject fewer items than a large budget"
    )

    # Rendered content must stay within ~4 chars/token of the budget.
    rendered = " ".join(i["content"] for i in tiny["items"])
    assert len(rendered) <= 20 * 4 + 200, (
        f"rendered context exceeds token budget: {len(rendered)} chars"
    )


# ---------------------------------------------------------------------------
# REQ-5: logs an 'injection' event in usage_events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_logs_injection_event(storage_with_beliefs):
    """REQ-5: after memory_context, usage_events contains an 'injection' event
    carrying belief_hashes + count."""
    from mcp_memory_service.storage.context_injection import memory_context

    result = await memory_context(
        storage_with_beliefs,
        task="database connection pool",
        limit=3,
    )

    def check_event():
        cursor = storage_with_beliefs.conn.execute(
            "SELECT * FROM usage_events WHERE event_type = 'injection'"
        )
        events = cursor.fetchall()
        assert len(events) == 1, f"Expected 1 injection event, got {len(events)}"
        event = events[0]
        assert event["event_type"] == "injection"

        # belief_hashes + count live in the metadata JSON column (schema has no
        # dedicated columns for them — see migration 013).
        meta_raw = event["metadata"]
        assert meta_raw, "injection event missing metadata payload"
        meta = json.loads(meta_raw)
        assert "belief_hashes" in meta, f"metadata missing belief_hashes: {meta}"
        assert "count" in meta, f"metadata missing count: {meta}"
        assert meta["count"] == len(result["items"])
        assert set(result.get("belief_hashes", [])) == set(meta["belief_hashes"])

    await storage_with_beliefs._execute_with_retry(check_event)


# ---------------------------------------------------------------------------
# REQ-6: killswitch off -> no injection, no event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_killswitch_off(storage_with_beliefs, monkeypatch):
    """REQ-6: MCP_CONTEXT_INJECTION_ENABLED=false -> no injection (empty/noop)
    and no injection event logged."""
    from mcp_memory_service.storage.context_injection import memory_context

    monkeypatch.setenv("MCP_CONTEXT_INJECTION_ENABLED", "false")

    result = await memory_context(
        storage_with_beliefs,
        task="database connection pool",
        limit=3,
    )

    assert result["injected"] is False, "killswitch off must not inject"
    assert result["items"] == [], "killswitch off must return no items"

    def check_no_event():
        cursor = storage_with_beliefs.conn.execute(
            "SELECT COUNT(*) AS c FROM usage_events WHERE event_type = 'injection'"
        )
        assert cursor.fetchone()["c"] == 0, "killswitch off must log no event"

    await storage_with_beliefs._execute_with_retry(check_no_event)


# ---------------------------------------------------------------------------
# REQ-7: graceful fallback without embedding
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_graceful_without_embedding(storage_with_beliefs):
    """REQ-7: with no embedding model available, memory_context must not crash
    and must fall back to top-N by confidence."""
    from mcp_memory_service.storage.context_injection import memory_context

    # Force the "no embedding" path: retrieve() returns [] and any similarity
    # computation is unavailable.
    storage_with_beliefs.embedding_model = None

    result = await memory_context(
        storage_with_beliefs,
        task="database connection pool",
        limit=2,
    )

    assert isinstance(result, dict)
    items = result["items"]
    assert items, "fallback must still return beliefs by confidence"
    # Fallback = top-N by confidence => highest-confidence belief ('async', 0.95)
    # leads when theme similarity is unavailable.
    confidences = [i["confidence"] for i in items]
    assert confidences == sorted(confidences, reverse=True), (
        f"fallback must order by confidence desc: {confidences}"
    )
    assert confidences[0] == pytest.approx(0.95), (
        "fallback top item should be the highest-confidence belief"
    )
