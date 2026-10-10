"""L4 feedback closes only when injection provenance is correlatable.

Context (2026-10-10): injection_coverage and injected_then_used were structurally
stuck at 0.0 — the injection event recorded only belief_hashes (sha256 of distilled
belief text), while coverage correlates against retrieval returned_hashes (memory
content_hashes). belief_hash ∩ content_hash = ∅, so the loop could never show
"an injected belief was later used".

Fix under test: the injection event also records source_hashes (each injected
belief's derived_from provenance = its source memories' content_hashes), and the
telemetry correlates on those. This test proves coverage/injected_then_used move
off zero when a source memory of an injected belief later appears in a retrieval.
"""
import json

import pytest
import pytest_asyncio

from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage
from mcp_memory_service.storage.usage_telemetry import (
    log_usage_event,
    get_assertiveness_metrics,
    _event_belief_hashes,
)


@pytest_asyncio.fixture
async def storage(tmp_path):
    st = SqliteVecMemoryStorage(str(tmp_path / "t.db"))
    await st.initialize()
    yield st
    try:
        st.conn.close()
    except Exception:
        pass


def test_event_hashes_prefers_source_over_belief():
    """_event_belief_hashes returns source_hashes (provenance) when present."""
    meta = json.dumps({"belief_hashes": ["beliefX"], "source_hashes": ["memA", "memB"]})
    assert _event_belief_hashes(meta) == ["memA", "memB"]


def test_event_hashes_falls_back_to_belief_hashes_for_old_events():
    """Older injection events without source_hashes still parse (belief_hashes)."""
    meta = json.dumps({"belief_hashes": ["beliefX"], "count": 1})
    assert _event_belief_hashes(meta) == ["beliefX"]


@pytest.mark.asyncio
async def test_injection_coverage_moves_off_zero_with_provenance(storage, monkeypatch):
    """E2E: inject a belief carrying source_hashes, then a retrieval that returns one
    of those source memories → injection_coverage and injected_then_used > 0."""
    monkeypatch.setenv("MCP_USAGE_TELEMETRY", "true")
    src_hash = "a" * 64  # a source memory content_hash

    # 1. Injection event records the belief's provenance (source_hashes) — the fix.
    await log_usage_event(
        storage, "injection", n_results=1, agent_id="zero",
        metadata=json.dumps({"belief_hashes": ["b" * 64], "source_hashes": [src_hash], "count": 1}),
    )
    # 2. A later retrieval returns that source memory.
    await log_usage_event(
        storage, "retrieval", n_results=1, agent_id="zero",
        metadata=json.dumps({"returned_hashes": [src_hash], "result_count": 1}),
    )

    metrics = await get_assertiveness_metrics(storage)
    assert metrics["injection_coverage"] > 0.0, (
        f"coverage must move off zero once provenance is correlatable, got {metrics}"
    )


@pytest.mark.asyncio
async def test_injection_coverage_stays_zero_without_followup_use(storage, monkeypatch):
    """A belief injected but whose source memory is never retrieved stays uncovered
    (the metric reflects real utility, not mere injection)."""
    monkeypatch.setenv("MCP_USAGE_TELEMETRY", "true")
    await log_usage_event(
        storage, "injection", n_results=1, agent_id="zero",
        metadata=json.dumps({"belief_hashes": ["b" * 64], "source_hashes": ["c" * 64], "count": 1}),
    )
    # a retrieval that returns an UNRELATED memory
    await log_usage_event(
        storage, "retrieval", n_results=1, agent_id="zero",
        metadata=json.dumps({"returned_hashes": ["d" * 64], "result_count": 1}),
    )
    metrics = await get_assertiveness_metrics(storage)
    assert metrics["injection_coverage"] == 0.0, "uncovered injection must not count as used"
