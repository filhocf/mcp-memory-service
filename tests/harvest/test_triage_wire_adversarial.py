"""Adversarial tests for the triage-wire fix (Gate 5 / JiTTesting).

These tests try to BREAK the fix that swapped HarvestConfig(...) for
harvest_config_from_env(...) at the harvest entry call-sites. They attack:

(a) env absent  -> triage_enabled is False at every call-site (opt-in default)
(b) MCP_HARVEST_TRIAGE=1 (and other truthy spellings) -> True
(c) garbage env values do not explode and fall back to a SAFE default
(d) call-site overrides survive the factory (defaults.update(overrides))
(e) a valid threshold in the env is honored, overrides still win on conflict

The design contract (from the manager):
  - Default MUST stay OFF (opt-in). Only MCP_HARVEST_TRIAGE in
    {1,true,yes,on} (case-insensitive, stripped) turns it on.
  - No call-site kwarg (sessions, dry_run, use_llm, min_confidence,
    project_path, force_reharvest, session_ids, types) may be lost.
"""

import asyncio
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_memory_service.harvest.models import HarvestConfig, harvest_config_from_env


TRIAGE_ENV = ("MCP_HARVEST_TRIAGE", "MCP_HARVEST_TRIAGE_THRESHOLD")


@pytest.fixture(autouse=True)
def _clean_triage_env(monkeypatch):
    """Each test starts with a pristine env — no triage vars leaking in."""
    for var in TRIAGE_ENV:
        monkeypatch.delenv(var, raising=False)
    yield


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# (a) env absent -> opt-in default OFF
# ---------------------------------------------------------------------------

class TestDefaultOff:
    def test_factory_default_off(self):
        cfg = harvest_config_from_env()
        assert cfg.triage_enabled is False
        assert cfg.triage_threshold == 0.25

    def test_default_off_even_with_other_overrides(self):
        # Passing unrelated overrides must not accidentally turn triage on.
        cfg = harvest_config_from_env(sessions=5, dry_run=False, use_llm=True)
        assert cfg.triage_enabled is False

    def test_dataclass_default_is_off(self):
        # Sanity: the dataclass itself defaults off, so any call-site that
        # (wrongly) reverted to HarvestConfig() would also be off — the risk
        # is the reverse (silently ON), which the truthy tests below guard.
        assert HarvestConfig().triage_enabled is False


# ---------------------------------------------------------------------------
# (b) truthy spellings -> ON
# ---------------------------------------------------------------------------

class TestTruthyOn:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "True", "yes", "YES", "on", "ON", " on ", "  1  "])
    def test_truthy_values_enable(self, monkeypatch, value):
        monkeypatch.setenv("MCP_HARVEST_TRIAGE", value)
        cfg = harvest_config_from_env()
        assert cfg.triage_enabled is True, f"{value!r} should enable triage"

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "2", "maybe", "disabled", "yes please", "trueish", "onnn"])
    def test_non_truthy_values_stay_off(self, monkeypatch, value):
        monkeypatch.setenv("MCP_HARVEST_TRIAGE", value)
        cfg = harvest_config_from_env()
        assert cfg.triage_enabled is False, f"{value!r} must NOT enable triage"


# ---------------------------------------------------------------------------
# (c) garbage env values -> no explosion, safe fallback
# ---------------------------------------------------------------------------

class TestGarbageSafety:
    def test_garbage_threshold_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("MCP_HARVEST_TRIAGE_THRESHOLD", "abc")
        cfg = harvest_config_from_env()  # must not raise
        assert cfg.triage_threshold == 0.25  # default preserved

    @pytest.mark.parametrize("junk", ["abc", "", "0.1.2", "NaNaN", "1e", "True", "null", "  "])
    def test_assorted_garbage_thresholds_do_not_raise(self, monkeypatch, junk):
        monkeypatch.setenv("MCP_HARVEST_TRIAGE_THRESHOLD", junk)
        cfg = harvest_config_from_env()
        # Either falls back to default or (for parseable floats) a float.
        assert isinstance(cfg.triage_threshold, float)

    def test_garbage_triage_flag_does_not_raise_and_stays_off(self, monkeypatch):
        monkeypatch.setenv("MCP_HARVEST_TRIAGE", "maybe")
        monkeypatch.setenv("MCP_HARVEST_TRIAGE_THRESHOLD", "abc")
        cfg = harvest_config_from_env(sessions=3)
        assert cfg.triage_enabled is False
        assert cfg.triage_threshold == 0.25
        assert cfg.sessions == 3

    def test_nan_inf_are_technically_parseable_floats(self, monkeypatch):
        # float("nan")/float("inf") parse without ValueError. Documenting the
        # real behavior: these DO get through. Not a crash, but a value a
        # stricter validation might reject. Captured as behavior, not failure.
        monkeypatch.setenv("MCP_HARVEST_TRIAGE_THRESHOLD", "nan")
        cfg = harvest_config_from_env()
        assert isinstance(cfg.triage_threshold, float)
        assert cfg.triage_threshold != cfg.triage_threshold  # nan != nan


# ---------------------------------------------------------------------------
# (d) overrides survive the factory and WIN on conflict
# ---------------------------------------------------------------------------

class TestOverridesSurvive:
    def test_all_call_site_kwargs_preserved(self, monkeypatch):
        monkeypatch.setenv("MCP_HARVEST_TRIAGE", "1")
        cfg = harvest_config_from_env(
            sessions=7,
            session_ids=["a", "b"],
            types=["decision", "bug"],
            min_confidence=0.42,
            dry_run=False,
            project_path="/tmp/zzz",
            use_llm=True,
            force_reharvest=True,
        )
        assert cfg.sessions == 7
        assert cfg.session_ids == ["a", "b"]
        assert cfg.types == ["decision", "bug"]
        assert cfg.min_confidence == 0.42
        assert cfg.dry_run is False
        assert cfg.project_path == "/tmp/zzz"
        assert cfg.use_llm is True
        assert cfg.force_reharvest is True
        # triage still honored from env, independent of the overrides
        assert cfg.triage_enabled is True

    def test_override_threshold_beats_env_threshold(self, monkeypatch):
        # defaults.update(overrides) => an explicit triage_threshold override
        # must win over the env value.
        monkeypatch.setenv("MCP_HARVEST_TRIAGE_THRESHOLD", "0.9")
        cfg = harvest_config_from_env(triage_threshold=0.1)
        assert cfg.triage_threshold == 0.1

    def test_override_triage_enabled_beats_env(self, monkeypatch):
        # Explicit triage_enabled=False override must win even if env says on.
        monkeypatch.setenv("MCP_HARVEST_TRIAGE", "1")
        cfg = harvest_config_from_env(triage_enabled=False)
        assert cfg.triage_enabled is False

    def test_override_triage_enabled_true_without_env(self):
        # A call-site can force it on explicitly even with no env.
        cfg = harvest_config_from_env(triage_enabled=True)
        assert cfg.triage_enabled is True


# ---------------------------------------------------------------------------
# (e) valid threshold honored
# ---------------------------------------------------------------------------

class TestValidThreshold:
    @pytest.mark.parametrize("raw,expected", [("0.35", 0.35), ("0", 0.0), ("1", 1.0), ("0.5", 0.5), ("1.5", 1.5), ("-0.2", -0.2)])
    def test_valid_threshold_parsed(self, monkeypatch, raw, expected):
        monkeypatch.setenv("MCP_HARVEST_TRIAGE_THRESHOLD", raw)
        cfg = harvest_config_from_env()
        assert cfg.triage_threshold == expected

    def test_threshold_without_flag_does_not_enable(self, monkeypatch):
        # Setting only the threshold must NOT enable triage.
        monkeypatch.setenv("MCP_HARVEST_TRIAGE_THRESHOLD", "0.4")
        cfg = harvest_config_from_env()
        assert cfg.triage_enabled is False
        assert cfg.triage_threshold == 0.4


# ---------------------------------------------------------------------------
# Integration: drive the REAL consolidation handler call-site end to end.
# This exercises the actual swapped line (server/handlers/consolidation.py),
# not just the factory in isolation.
# ---------------------------------------------------------------------------

class TestConsolidationHandlerIntegration:
    def _drive(self, monkeypatch, tmpdir):
        from mcp_memory_service.server.handlers.consolidation import (
            handle_memory_consolidate,
        )

        server = MagicMock()
        server.storage = AsyncMock()
        monkeypatch.setenv("MCP_HARVEST_ALLOWED_ROOTS", tmpdir)

        captured = {}

        def capture(*args, **kwargs):
            captured["cfg"] = kwargs.get("cfg") or (args[0] if args else None)
            return AsyncMock(return_value=[SimpleNamespace(candidates=[], stored=0)])()

        with patch("mcp_memory_service.harvest.harvester.SessionHarvester") as mh:
            with patch("mcp_memory_service.services.memory_service.MemoryService"):
                harv = MagicMock()
                harv.harvest_and_store = capture
                mh.return_value = harv
                _run(handle_memory_consolidate(server, {"action": "harvest", "path": tmpdir}))
        return captured.get("cfg")

    def test_handler_off_by_default(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._drive(monkeypatch, tmp)
            assert isinstance(cfg, HarvestConfig)
            assert cfg.triage_enabled is False
            # existing call-site kwargs preserved through the factory
            assert cfg.min_confidence == 0.65
            assert cfg.project_path == tmp

    def test_handler_on_with_env(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("MCP_HARVEST_TRIAGE", "on")
            monkeypatch.setenv("MCP_HARVEST_TRIAGE_THRESHOLD", "0.37")
            cfg = self._drive(monkeypatch, tmp)
            assert cfg.triage_enabled is True
            assert cfg.triage_threshold == 0.37
            # the hardcoded min_confidence override must still win
            assert cfg.min_confidence == 0.65

    def test_handler_garbage_env_does_not_break_handler(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("MCP_HARVEST_TRIAGE", "maybe")
            monkeypatch.setenv("MCP_HARVEST_TRIAGE_THRESHOLD", "abc")
            cfg = self._drive(monkeypatch, tmp)
            assert cfg.triage_enabled is False
            assert cfg.triage_threshold == 0.25
