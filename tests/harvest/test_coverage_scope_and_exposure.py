"""Adversarial tests for PR #1423 coverage visibility (Gate 5 independent review).

Goal: try to BREAK the three coverage scope fixes, not merely re-assert them.

Per-session reset: coverage exposed on BOTH MCP (server_impl.handle_memory_harvest) and
      HTTP (web.api.harvest.harvest_sessions) response paths.
Empty coverage logging: empty coverage logs an explicit 'none measured' line (not silence,
      not spurious when there IS coverage).
Per-run scope: parser.reset_coverage() scopes coverage per-run WITHOUT killing the
      intra-run accumulation across the N sessions of a single run.

These complement tests/harvest/test_coverage_response_exposure.py by attacking
the edges the happy-path tests do not: empty run AFTER a non-empty run on the
same harvester, multi-session summation inside one run, and log spuriousness.
"""

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mcp_memory_service.harvest.harvester import SessionHarvester
from mcp_memory_service.harvest.models import HarvestConfig
from mcp_memory_service.server import MemoryServer


def _write_session(tmp_path: Path, session_id: str, lines: list) -> Path:
    session_file = tmp_path / f"{session_id}.jsonl"
    session_file.write_text(
        "".join(json.dumps(line) + "\n" for line in lines),
        encoding="utf-8",
    )
    return session_file


def _text_session(text: str) -> list:
    return [
        {"kind": "AssistantMessage", "data": {"content": [
            {"kind": "text", "data": text}
        ]}}
    ]


# ---------------------------------------------------------------------------
# (a) run A (with counters) then run B EMPTY on the SAME harvester:
#     B.coverage must NOT carry A's counters.
# ---------------------------------------------------------------------------
def test_a_empty_run_after_nonempty_does_not_inherit_counters(tmp_path):
    harvester = SessionHarvester(project_dir=tmp_path)

    # Run A: real text content -> non-empty coverage.
    _write_session(tmp_path, "runA", _text_session("A design decision worth harvesting."))
    cfgA = HarvestConfig(project_path=str(tmp_path), session_ids=["runA"], dry_run=True)
    resA = harvester.harvest(cfgA)
    assert resA[0].coverage, "run A should produce non-empty coverage"
    assert resA[0].coverage["text"]["seen"] >= 1

    # Run B on the SAME harvester: a session with NOTHING parseable -> empty coverage.
    _write_session(tmp_path, "runB", [{"garbage": "no recognizable kind"}])
    cfgB = HarvestConfig(project_path=str(tmp_path), session_ids=["runB"], dry_run=True)
    resB = harvester.harvest(cfgB)

    # The regression (persistent parser state) would leak A's "text" counter into B.
    covB = resB[0].coverage
    assert covB == {}, f"empty run B must not inherit run A counters, got {covB}"


# ---------------------------------------------------------------------------
# (b) run with N sessions -> coverage SUMS across the N (reset does not kill
#     intra-run accumulation).
# ---------------------------------------------------------------------------
def test_b_multisession_run_sums_coverage_across_sessions(tmp_path):
    harvester = SessionHarvester(project_dir=tmp_path)

    N = 3
    for i in range(N):
        _write_session(tmp_path, f"s{i}", _text_session(f"Decision number {i} to harvest."))

    cfg = HarvestConfig(
        project_path=str(tmp_path),
        session_ids=[f"s{i}" for i in range(N)],
        dry_run=True,
    )
    results = harvester.harvest(cfg)
    assert len(results) == N

    # Coverage is per-session now, so each result has its own coverage
    for i, result in enumerate(results):
        cov = result.coverage
        assert "text" in cov, f"expected text kind in per-session coverage, got {cov}"
        assert cov["text"]["seen"] == 1, (
            f"per-session coverage broken: expected 1 text block seen for session {i}, got {cov['text']['seen']}"
        )


def test_b_two_runs_consecutive_do_not_accumulate(tmp_path):
    """Direct per-run reset test: two runs on same harvester, second must equal a fresh run."""
    harvester = SessionHarvester(project_dir=tmp_path)

    _write_session(tmp_path, "first", _text_session("First run content here."))
    cfg1 = HarvestConfig(project_path=str(tmp_path), session_ids=["first"], dry_run=True)
    cov1 = harvester.harvest(cfg1)[0].coverage
    seen1 = cov1["text"]["seen"]

    _write_session(tmp_path, "second", _text_session("Second run content here."))
    cfg2 = HarvestConfig(project_path=str(tmp_path), session_ids=["second"], dry_run=True)
    cov2 = harvester.harvest(cfg2)[0].coverage

    assert cov2["text"]["seen"] == seen1, (
        f"run 2 accumulated: run1={seen1}, run2={cov2['text']['seen']}"
    )


# ---------------------------------------------------------------------------
# (c) BOTH response paths (HTTP + MCP) carry non-None coverage when data exists.
# ---------------------------------------------------------------------------
def test_c_http_path_carries_nonnull_coverage(tmp_path, monkeypatch):
    import asyncio
    from mcp_memory_service.web.api.harvest import harvest_sessions, HarvestRequest

    claude_projects = tmp_path / ".claude" / "projects"
    project_dir = claude_projects / "proj"
    project_dir.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))

    _write_session(project_dir, "httpsess", _text_session("Design decision over HTTP path."))
    request = HarvestRequest(project_path="proj", session_ids=["httpsess"], dry_run=True)

    response = asyncio.run(harvest_sessions(request))
    assert response["results"], "HTTP path returned no results"
    cov = response["results"][0]["coverage"]
    assert cov is not None and cov != {}, f"HTTP coverage missing/empty: {cov!r}"
    assert "text" in cov


@pytest.mark.asyncio
async def test_c_mcp_path_carries_nonnull_coverage(tmp_path):
    server = MemoryServer()
    _write_session(tmp_path, "mcpsess", _text_session("Design decision over MCP path."))

    with patch.object(server, "_ensure_storage_initialized", new_callable=AsyncMock) as mock_init:
        mock_init.return_value = None
        result = await server.handle_memory_harvest({
            "project_path": str(tmp_path),
            "session_ids": ["mcpsess"],
            "dry_run": True,
        })

    payload = json.loads(result[0].text)
    assert payload["results"], "MCP path returned no results"
    cov = payload["results"][0]["coverage"]
    assert cov is not None and cov != {}, f"MCP coverage missing/empty: {cov!r}"
    assert "text" in cov


# ---------------------------------------------------------------------------
# (d) empty coverage -> field present AND 'none measured' log line emitted,
#     and NOT emitted spuriously when coverage IS present.
# ---------------------------------------------------------------------------
def test_d_empty_coverage_field_present_and_logged(tmp_path, caplog):
    harvester = SessionHarvester(project_dir=tmp_path)
    _write_session(tmp_path, "empty", [{"garbage": "unparseable"}])
    cfg = HarvestConfig(project_path=str(tmp_path), session_ids=["empty"], dry_run=True)

    with caplog.at_level(logging.INFO):
        results = harvester.harvest(cfg)

    # Field is present and consistently empty-dict (not None, not missing).
    assert results[0].coverage == {}

    msgs = [r.message for r in caplog.records if r.levelname == "INFO"]
    none_measured = [m for m in msgs if "none measured" in m.lower() or "no counters" in m.lower()]
    assert none_measured, f"expected explicit empty-coverage log, got INFO msgs: {msgs}"
    # Guard against spuriousness: exactly one such line for one run.
    assert len(none_measured) == 1, f"expected 1 'none measured' line, got {len(none_measured)}: {none_measured}"


def test_d_nonempty_coverage_does_not_log_none_measured(tmp_path, caplog):
    """The 'none measured' line must NOT appear when there IS coverage (anti-spurious)."""
    harvester = SessionHarvester(project_dir=tmp_path)
    _write_session(tmp_path, "real", _text_session("Real content producing coverage."))
    cfg = HarvestConfig(project_path=str(tmp_path), session_ids=["real"], dry_run=True)

    with caplog.at_level(logging.INFO):
        harvester.harvest(cfg)

    msgs = [r.message for r in caplog.records if r.levelname == "INFO"]
    none_measured = [m for m in msgs if "none measured" in m.lower() or "no counters" in m.lower()]
    assert not none_measured, f"spurious 'none measured' log with real coverage: {none_measured}"
    # And the real coverage summary line SHOULD be present.
    assert any("coverage" in m.lower() for m in msgs), f"expected a coverage summary line, got {msgs}"


# ===========================================================================
# Gate 5 reviewer (Tuvok) adversarials — Henry's three explicit requirements:
#   (a) 3 sessions, DIFFERENT kinds -> each result.coverage isolated AND the
#       run aggregate (helper) equals the exact sum, including the `languages`
#       sub-dict.
#   (b) harvest_and_store (async, asyncio.to_thread in the loop) is per-session
#       and the reset mid-loop does NOT leak counters between sessions.
#   (c) HTTP and MCP responses carry the PER-SESSION coverage, NOT the run
#       aggregate (prove by value, not merely non-null).
# ===========================================================================


def _toolresult_session(text: str) -> list:
    """A ToolResult block — dropped (not harvested) but recorded in coverage."""
    return [
        {"kind": "ToolResult", "data": {"content": [
            {"kind": "text", "data": text}
        ]}}
    ]


def test_rev_a_three_sessions_distinct_kinds_isolated_and_sum(tmp_path):
    """3 sessions with distinct kind mixes: each result.coverage reflects ONLY
    its own session, and _aggregate_coverage_from_sessions equals the exact
    element-wise sum (seen/extracted/dropped AND the languages sub-dict)."""
    harvester = SessionHarvester(project_dir=tmp_path)

    # s0: one AssistantMessage text (extracted, pt-BR) ; s1: two ToolResults
    # (dropped) ; s2: one text (extracted) + one ToolResult (dropped).
    _write_session(tmp_path, "s0", _text_session(
        "Decisão de arquitetura importante que não deve ser perdida para análise."
    ))
    _write_session(tmp_path, "s1",
        _toolresult_session("tool output one") + _toolresult_session("tool output two"))
    _write_session(tmp_path, "s2",
        _text_session("The analysis decision should be kept before changing anything.")
        + _toolresult_session("another tool output"))

    cfg = HarvestConfig(
        project_path=str(tmp_path),
        session_ids=["s0", "s1", "s2"],
        dry_run=True,
    )
    results = harvester.harvest(cfg)
    assert len(results) == 3
    cov0, cov1, cov2 = (r.coverage for r in results)

    # --- Isolation: each session sees ONLY its own kinds. ---
    assert "text" in cov0 and "ToolResult" not in cov0
    assert cov0["text"]["seen"] == 1 and cov0["text"]["extracted"] == 1

    assert "ToolResult" in cov1 and "text" not in cov1
    assert cov1["ToolResult"]["seen"] == 2 and cov1["ToolResult"]["dropped"] == 2

    assert "text" in cov2 and "ToolResult" in cov2
    assert cov2["text"]["seen"] == 1
    assert cov2["ToolResult"]["seen"] == 1

    # --- Aggregate equals the EXACT element-wise sum. ---
    agg = harvester._aggregate_coverage_from_sessions(results)
    assert agg["text"]["seen"] == 2          # s0 + s2
    assert agg["text"]["extracted"] == 2
    assert agg["ToolResult"]["seen"] == 3    # s1(2) + s2(1)
    assert agg["ToolResult"]["dropped"] == 3

    # languages sub-dict aggregated: pt from s0, en from s2 (both EXTRACTED text).
    text_langs = agg["text"]["languages"]["extracted"]
    total_lang_hits = sum(text_langs.values())
    assert total_lang_hits == 2, f"languages sub-dict not summed: {text_langs}"
    # Element-wise: the aggregate language counts must match the per-session sum.
    expected = {}
    for cov in (cov0, cov2):
        for lang, n in cov["text"]["languages"]["extracted"].items():
            expected[lang] = expected.get(lang, 0) + n
    assert text_langs == expected, f"lang aggregate {text_langs} != per-session sum {expected}"


@pytest.mark.asyncio
async def test_rev_b_store_path_per_session_no_leak_across_tothread(tmp_path):
    """harvest_and_store(): the reset lives BEFORE asyncio.to_thread inside the
    loop. Prove the offloaded _harvest_file does not let session N's counters
    leak into session N+1's result."""
    harvester = SessionHarvester(project_dir=tmp_path)

    _write_session(tmp_path, "a",
        _toolresult_session("x1") + _toolresult_session("x2") + _toolresult_session("x3"))
    _write_session(tmp_path, "b", _text_session("Lone harvestable decision here."))

    cfg = HarvestConfig(project_path=str(tmp_path), session_ids=["a", "b"], dry_run=True)
    results = await harvester.harvest_and_store(cfg)
    assert len(results) == 2
    covA, covB = results[0].coverage, results[1].coverage

    # A: three ToolResults, zero text.
    assert covA["ToolResult"]["seen"] == 3
    assert "text" not in covA
    # B: one text, ZERO ToolResult (no leak of A's 3 across the to_thread boundary).
    assert covB["text"]["seen"] == 1
    assert "ToolResult" not in covB, f"A's ToolResult leaked into B: {covB}"
    # Distinct objects.
    assert covA is not covB


def test_rev_c_http_response_is_per_session_not_aggregate(tmp_path, monkeypatch):
    """HTTP response must carry EACH session's own coverage, not the run sum.
    Two text sessions -> each result.coverage['text']['seen'] == 1, never 2."""
    import asyncio
    from mcp_memory_service.web.api.harvest import harvest_sessions, HarvestRequest

    claude_projects = tmp_path / ".claude" / "projects"
    project_dir = claude_projects / "proj"
    project_dir.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))

    _write_session(project_dir, "h1", _text_session("First HTTP decision to harvest."))
    _write_session(project_dir, "h2", _text_session("Second HTTP decision to harvest."))
    request = HarvestRequest(project_path="proj", session_ids=["h1", "h2"], dry_run=True)

    response = asyncio.run(harvest_sessions(request))
    assert len(response["results"]) == 2
    for r in response["results"]:
        cov = r["coverage"]
        assert cov and cov["text"]["seen"] == 1, (
            f"HTTP coverage is aggregated, expected per-session seen==1, got {cov}"
        )


@pytest.mark.asyncio
async def test_rev_c_mcp_response_is_per_session_not_aggregate(tmp_path):
    """MCP response must carry EACH session's own coverage, not the run sum."""
    server = MemoryServer()
    _write_session(tmp_path, "m1", _text_session("First MCP decision to harvest."))
    _write_session(tmp_path, "m2", _text_session("Second MCP decision to harvest."))

    with patch.object(server, "_ensure_storage_initialized", new_callable=AsyncMock) as mock_init:
        mock_init.return_value = None
        result = await server.handle_memory_harvest({
            "project_path": str(tmp_path),
            "session_ids": ["m1", "m2"],
            "dry_run": True,
        })

    payload = json.loads(result[0].text)
    assert len(payload["results"]) == 2
    for r in payload["results"]:
        cov = r["coverage"]
        assert cov and cov["text"]["seen"] == 1, (
            f"MCP coverage is aggregated, expected per-session seen==1, got {cov}"
        )
