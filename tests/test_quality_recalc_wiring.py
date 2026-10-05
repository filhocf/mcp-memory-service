"""RED tests for the L4 learning-loop quality-recalc WIRING (Gate 3).

Three production pieces already exist but have ZERO production callers
(dead-letter). These tests pin the wiring that must connect them, and are
designed to FAIL on main because the wiring is absent:

Peça 1 — scheduler job (does NOT exist yet):
  ConsolidationScheduler._schedule_quality_recalc_job() +
  ._run_quality_recalc_job(), opt-in via MCP_QUALITY_RECALC_SCHEDULE,
  APScheduler job id == "quality_recalc".
  Mirrors the existing _schedule_harvest_job pattern
  (tests/test_scheduled_harvest.py).

Peça 2 — persistence + clamp (gap: recompute_quality_scores only CALCULATES):
  storage/usage_telemetry.py::recompute_quality_scores returns a dict today but
  (a) never PERSISTS the new quality_score into storage and (b) never CLAMPS to
  [0, 1] (the signed sigmoid can push base+delta below 0 or above 1). The job
  from Peça 1 must: recompute -> clamp [0,1] -> persist via
  storage.update_memory_metadata(hash, {"quality_score": v}) (the real update
  path; quality_score is a non-protected metadata field, read back through the
  Memory.quality_score property — models/memory.py:239-241).

Nothing here touches src/. Helpers/fixtures mirror
tests/storage/test_assertiveness_metric.py and tests/test_scheduled_harvest.py
(no shared conftest provides them, so the sqlite-vec fixtures are redefined
here with the SAME shape — the originals are file-local in that module).
"""

import os
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# sqlite-vec availability guard (mirror tests/storage/test_assertiveness_metric.py)
# ---------------------------------------------------------------------------
try:
    import sqlite_vec  # noqa: F401
    SQLITE_VEC_AVAILABLE = True
except ImportError:
    SQLITE_VEC_AVAILABLE = False

from mcp_memory_service.consolidation.scheduler import ConsolidationScheduler

if SQLITE_VEC_AVAILABLE:
    from mcp_memory_service.models.memory import Memory
    from mcp_memory_service.utils.hashing import generate_content_hash
    from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage
    from mcp_memory_service.storage.usage_telemetry import log_usage_event, query_hash


# ===========================================================================
# Peça 1 — scheduler job wiring (NO sqlite-vec needed; mirrors harvest tests)
# ===========================================================================
def _scheduler(env, monkeypatch):
    """Build a ConsolidationScheduler with no consolidation jobs.

    Same shape as tests/test_scheduled_harvest.py::_scheduler.
    """
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    consolidator = MagicMock()
    consolidator.storage = MagicMock()
    sched = ConsolidationScheduler(
        consolidator=consolidator,
        schedule_config={},  # no consolidation jobs
        enabled=True,
    )
    return sched


def test_quality_recalc_job_registered_when_env_set(monkeypatch):
    """MCP_QUALITY_RECALC_SCHEDULE=1h registers a 'quality_recalc' job.

    RED: ConsolidationScheduler has no _schedule_quality_recalc_job yet =>
    AttributeError (method absent).
    """
    sched = _scheduler({"MCP_QUALITY_RECALC_SCHEDULE": "1h"}, monkeypatch)
    assert sched.scheduler is not None
    sched._schedule_quality_recalc_job()
    job = sched.scheduler.get_job("quality_recalc")
    assert job is not None, (
        "quality_recalc job should be registered when "
        "MCP_QUALITY_RECALC_SCHEDULE is set"
    )


def test_quality_recalc_job_not_registered_by_default(monkeypatch):
    """Unset MCP_QUALITY_RECALC_SCHEDULE => no job (opt-in, zero regression).

    RED: method absent => AttributeError.
    """
    monkeypatch.delenv("MCP_QUALITY_RECALC_SCHEDULE", raising=False)
    sched = _scheduler({}, monkeypatch)
    sched._schedule_quality_recalc_job()
    assert sched.scheduler.get_job("quality_recalc") is None


def test_quality_recalc_job_not_registered_when_disabled(monkeypatch):
    """Explicit 'disabled' => no job.

    RED: method absent => AttributeError.
    """
    sched = _scheduler({"MCP_QUALITY_RECALC_SCHEDULE": "disabled"}, monkeypatch)
    sched._schedule_quality_recalc_job()
    assert sched.scheduler.get_job("quality_recalc") is None


# ===========================================================================
# Peça 2 — persistence + clamp (requires sqlite-vec; mirrors assertiveness test)
# ===========================================================================
pytestmark_sqlite = pytest.mark.skipif(
    not SQLITE_VEC_AVAILABLE, reason="sqlite-vec not available"
)


@pytest_asyncio.fixture
async def storage():
    """Real sqlite-vec storage in a tmp dir (same shape as test_assertiveness_metric)."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_quality_recalc.db")
    store = SqliteVecMemoryStorage(db_path)
    await store.initialize()
    yield store
    if store.conn:
        store.conn.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest_asyncio.fixture
async def storage_with_memories(storage):
    """Storage seeded with a few retrievable memories (same contents as molde)."""
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
                tags=["quality-recalc-test"],
            )
        )
    return storage


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def _seed_retrieval_event(storage, *, agent_id, returned_hashes, query, when):
    """Seed a retrieval usage_event with returned_hashes in metadata.

    Same helper as tests/storage/test_assertiveness_metric.py::_seed_retrieval_event.
    """
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


async def _stored_quality(storage, content_hash: str) -> float:
    """Read the PERSISTED quality_score back from storage.

    quality_score lives in the metadata JSON and is surfaced via the
    Memory.quality_score property (models/memory.py:239-241).
    """
    results = await storage.retrieve(
        query="Test memory", n_results=10
    )
    for r in results:
        if r.memory.content_hash == content_hash:
            return r.memory.quality_score
    raise AssertionError(f"memory {content_hash} not found when reading quality")


async def _stored_computed(storage, content_hash: str) -> float:
    """Read the PERSISTED computed_quality (machine origin) back from storage.

    After the #1312 split the MACHINE recalc writes computed_quality; the
    effective quality_score is re-materialized respecting any human user_rating.
    computed_quality has no model property, so read it from metadata directly.
    """
    results = await storage.retrieve(query="Test memory", n_results=10)
    for r in results:
        if r.memory.content_hash == content_hash:
            value = r.memory.metadata.get("computed_quality")
            if value is None:
                raise AssertionError(
                    f"memory {content_hash} has no computed_quality persisted"
                )
            return float(value)
    raise AssertionError(f"memory {content_hash} not found when reading computed_quality")


async def _set_user_rating(storage, content_hash: str, rating: int) -> None:
    """Set a human user_rating on a stored memory (mirrors set_memory_rating).

    quality_score is non-protected metadata, so a flat update lands user_rating
    (and the rating-materialized quality_score) straight into the metadata JSON,
    the same end state the handler produces.
    """
    from mcp_memory_service.quality.config import effective_quality

    memory = await storage.get_by_hash(content_hash)
    assert memory is not None, f"cannot rate missing memory {content_hash}"
    computed = memory.metadata.get("computed_quality")
    if computed is None:
        computed = memory.metadata.get("quality_score", 0.5)
    materialized = effective_quality(computed=computed, user_rating=rating)
    await storage.update_memory_metadata(
        content_hash,
        {
            "user_rating": rating,
            "computed_quality": computed,
            "quality_score": materialized,
        },
        preserve_timestamps=True,
    )


@pytestmark_sqlite
@pytest.mark.asyncio
async def test_recalc_job_persists_quality_scores(storage_with_memories, monkeypatch):
    """The quality-recalc JOB must PERSIST the recomputed MACHINE score into
    storage: a hash with reaccess (positive) rises above base; a hash with
    retry_failed (negative) drops below base. Default base=0.5.

    After the #1312 split the machine origin is ``computed_quality`` (the
    effective ``quality_score`` only moves on its own when there is no human
    ``user_rating``). With no rating set here, both fields track together, but
    the assertion targets ``computed_quality`` — the field the machine owns.
    """
    monkeypatch.setenv("MCP_USAGE_TELEMETRY", "true")
    storage = storage_with_memories

    h_pos = generate_content_hash("Test memory about Python programming and async patterns")
    h_neg = generate_content_hash("Test memory about database design and indexes")
    now = datetime.now(timezone.utc)

    # h_pos: reaccessed across two distinct retrievals (positive signal).
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h_pos], query="py async",
        when=now - timedelta(days=2),
    )
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h_pos], query="py async again",
        when=now,
    )

    # h_neg: close re-queries with distinct query, overlapping result => retry_failed.
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h_neg], query="db a",
        when=now - timedelta(minutes=4),
    )
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h_neg], query="db b",
        when=now - timedelta(minutes=3),
    )
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h_neg], query="db c",
        when=now - timedelta(minutes=2),
    )

    # Build the scheduler bound to THIS real storage and run the recalc job.
    consolidator = MagicMock()
    consolidator.storage = storage
    sched = ConsolidationScheduler(
        consolidator=consolidator, schedule_config={}, enabled=True
    )
    await sched._run_quality_recalc_job()

    computed_pos = await _stored_computed(storage, h_pos)
    computed_neg = await _stored_computed(storage, h_neg)

    assert computed_pos > 0.5, (
        "a reaccessed hash should have its PERSISTED computed_quality raised "
        f"above base (got {computed_pos})"
    )
    assert computed_neg < 0.5, (
        "a retry_failed hash should have its PERSISTED computed_quality dropped "
        f"below base (got {computed_neg})"
    )


@pytestmark_sqlite
@pytest.mark.asyncio
async def test_recalc_job_clamps_quality_to_unit_interval(storage_with_memories, monkeypatch):
    """Persisted quality_score must be CLAMPED to [0, 1].

    With a high base and a strong negative net signal the raw formula
    (base + signed_sigmoid(...)*decay) goes negative; with a high base and a
    strong positive net it exceeds 1. The job must clamp before persisting so no
    out-of-range quality ever reaches storage.

    RED: no job + no clamp today => either AttributeError (job absent) or, when
    recompute is called directly, nothing is persisted/clamped at all.
    """
    monkeypatch.setenv("MCP_USAGE_TELEMETRY", "true")
    storage = storage_with_memories

    h_low = generate_content_hash("Test memory about database design and indexes")
    now = datetime.now(timezone.utc)

    # Drive h_low strongly negative via repeated close re-queries.
    for i in range(5):
        await _seed_retrieval_event(
            storage, agent_id="zero", returned_hashes=[h_low],
            query=f"q{i}", when=now - timedelta(seconds=30 * (5 - i)),
        )

    consolidator = MagicMock()
    consolidator.storage = storage
    sched = ConsolidationScheduler(
        consolidator=consolidator, schedule_config={}, enabled=True
    )
    await sched._run_quality_recalc_job()

    persisted = await _stored_quality(storage, h_low)
    assert 0.0 <= persisted <= 1.0, (
        f"persisted quality_score must be clamped to [0,1], got {persisted}"
    )


@pytestmark_sqlite
@pytest.mark.asyncio
async def test_recalc_job_preserves_human_rating(storage_with_memories, monkeypatch):
    """P1 regression: the periodic machine recalc must NOT erase a human rating.

    Model split #1312: quality_score is the EFFECTIVE value materialized from
    computed_quality (machine) and user_rating (human). A thumbs-down maps to
    0.25 (USER_RATING_TO_QUALITY) and must win over the machine recompute. The
    old job wrote the machine score straight into quality_score, wiping the
    human verdict every cycle — this test fails against that behaviour.

    After the fix:
      - quality_score STAYS at the rating value (0.25 for thumbs-down),
      - computed_quality IS updated by the machine recalc (positive signal here,
        so it rises above base and is clearly != quality_score).
    """
    monkeypatch.setenv("MCP_USAGE_TELEMETRY", "true")
    storage = storage_with_memories

    h_rated = generate_content_hash("Test memory about Python programming and async patterns")
    now = datetime.now(timezone.utc)

    # Human thumbs-down (-1) BEFORE the recalc runs. Effective quality -> 0.25.
    await _set_user_rating(storage, h_rated, -1)
    assert await _stored_quality(storage, h_rated) == pytest.approx(0.25), (
        "precondition: thumbs-down should materialize quality_score to 0.25"
    )

    # Give the machine a strong POSITIVE signal (two distinct reaccesses) so the
    # recomputed computed_quality rises above base — if the job wrote it into
    # quality_score it would overwrite the 0.25 and the assertion below fails.
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h_rated], query="py async",
        when=now - timedelta(days=2),
    )
    await _seed_retrieval_event(
        storage, agent_id="zero", returned_hashes=[h_rated], query="py async again",
        when=now,
    )

    consolidator = MagicMock()
    consolidator.storage = storage
    sched = ConsolidationScheduler(
        consolidator=consolidator, schedule_config={}, enabled=True
    )
    await sched._run_quality_recalc_job()

    persisted_quality = await _stored_quality(storage, h_rated)
    persisted_computed = await _stored_computed(storage, h_rated)

    # The human verdict survives the recompute.
    assert persisted_quality == pytest.approx(0.25), (
        "human thumbs-down must NOT be erased by the recalc job "
        f"(quality_score should stay 0.25, got {persisted_quality})"
    )
    # The machine field still updates underneath, reflecting the positive signal.
    assert persisted_computed > 0.5, (
        "computed_quality should be refreshed by the machine recalc "
        f"(positive signal => above base, got {persisted_computed})"
    )
    assert persisted_computed != pytest.approx(persisted_quality), (
        "computed_quality (machine) and quality_score (human-rated) must now "
        "diverge, proving the two origins are tracked separately"
    )
