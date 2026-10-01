"""Harvest-level triage gate: triage_enabled drops low-value sessions (C3a).

Proves the triage is actually wired into SessionHarvester.harvest(), not just
available standalone. Default-off is covered by the rest of the suite staying green.
"""
import json
import pytest

from mcp_memory_service.harvest.harvester import SessionHarvester
from mcp_memory_service.harvest.models import HarvestConfig


def _write(tmp_path, name, records):
    # flat layout at project root: find_sessions picks up *.jsonl here
    fp = tmp_path / f"{name}.jsonl"
    fp.write_text("\n".join(json.dumps(r) for r in records))
    return fp


def _user(t): return {"payload": {"type": "user", "content": t}}
def _asst(t): return {"payload": {"type": "assistant", "content": t}}

PROSE = "x" * 400


@pytest.mark.unit
def test_harvest_triage_drops_test_session(tmp_path):
    # One real conversation (keep) + one smoke test (drop)
    _write(tmp_path, "real_session",
           [_user("kiro, me ajuda a entender esse bug? " + PROSE), _asst("claro, " + PROSE)])
    _write(tmp_path, "test_session",
           [_user("respond with just 'hello v3'"), _asst("hello v3")])

    h = SessionHarvester(tmp_path)

    # triage OFF (default) → both sessions parsed (unchanged behavior)
    off = h.harvest(HarvestConfig(triage_enabled=False, sessions=10))
    assert len(off) == 2, f"triage off should parse both, got {len(off)}"

    # triage ON → the smoke-test session is dropped, the real one kept
    on = h.harvest(HarvestConfig(triage_enabled=True, triage_threshold=0.25, sessions=10))
    assert len(on) < len(off), "triage on must drop at least the smoke-test session"
    ids_on = {r.session_id for r in on}
    assert any("real" in i for i in ids_on), f"real session must survive triage, got {ids_on}"
    assert not any("test_session" in i for i in ids_on), "smoke-test session must be dropped"
