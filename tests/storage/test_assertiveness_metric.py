"""
RED tests for the assertiveness metric + reaccess/re-query signals feature.

Spec: ~/.kiro/tmp/g0-metrica-reaccess.md
- ADR-0005 (métrica de assertividade: re-query rate, injection coverage, lost context)
- RFC-MM-01 (job de recálculo de quality_score a partir de sinais derivados)
- Tudo sobre a telemetria usage_events existente (migration 014), opt-in
  MCP_USAGE_TELEMETRY, zero-disciplina (deriva de usage_events, nada manual).

These tests target an API that does NOT exist yet and MUST fail RED:
- Capture of returned content hashes in usage_events.metadata (retrieve hook today
  only writes n_results, never the returned hashes) -> REQ-1.
- derive_signals(storage, ...) -> per-hash reaccess / retry_failed signals (REQ-2/3).
- get_assertiveness_metrics(storage) -> re_query_rate / injection_coverage /
  lost_context_count / lost_context_rate (REQ-4/5/6).
- recompute_quality_scores(storage, ...) -> quality recalc job with decay (REQ-7).
- Kill-switch + zero-discipline guarantees (REQ-8).

Each test maps 1:1 to REQ-1..8 of the EARS spec. All are designed to FAIL until
the dev-impl lands the production code. Nothing here touches src/.
"""

import pytest
import pytest_asyncio
import os
import json
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

# Skip tests if sqlite-vec is not available (mirror tests/test_usage_telemetry.py)
try:
    import sqlite_vec  # noqa: F401
    SQLITE_VEC_AVAILABLE = True
except ImportError:
    SQLITE_VEC_AVAILABLE = False

from mcp_memory_service.models.memory import Memory
from mcp_memory_service.utils.hashing import generate_content_hash
from mcp_memory_service.storage.usage_telemetry import log_usage_event

if SQLITE_VEC_AVAILABLE:
    from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage

pytestmark = pytest.mark.skipif(
    not SQLITE_VEC_AVAILABLE, reason="sqlite-vec not available"
)


# ---------------------------------------------------------------------------
# Fixtures (same shape as tests/test_usage_telemetry.py: sqlite-vec real in tmp)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def storage():
    """Create a real sqlite-vec storage instance in a tmp dir."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_assertiveness.db")

    store = SqliteVecMemoryStorage(db_path)
    await store.initialize()

    yield store

    if store.conn:
        store.conn.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest_asyncio.fixture
async def storage_with_memories(storage):
    """Storage seeded with a few retrievable memories."""
    contents = [
        "Test memory about Python programming and async patterns",
        "Test memory about database design and indexes",
        "Test memory about jenkins credentials and pipelines",
    ]
    for c in contents:
        await storage.store(
            Memory(
                content=c,
                content_hash=generate_content_hash(c),
                tags=["assertiveness-test"],
            )
        )
    return storage


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def _seed_retrieval_event(storage, *, agent_id, returned_hashes, query, when):
    """Seed a retrieval usage_event with returned_hashes in metadata.

    Uses the production log_usage_event path with the NEW returned_hashes kwarg
    so these tests exercise the exact capture contract the dev-impl must honor.
    """
    from mcp_memory_service.storage.usage_telemetry import query_hash

    await log_usage_event(
        storage,
        "retrieval",
        tool="retrieval",
        n_results=len(returned_hashes),
        latency_ms=1.0,
        query_hash=query_hash(query),
        agent_id=agent_id,
        returned_hashes=list(returned_hashes),
        timestamp=_iso(when),
    )


# ---------------------------------------------------------------------------
# REQ-1 — retrieval captures returned hashes (no raw query leak)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retrieval_captures_returned_hashes(storage_with_memories):
    """REQ-1: after retrieve(n_results=3) the retrieval event's metadata carries
    {'returned_hashes': [... up to 3 hashes ...]}; the raw query never leaks.

    RED: retrieve.py today logs only n_results (no returned_hashes), so the
    metadata column is NULL -> JSON parse / key lookup fails.
    """
    storage = storage_with_memories
    query = "Python async programming tips"

    results = await storage.retrieve(query=query, n_results=3)
    returned = [r.memory.content_hash for r in results]
    assert returned, "fixture should return at least one memory"

    def check():
        cursor = storage.conn.execute(
            "SELECT metadata FROM usage_events WHERE event_type='retrieval' "
            "ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        assert row is not None, "a retrieval event should have been logged"

        metadata_raw = row["metadata"]
        assert metadata_raw is not None, (
            "retrieval metadata must carry returned_hashes (today it is NULL)"
        )
        meta = json.loads(metadata_raw)
        assert "returned_hashes" in meta, "metadata must contain 'returned_hashes'"
        assert meta["returned_hashes"] == returned, (
            "returned_hashes must be exactly the hashes retrieve() returned"
        )

        # Privacy: raw query text must never appear anywhere in the event row.
        cursor2 = storage.conn.execute("SELECT * FROM usage_events")
        for r in cursor2.fetchall():
            assert query not in str(r), "raw query leaked into usage_events"

    await storage._execute_with_retry(check)


# ---------------------------------------------------------------------------
# REQ-2 — reaccess signal derived (positive)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reaccess_signal_derived(storage_with_memories):
    """REQ-2: same content_hash returned in >=2 retrievals of the same agent
    within the reaccess window => (N-1) positive 'reaccess' signals for that hash.

    RED: derive_signals does not exist yet.
    """
    storage = storage_with_memories
    from mcp_memory_service.storage.usage_telemetry import derive_signals

    h = generate_content_hash("Test memory about Python programming and async patterns")
    now = datetime.now(timezone.utc)

    # Same hash H returned to the same agent in two distinct retrievals.
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h], query="q1", when=now - timedelta(days=2)
    )
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h], query="q2", when=now
    )

    signals = await derive_signals(storage)

    assert h in signals, "derived signals must be keyed by content_hash"
    assert signals[h].get("reaccess") == 1, (
        "two retrievals of the same hash by one agent => reaccess == 1"
    )


# ---------------------------------------------------------------------------
# REQ-3 — re-query signal derived (negative / retry_failed)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_requery_signal_derived(storage_with_memories):
    """REQ-3: two retrievals of the same agent within 5 min, distinct query_hash,
    overlapping returned_hashes => 'retry_failed' signal for the hashes returned
    by the FIRST event.

    RED: derive_signals does not exist yet.
    """
    storage = storage_with_memories
    from mcp_memory_service.storage.usage_telemetry import derive_signals

    h = generate_content_hash("Test memory about jenkins credentials and pipelines")
    now = datetime.now(timezone.utc)

    # Two close retrievals, different queries, overlapping result set.
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h], query="jenkins creds",
        when=now - timedelta(minutes=3),
    )
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h], query="jenkins pipeline token",
        when=now,
    )

    signals = await derive_signals(storage)

    assert h in signals, "derived signals must be keyed by content_hash"
    assert signals[h].get("retry_failed", 0) > 0, (
        "a close re-query with overlapping results => retry_failed > 0 for first-event hashes"
    )


# ---------------------------------------------------------------------------
# REQ-4 — re_query_rate sub-metric (ADR-0005 #1)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_re_query_rate(storage_with_memories):
    """REQ-4: re_query_rate = (# retrievals classified as re-query) / (total retrievals),
    in [0,1]; empty dataset => 0.0.

    Dataset: 4 retrievals, exactly 1 of which is a re-query => 0.25.
    RED: get_assertiveness_metrics does not exist yet.
    """
    storage = storage_with_memories
    from mcp_memory_service.storage.usage_telemetry import get_assertiveness_metrics

    # Empty dataset -> 0.0
    empty_metrics = await get_assertiveness_metrics(storage)
    assert empty_metrics["re_query_rate"] == 0.0, "no retrievals => re_query_rate 0.0"

    h1 = generate_content_hash("Test memory about Python programming and async patterns")
    h2 = generate_content_hash("Test memory about database design and indexes")
    now = datetime.now(timezone.utc)

    # Retrieval 1 and 2 form a re-query pair (close, distinct query, overlapping h1).
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h1], query="py async",
        when=now - timedelta(minutes=2),
    )
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h1], query="python patterns",
        when=now - timedelta(minutes=1),
    )
    # Retrieval 3 and 4: unrelated, far apart, no overlap -> not re-queries.
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h2], query="database",
        when=now - timedelta(hours=5),
    )
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h2], query="indexes",
        when=now - timedelta(hours=10),
    )

    metrics = await get_assertiveness_metrics(storage)
    assert metrics["re_query_rate"] == 0.25, (
        f"1 re-query in 4 retrievals => 0.25, got {metrics['re_query_rate']}"
    )


# ---------------------------------------------------------------------------
# REQ-5 — injection_coverage sub-metric (ADR-0005 #2)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_injection_coverage(storage_with_memories):
    """REQ-5: injection_coverage = fraction of injected belief_hashes that reappear
    later in a retrieval's returned_hashes (or feedback/drill-down) within the window.

    Inject [A, B]; later a retrieval returns A => coverage 0.5.
    RED: get_assertiveness_metrics does not exist yet.
    """
    storage = storage_with_memories
    from mcp_memory_service.storage.usage_telemetry import get_assertiveness_metrics

    a = generate_content_hash("Test memory about Python programming and async patterns")
    b = generate_content_hash("Test memory about database design and indexes")
    now = datetime.now(timezone.utc)

    # An injection event (same pattern as context_injection.py: belief_hashes in metadata).
    await log_usage_event(
        storage,
        "injection",
        tool="injection",
        agent_id="zero",
        timestamp=_iso(now - timedelta(minutes=5)),
        metadata=json.dumps({"belief_hashes": [a, b], "count": 2}),
    )
    # Later retrieval returns only A.
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[a], query="async", when=now
    )

    metrics = await get_assertiveness_metrics(storage)
    assert metrics["injection_coverage"] == 0.5, (
        f"1 of 2 injected hashes reused => 0.5, got {metrics['injection_coverage']}"
    )


# ---------------------------------------------------------------------------
# REQ-6 — lost_context sub-metric (ADR-0005 #3, proxy)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lost_context_rate(storage):
    """REQ-6: when a retrieval returns a content_hash whose memory is a recent
    checkpoint (proxy for 'should have been in context'), it counts toward
    lost_context_count and lost_context_rate over total retrievals.

    RED: get_assertiveness_metrics does not exist yet.
    """
    from mcp_memory_service.storage.usage_telemetry import get_assertiveness_metrics

    checkpoint_content = "[CHECKPOINT] sessao g3 metrica reaccess feito"
    ckpt_hash = generate_content_hash(checkpoint_content)
    await storage.store(
        Memory(
            content=checkpoint_content,
            content_hash=ckpt_hash,
            tags=["checkpoint", "sessao"],
            memory_type="milestone",
        )
    )

    now = datetime.now(timezone.utc)
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[ckpt_hash],
        query="where did we stop", when=now,
    )

    metrics = await get_assertiveness_metrics(storage)
    assert metrics["lost_context_count"] >= 1, (
        "retrieving a recent checkpoint should count as lost-context (proxy)"
    )
    assert "lost_context_rate" in metrics, "lost_context_rate must be exposed"


# ---------------------------------------------------------------------------
# REQ-7 — quality_score recalc job (RFC-MM-01 §4) with decay
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_quality_recalc_job(storage_with_memories):
    """REQ-7: recompute_quality_scores updates quality per content_hash:
      quality = base + sigmoid(sum(pos) - 2*sum(neg)) * decay(age, half_life=14d)
    - hash with 3 pos / 0 neg => quality rises above base
    - hash with 0 pos / 2 neg => quality falls below base
    - a signal 28d old weighs ~1/4 of a fresh one (half_life 14d: 2 half-lives)

    RED: recompute_quality_scores does not exist yet.
    """
    storage = storage_with_memories
    from mcp_memory_service.storage.usage_telemetry import recompute_quality_scores

    h_pos = generate_content_hash("Test memory about Python programming and async patterns")
    h_neg = generate_content_hash("Test memory about database design and indexes")
    h_decay = generate_content_hash("Test memory about jenkins credentials and pipelines")

    now = datetime.now(timezone.utc)

    # h_pos: 3 fresh positive (reaccess) signals.
    for i in range(3):
        await _seed_retrieval_event(
            storage, agent_id="zero", returned_hashes=[h_pos], query=f"pos{i}",
            when=now - timedelta(minutes=i + 1),
        )
    # Extra reaccess for h_pos: appears again so it is reaccessed.
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h_pos], query="pos-again", when=now
    )

    # h_neg: 2 negative (retry_failed) signals via close re-queries.
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h_neg], query="neg a",
        when=now - timedelta(minutes=4),
    )
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h_neg], query="neg b",
        when=now - timedelta(minutes=3),
    )
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h_neg], query="neg c",
        when=now - timedelta(minutes=2),
    )

    base = 0.5
    result = await recompute_quality_scores(storage, base=base)

    assert result[h_pos] > base, "3 positive signals should raise quality above base"
    assert result[h_neg] < base, "2 negative signals should drop quality below base"

    # Decay check: same single positive signal, fresh vs 28d old (~2 half-lives => ~1/4).
    fresh = await recompute_quality_scores(
        storage, base=base,
        signals_override={h_decay: {"reaccess": 1, "age_days": 0}},
    )
    old = await recompute_quality_scores(
        storage, base=base,
        signals_override={h_decay: {"reaccess": 1, "age_days": 28}},
    )
    fresh_delta = fresh[h_decay] - base
    old_delta = old[h_decay] - base
    assert fresh_delta > 0 and old_delta > 0, "a positive signal must raise quality"
    ratio = old_delta / fresh_delta
    assert 0.15 <= ratio <= 0.35, (
        f"28d-old signal should weigh ~1/4 of a fresh one (half_life=14d), got ratio={ratio:.3f}"
    )


# ---------------------------------------------------------------------------
# REQ-8 — kill-switch + zero-discipline
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_killswitch_and_zero_discipline(storage_with_memories):
    """REQ-8: MCP_USAGE_TELEMETRY off => no returned_hashes captured and no signals;
    on => signals arise only from retrieve()/record_feedback_event(), with NO manual
    rating API call. Derivation reads purely from usage_events (zero-discipline).

    RED: derive_signals does not exist yet; capture of returned_hashes is missing.
    """
    storage = storage_with_memories
    from mcp_memory_service.storage.usage_telemetry import derive_signals

    # --- OFF: nothing captured, no signals ---
    with patch.dict(os.environ, {"MCP_USAGE_TELEMETRY": "false"}):
        await storage.retrieve(query="python async", n_results=3)

        def check_no_capture():
            cursor = storage.conn.execute(
                "SELECT metadata FROM usage_events WHERE event_type='retrieval'"
            )
            for row in cursor.fetchall():
                meta = json.loads(row["metadata"]) if row["metadata"] else {}
                assert not meta.get("returned_hashes"), (
                    "kill-switch off must not capture returned_hashes"
                )

        await storage._execute_with_retry(check_no_capture)

        off_signals = await derive_signals(storage)
        assert off_signals == {}, "kill-switch off => zero derived signals"

    # --- ON: signals derive only from retrieve() hook, no manual rating API ---
    with patch.dict(os.environ, {"MCP_USAGE_TELEMETRY": "true"}):
        # Two real retrievals of the same query -> same memory returned twice ->
        # must yield a reaccess signal WITHOUT any manual rating/annotation call.
        await storage.retrieve(query="python async", n_results=3)
        await storage.retrieve(query="python async", n_results=3)

        on_signals = await derive_signals(storage)
        assert on_signals, (
            "with telemetry on, retrieve() alone (zero-discipline) must produce signals"
        )
        assert any(
            s.get("reaccess", 0) >= 1 for s in on_signals.values()
        ), "repeated retrieve of the same memory must derive a reaccess signal"
