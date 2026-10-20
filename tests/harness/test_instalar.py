"""Tests for scripts/harness/instalar.py — the multi-harness installer.

Every test runs against tmp_path: the developer's real ~/.hermes and ~/.kiro are
never touched. The load-bearing cases are the ones the sandbox run exposed:

* `uninstall` must remove the server BY KEY, never delete the harness config
  (doing so would take the other 13 servers with it);
* the manifest must not list a config file the installer merely edited.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "harness"))


def _mod():
    return importlib.import_module("instalar")


# --- detection ---------------------------------------------------------------


def test_detect_finds_only_existing_roots(tmp_path):
    instalar = _mod()
    roots = {"hermes": tmp_path / "hermes", "kiro": tmp_path / "kiro"}
    (tmp_path / "kiro").mkdir()

    assert instalar.detect(roots) == ["kiro"]


# --- planning ----------------------------------------------------------------


def test_plan_is_empty_when_everything_is_installed(tmp_path):
    instalar = _mod()
    harness = instalar.harnesses()["kiro"]
    actions = instalar.plan_for(harness, tmp_path, 3202, installed=True, cli_present=False)
    # `installed` only covers the MCP registration; the file surfaces depend on
    # the files existing. Materialise them, then the plan must be empty.
    for action in actions:
        assert action.target is not None
        action.target.parent.mkdir(parents=True, exist_ok=True)
        action.target.write_text("x")

    again = instalar.plan_for(harness, tmp_path, 3202, installed=True, cli_present=False)

    assert again == [], "maquina ja instalada nao pode gerar acao"


def test_plan_covers_every_surface_on_a_clean_machine(tmp_path):
    instalar = _mod()
    harness = instalar.harnesses()["kiro"]
    actions = instalar.plan_for(harness, tmp_path, 3202, installed=False, cli_present=False)

    kinds = [a.kind for a in actions]
    assert "merge-mcp" in kinds
    assert kinds.count("copy") == 2, "steering + skill"
    targets = {str(a.target) for a in actions if a.target}
    assert any("steering" in t for t in targets)
    assert any("skills" in t for t in targets)


def test_hermes_plans_a_cli_registration_and_a_hook(tmp_path):
    instalar = _mod()
    harness = instalar.harnesses()["hermes"]
    actions = instalar.plan_for(harness, tmp_path, 3202, installed=False, cli_present=False)

    cli = [a for a in actions if a.kind == "cli"]
    assert cli and cli[0].argv[:3] == ["hermes", "mcp", "add"]
    assert any(a.kind == "copy" and "agent-hooks" in str(a.target) for a in actions)


def test_cost_skill_is_not_part_of_the_payload(tmp_path):
    instalar = _mod()
    harness = instalar.harnesses()["kiro"]
    actions = instalar.plan_for(harness, tmp_path, 3202, installed=False, cli_present=False)

    assert not any("custo" in a.render() for a in actions)


# --- config merge ------------------------------------------------------------


def test_merge_preserves_other_servers(tmp_path):
    instalar = _mod()
    config = tmp_path / "settings" / "mcp.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"mcpServers": {"outro": {"url": "http://x"}}}))

    instalar.merge_mcp(config, 3202)

    servers = json.loads(config.read_text())["mcpServers"]
    assert servers["outro"] == {"url": "http://x"}
    assert servers["mms"]["url"] == "http://localhost:3202/mcp"


def test_merge_does_not_autoapprove_inventory_tools(tmp_path):
    instalar = _mod()
    config = tmp_path / "settings" / "mcp.json"

    instalar.merge_mcp(config, 3202)

    approved = json.loads(config.read_text())["mcpServers"]["mms"]["autoApprove"]
    assert "memory_list" not in approved
    assert "memory_context" not in approved
    assert "memory_search" in approved


def test_merge_refuses_to_destroy_invalid_json(tmp_path):
    instalar = _mod()
    config = tmp_path / "settings" / "mcp.json"
    config.parent.mkdir(parents=True)
    config.write_text("{ nao e json")

    with pytest.raises(RuntimeError):
        instalar.merge_mcp(config, 3202)


# --- manifest + uninstall (the destructive bug) ------------------------------


def test_manifest_does_not_list_the_config_file(tmp_path):
    """A merged config is edited, never created by us — listing it deletes it."""
    instalar = _mod()
    harness = instalar.harnesses()["kiro"]
    actions = instalar.plan_for(harness, tmp_path, 3202, installed=False, cli_present=False)

    instalar.write_manifest(tmp_path, actions)

    created = json.loads((tmp_path / instalar.MANIFEST_NAME).read_text())["created"]
    assert not any(entry.endswith("mcp.json") for entry in created)


def test_uninstall_removes_only_the_server_and_keeps_the_rest(tmp_path):
    instalar = _mod()
    harness = instalar.harnesses()["kiro"]
    config = tmp_path / "settings" / "mcp.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"mcpServers": {"outro": {"url": "http://x"}}}))
    instalar.merge_mcp(config, 3202)
    steering = tmp_path / "steering" / "mms.md"
    steering.parent.mkdir(parents=True)
    steering.write_text("doutrina")
    instalar.write_manifest(
        tmp_path,
        [instalar.Action(kind="copy", description="steering", target=steering)],
    )

    instalar.uninstall(harness, tmp_path)

    assert config.is_file(), "o config do harness nao pode ser apagado"
    servers = json.loads(config.read_text())["mcpServers"]
    assert servers == {"outro": {"url": "http://x"}}
    assert not steering.exists()


def test_uninstall_survives_a_corrupted_manifest(tmp_path):
    """A corrupted manifest must not raise; the uninstall still completes."""
    instalar = _mod()
    harness = instalar.harnesses()["kiro"]
    (tmp_path / instalar.MANIFEST_NAME).write_text("<<< not json >>>")

    removed = instalar.uninstall(harness, tmp_path)

    assert isinstance(removed, list), "uninstall precisa concluir sem excecao"


# --- end to end in a sandbox -------------------------------------------------


def test_install_then_reinstall_is_a_noop_then_uninstall_cleans(tmp_path):
    instalar = _mod()
    harness = instalar.harnesses()["kiro"]

    rc = instalar.main(["--harness", "kiro", "--root", str(tmp_path), "--skip-health"])
    assert rc == 0
    assert (tmp_path / "settings" / "mcp.json").is_file()
    assert (tmp_path / "steering" / "mms.md").is_file()
    assert (tmp_path / "skills" / "mms-uso" / "SKILL.md").is_file()

    second = instalar.plan_for(harness, tmp_path, 3202, installed=True, cli_present=False)
    assert second == []

    rc = instalar.main(
        ["--harness", "kiro", "--root", str(tmp_path), "--uninstall"]
    )
    assert rc == 0
    assert json.loads((tmp_path / "settings" / "mcp.json").read_text())["mcpServers"] == {}
    assert not (tmp_path / "steering" / "mms.md").exists()


def test_dry_run_writes_nothing(tmp_path):
    instalar = _mod()

    rc = instalar.main(
        ["--harness", "kiro", "--root", str(tmp_path), "--skip-health", "--dry-run"]
    )

    assert rc == 0
    assert list(tmp_path.rglob("*")) == [], "dry-run nao pode escrever"


# --- registration must be usable, not merely present -------------------------


def test_entry_is_usable_rejects_wrong_port_and_disabled(tmp_path):
    """The Greptile P1: name-only matching accepted a stale or disabled entry."""
    instalar = _mod()

    good = {"url": "http://localhost:8000/mcp"}
    wrong_port = {"url": "http://localhost:9999/mcp"}
    disabled = {"url": "http://localhost:8000/mcp", "disabled": True}

    assert instalar.entry_is_usable(good, 8000) is True
    assert instalar.entry_is_usable(wrong_port, 8000) is False
    assert instalar.entry_is_usable(disabled, 8000) is False
    assert instalar.entry_is_usable({}, 8000) is False


def test_merge_sends_bearer_when_api_key_is_set(tmp_path, monkeypatch):
    instalar = _mod()
    config = tmp_path / "settings" / "mcp.json"
    monkeypatch.setenv("MCP_API_KEY", "s3cret")

    instalar.merge_mcp(config, 8000)

    entry = json.loads(config.read_text())["mcpServers"]["mms"]
    assert entry["headers"]["Authorization"] == "Bearer s3cret"


def test_merge_omits_headers_without_a_key(tmp_path, monkeypatch):
    instalar = _mod()
    config = tmp_path / "settings" / "mcp.json"
    monkeypatch.delenv("MCP_API_KEY", raising=False)

    instalar.merge_mcp(config, 8000)

    assert "headers" not in json.loads(config.read_text())["mcpServers"]["mms"]


def test_uninstall_works_with_the_service_down(tmp_path):
    """Uninstalling must not require a reachable server — often it is the reason."""
    instalar = _mod()
    instalar.main(["--harness", "kiro", "--root", str(tmp_path), "--skip-health"])
    (tmp_path / "settings" / "mcp.json").is_file()

    rc = instalar.main(
        ["--harness", "kiro", "--root", str(tmp_path), "--port", "1", "--uninstall"]
    )

    assert rc == 0, "uninstall nao pode depender do servico no ar"
