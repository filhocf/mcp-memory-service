"""RED tests for harvest re-harvest safety (RFC-harvest-provenance Phase 2).

R7: scheduler tracker only marks sessions with stored>0.
R9: _try_evolve stamps harvest:method tag (fixes Phase 1 gap where evolved
    memories lacked provenance).
R8: force_reharvest ignores the tracker.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp_memory_service.harvest.harvester import SessionHarvester
from mcp_memory_service.harvest.models import HarvestConfig, HarvestCandidate, HarvestResult


def _mk_result(session_id, stored, found=None):
    return HarvestResult(candidates=[], session_id=session_id,
                         total_messages=1, found=found if found is not None else stored,
                         by_type={}, stored=stored)


# --- R7: tracker only marks stored>0 -----------------------------------------

def test_tracker_selects_only_sessions_with_stored(monkeypatch):
    """R7: helper that computes tracker additions must exclude stored==0 sessions."""
    from mcp_memory_service.consolidation import scheduler as sch

    # The Phase 2 contract: a pure helper returns only session ids with stored>0.
    results = [
        _mk_result("sess-A", stored=3),
        _mk_result("sess-B", stored=0),   # LLM failed / nothing stored → must NOT be tracked
        _mk_result("sess-C", stored=1),
    ]
    marked = sch.sessions_to_track(results)
    assert marked == {"sess-A", "sess-C"}, f"stored==0 leaked into tracker: {marked}"


# --- R9: evolve stamps method tag --------------------------------------------

@pytest.mark.asyncio
async def test_evolve_stamps_method_tag(monkeypatch):
    """R9: an evolved memory carries harvest:method:* (Phase 1 gap fix)."""
    svc = MagicMock()
    captured = {}

    async def _update(existing_hash, content, new_tags=None, new_memory_type=None, reason=None):
        captured["tags"] = new_tags
        return True, "ok", "newhash"

    svc.storage = MagicMock()
    svc.storage.update_memory_versioned = AsyncMock(side_effect=_update)
    # similar match above threshold → evolve path
    sim = MagicMock()
    sim.relevance_score = 0.95
    sim.memory.content_hash = "existinghash"
    svc.storage.retrieve = AsyncMock(return_value=[sim])

    harvester = SessionHarvester(project_dir="/tmp", memory_service=svc)
    cand = HarvestCandidate(content="insight", memory_type="decision",
                            tags=["harvest:decision"], confidence=0.8,
                            harvest_method="llm", harvest_model="deepseek/deepseek-chat")
    cfg = HarvestConfig(sessions=1, similarity_threshold=0.85)

    evolved = await harvester._try_evolve(cand, cfg)
    assert evolved is True
    assert captured["tags"] is not None
    assert "harvest:method:llm" in captured["tags"], f"R9: evolve missing method tag: {captured['tags']}"
    assert "session-harvest" in captured["tags"]
