"""RED tests for SPEC-F005 — X-Agent-ID authorship (installer side).

The installer must stamp a stable identity on both surfaces it writes for
OpenCode: the MCP registration header ``X-Agent-ID`` and the plugin bootstrap
``memoryService.agentId``. These tests describe that contract and fail on the
current implementation, which writes neither.

Every test installs into ``tmp_path`` through ``--root``; neither the real
``~/.config/opencode`` nor a running MMS is touched.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "harness"))

PORT = 39123
URL = f"http://127.0.0.1:{PORT}/mcp"
DEFAULT_AGENT = "opencode"
HEADER = "X-Agent-ID"


# --- helpers -----------------------------------------------------------------


def _mod():
    return importlib.import_module("instalar")


def _install(root: Path, *extra: str) -> int:
    return _mod().main(
        [
            "--harness",
            "opencode",
            "--root",
            str(root),
            "--port",
            str(PORT),
            "--skip-health",
            *extra,
        ]
    )


def _config_path(root: Path) -> Path:
    instalar = _mod()
    return instalar.resolve_mcp_file(instalar.harnesses()["opencode"], root)


def _entry(root: Path) -> dict:
    return _mod().opencode_entry(_config_path(root))


def _header(root: Path) -> object:
    headers = _entry(root).get("headers")
    assert isinstance(headers, dict), f"the mms registration has no headers: {_entry(root)!r}"
    return headers.get(HEADER)


def _plugin_agent_id(root: Path) -> object:
    path = root / "memory-plugin.json"
    assert path.is_file(), "memory-plugin.json was not bootstrapped"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["memoryService"].get("agentId")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    """Neither the developer's env nor a stray key may colour these tests."""
    monkeypatch.delenv("MMS_AGENT_ID", raising=False)
    monkeypatch.delenv("MCP_API_KEY", raising=False)


# --- 1. installer default (R1, AC5) ------------------------------------------


def test_default_install_stamps_opencode_on_both_surfaces(tmp_path):
    assert _install(tmp_path) == 0

    assert _header(tmp_path) == DEFAULT_AGENT, "the MCP registration carries no default X-Agent-ID"
    assert _plugin_agent_id(tmp_path) == DEFAULT_AGENT, (
        "the plugin bootstrap carries no default memoryService.agentId"
    )


# --- 2. installer override (R2, AC2) -----------------------------------------


def test_agent_id_flag_sets_both_surfaces(tmp_path):
    assert _install(tmp_path, "--agent-id", "research-box") == 0

    assert _header(tmp_path) == "research-box"
    assert _plugin_agent_id(tmp_path) == "research-box"


# --- 3. environment default (R5 installer-side) -------------------------------


def test_mms_agent_id_environment_sets_both_surfaces(tmp_path, monkeypatch):
    monkeypatch.setenv("MMS_AGENT_ID", "env-box")

    assert _install(tmp_path) == 0

    assert _header(tmp_path) == "env-box"
    assert _plugin_agent_id(tmp_path) == "env-box"


def test_the_flag_wins_over_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("MMS_AGENT_ID", "env-box")

    assert _install(tmp_path, "--agent-id", "flag-box") == 0

    assert _header(tmp_path) == "flag-box"
    assert _plugin_agent_id(tmp_path) == "flag-box"


# --- 4. trimming -------------------------------------------------------------


def test_agent_id_is_trimmed_before_it_is_written(tmp_path):
    assert _install(tmp_path, "--agent-id", "  research-box  ") == 0

    assert _header(tmp_path) == "research-box"
    assert _plugin_agent_id(tmp_path) == "research-box"


# --- 5. invalid identities fall back and warn (R8) ---------------------------


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("", id="empty"),
        pytest.param("a" * 65, id="65-chars"),
        pytest.param("research\nbox", id="newline"),
    ],
)
def test_invalid_agent_id_falls_back_to_opencode_and_warns(tmp_path, capsys, value):
    rc = _install(tmp_path, "--agent-id", value)

    assert rc == 0, "an invalid identity must not fail the install"
    assert _header(tmp_path) == DEFAULT_AGENT
    assert _plugin_agent_id(tmp_path) == DEFAULT_AGENT
    stderr = capsys.readouterr().err.lower()
    assert "agent" in stderr, f"the invalid identity was accepted silently: {stderr!r}"


# --- 6. legacy installations are upgraded (R7) -------------------------------


LEGACY_CONFIGS = {
    "v2-mcp-servers": """{
  "$schema": "https://opencode.ai/config.json",
  "theme": "dark",
  "mcp": {
    "servers": {
      "mms": {"type": "remote", "url": "%s"},
      "other": {"type": "remote", "url": "http://127.0.0.1:9000/mcp"}
    }
  }
}
"""
    % URL,
    "legacy-mcp-mms": """{
  "$schema": "https://opencode.ai/config.json",
  "theme": "dark",
  "mcp": {
    "mms": {"type": "remote", "url": "%s"},
    "servers": {
      "other": {"type": "remote", "url": "http://127.0.0.1:9000/mcp"}
    }
  }
}
"""
    % URL,
}


@pytest.mark.parametrize("shape", list(LEGACY_CONFIGS))
def test_an_existing_entry_without_the_header_is_upgraded(tmp_path, capsys, shape):
    _write(tmp_path / "opencode.json", LEGACY_CONFIGS[shape])

    assert _install(tmp_path) == 0

    assert _header(tmp_path) == DEFAULT_AGENT, (
        f"the pre-F005 {shape} registration was left without X-Agent-ID"
    )

    data = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert data["theme"] == "dark", "the upgrade dropped an unrelated top-level key"
    other = (data["mcp"].get("servers") or {}).get("other")
    assert other == {"type": "remote", "url": "http://127.0.0.1:9000/mcp"}, (
        "the upgrade rewrote another server"
    )

    before = (tmp_path / "opencode.json").read_bytes()
    capsys.readouterr()  # drop the upgrade run's output

    assert _install(tmp_path) == 0, "the upgraded installation is not idempotent"
    assert (tmp_path / "opencode.json").read_bytes() == before, (
        "the second install rewrote an already-correct registration"
    )
    assert "nothing to do" in capsys.readouterr().out


def test_an_existing_plugin_config_without_agent_id_is_not_rewritten(tmp_path):
    """The plugin, not the installer, owns the fallback for an existing file."""
    original = b'{\n  "memoryService": {"endpoint": "http://127.0.0.1:9999"},\n  "custom": true\n}\n'
    config = tmp_path / "memory-plugin.json"
    config.write_bytes(original)

    assert _install(tmp_path) == 0

    assert config.read_bytes() == original, "the installer rewrote a user-owned plugin config"


# --- B1: --agent-id reaches an existing plugin configuration (R2, §5.1) ------


def test_explicit_agent_id_merges_into_an_existing_plugin_config(tmp_path):
    """Review B1: an existing config swallowed the override entirely."""
    _write(
        tmp_path / "memory-plugin.json",
        json.dumps(
            {
                "memoryService": {"endpoint": "http://127.0.0.1:9999", "timeoutMs": 1234},
                "custom": True,
            },
            indent=2,
        )
        + "\n",
    )

    assert _install(tmp_path, "--agent-id", "research-box") == 0

    data = json.loads((tmp_path / "memory-plugin.json").read_text(encoding="utf-8"))
    assert data["memoryService"]["agentId"] == "research-box", (
        "--agent-id did not reach an existing plugin configuration"
    )
    assert data["memoryService"]["endpoint"] == "http://127.0.0.1:9999"
    assert data["memoryService"]["timeoutMs"] == 1234
    assert data["custom"] is True, "the merge dropped an unrelated top-level key"
    assert _header(tmp_path) == "research-box"


def test_explicit_agent_id_merges_into_the_legacy_plugin_config(tmp_path):
    """Review B1: the legacy memory-awareness.json is the active config here."""
    _write(
        tmp_path / "memory-awareness.json",
        json.dumps(
            {
                "memoryService": {"endpoint": "http://127.0.0.1:8123", "maxMemoriesPerSession": 3},
                "custom": "keep",
            },
            indent=2,
        )
        + "\n",
    )

    assert _install(tmp_path, "--agent-id", "legacy-box") == 0

    assert not (tmp_path / "memory-plugin.json").exists(), (
        "the merge created memory-plugin.json instead of updating the legacy config"
    )
    data = json.loads((tmp_path / "memory-awareness.json").read_text(encoding="utf-8"))
    assert data["memoryService"]["agentId"] == "legacy-box", (
        "--agent-id did not reach the legacy plugin configuration"
    )
    assert data["memoryService"]["endpoint"] == "http://127.0.0.1:8123"
    assert data["memoryService"]["maxMemoriesPerSession"] == 3
    assert data["custom"] == "keep", "the merge dropped an unrelated top-level key"
    assert _header(tmp_path) == "legacy-box"


def test_the_environment_default_never_rewrites_an_existing_plugin_config(tmp_path, monkeypatch):
    """Only an explicit flag may touch a file the operator already owns."""
    original = json.dumps(
        {"memoryService": {"endpoint": "http://127.0.0.1:9999"}, "custom": True}, indent=2
    ) + "\n"
    config = tmp_path / "memory-plugin.json"
    _write(config, original)
    monkeypatch.setenv("MMS_AGENT_ID", "env-box")

    assert _install(tmp_path) == 0

    assert config.read_text(encoding="utf-8") == original, (
        "MMS_AGENT_ID rewrote an existing plugin config without an explicit flag"
    )
    assert _header(tmp_path) == "env-box"


def test_an_invalid_flag_never_rewrites_an_existing_plugin_config(tmp_path, capsys):
    original = json.dumps(
        {"memoryService": {"endpoint": "http://127.0.0.1:9999"}, "custom": True}, indent=2
    ) + "\n"
    config = tmp_path / "memory-plugin.json"
    _write(config, original)

    assert _install(tmp_path, "--agent-id", "a" * 65) == 0

    assert config.read_text(encoding="utf-8") == original, (
        "an invalid --agent-id rewrote the plugin configuration"
    )
    assert _header(tmp_path) == DEFAULT_AGENT
    assert "agent" in capsys.readouterr().err.lower()


def test_a_corrupt_existing_plugin_config_aborts_without_writing(tmp_path, capsys):
    corrupt = '{\n  "memoryService": {"endpoint": "http://127.0.0.1:9999"\n'
    config = tmp_path / "memory-plugin.json"
    _write(config, corrupt)

    rc = _install(tmp_path, "--agent-id", "research-box")

    assert rc != 0, "a config the installer cannot merge must abort the install"
    assert config.read_text(encoding="utf-8") == corrupt, "the corrupt config was overwritten"
    assert not (tmp_path / "opencode.json").exists(), (
        "the MCP registration was written even though the plugin merge failed"
    )
    assert not (tmp_path / "plugins").exists(), "the plugin was deposited after the abort"
    captured = capsys.readouterr()
    output = (captured.out + captured.err).lower()
    assert "json" in output or "config" in output or "configura" in output, (
        f"the abort message does not name the offending configuration: {output!r}"
    )


# --- B2: upgrading an existing registration keeps its headers (§5.1) ---------


def test_upgrading_an_existing_registration_keeps_its_headers_and_keys(tmp_path):
    """Review B2: a naive re-registration dropped the operator's headers."""
    entry = {
        "type": "remote",
        "url": URL,
        "headers": {"Authorization": "Bearer user-token", "X-Custom": "keep-me"},
        "enabled": True,
    }
    _write(
        tmp_path / "opencode.json",
        json.dumps({"theme": "dark", "mcp": {"servers": {"mms": entry}}}, indent=2) + "\n",
    )

    assert _install(tmp_path) == 0

    written = _entry(tmp_path)
    assert _header(tmp_path) == DEFAULT_AGENT, (
        "the upgrade did not add X-Agent-ID to the existing registration"
    )
    assert written["headers"]["Authorization"] == "Bearer user-token", (
        "the upgrade dropped the existing Authorization header"
    )
    assert written["headers"]["X-Custom"] == "keep-me", (
        "the upgrade dropped an existing custom header"
    )
    assert written["enabled"] is True
    data = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert data["theme"] == "dark"


def test_kiro_merge_keeps_existing_headers_and_other_servers(tmp_path):
    instalar = _mod()
    config = tmp_path / "settings" / "mcp.json"
    _write(
        config,
        json.dumps(
            {
                "mcpServers": {
                    "mms": {
                        "url": f"http://localhost:{PORT}/mcp",
                        "headers": {
                            "Authorization": "Bearer kiro-token",
                            "X-Custom": "keep",
                        },
                    },
                    "other": {"url": "http://127.0.0.1:9000/mcp"},
                }
            },
            indent=2,
        )
        + "\n",
    )

    rc = instalar.main(
        ["--harness", "kiro", "--root", str(tmp_path), "--port", str(PORT), "--skip-health"]
    )

    assert rc == 0
    data = json.loads(config.read_text(encoding="utf-8"))
    entry = data["mcpServers"]["mms"]
    assert entry["headers"]["X-Agent-ID"] == DEFAULT_AGENT, (
        "the Kiro registration carries no X-Agent-ID"
    )
    assert entry["headers"]["Authorization"] == "Bearer kiro-token", (
        "the Kiro merge dropped the existing Authorization header"
    )
    assert entry["headers"]["X-Custom"] == "keep", "the Kiro merge dropped a custom header"
    assert data["mcpServers"]["other"] == {"url": "http://127.0.0.1:9000/mcp"}


def test_verify_reports_a_registration_without_the_agent_header(tmp_path):
    """Guard: verify is the post-write effect check, so it must see the header."""
    instalar = _mod()
    assert _install(tmp_path) == 0

    path = _config_path(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    entry = data["mcp"]["servers"]["mms"]
    headers = dict(entry.get("headers") or {})
    headers.pop(HEADER, None)
    if headers:
        entry["headers"] = headers
    else:
        entry.pop("headers", None)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    failures = instalar.verify(instalar.harnesses()["opencode"], tmp_path, PORT)

    assert failures, "verify accepted a registration without X-Agent-ID"
    joined = " ".join(failures).lower()
    assert "x-agent-id" in joined or "header" in joined, (
        f"the failure does not name the missing header: {failures!r}"
    )


def test_an_explicit_agent_id_is_trimmed_into_an_existing_config(tmp_path):
    """A padded --agent-id must be merged trimmed, never as the raw value."""
    original = json.dumps(
        {"memoryService": {"endpoint": "http://127.0.0.1:9999"}, "custom": True}, indent=2
    ) + "\n"
    config = tmp_path / "memory-plugin.json"
    _write(config, original)

    assert _install(tmp_path, "--agent-id", "  research-box  ") == 0

    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["memoryService"]["agentId"] == "research-box", (
        f"the raw value reached the merged config: {data['memoryService']['agentId']!r}"
    )
    assert data["memoryService"]["endpoint"] == "http://127.0.0.1:9999"
    assert data["custom"] is True
    assert _header(tmp_path) == "research-box", (
        f"the raw value reached the MCP header: {_header(tmp_path)!r}"
    )


# --- ownership after an explicit merge (uninstall must not eat edits) --------


def _uninstall(root: Path) -> int:
    return _mod().main(["--harness", "opencode", "--root", str(root), "--uninstall"])


def test_uninstall_preserves_an_edited_installer_config_after_agent_id_merge(tmp_path):
    """Ownership is the hash recorded BEFORE the merge, not the merged bytes."""
    assert _install(tmp_path) == 0
    config = tmp_path / "memory-plugin.json"
    assert config.is_file(), "the clean install did not create the plugin config"
    data = json.loads(config.read_text(encoding="utf-8"))
    data["memoryService"]["endpoint"] = "http://127.0.0.1:7777"
    data["projectNote"] = "mine"
    config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    assert _install(tmp_path, "--agent-id", "research-box") == 0
    assert _uninstall(tmp_path) == 0

    assert config.is_file(), (
        "uninstall deleted a config the operator edited before the merge install"
    )
    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["projectNote"] == "mine", "uninstall dropped the operator's key"
    assert data["memoryService"]["endpoint"] == "http://127.0.0.1:7777", (
        "uninstall reverted the operator's endpoint edit"
    )
    assert data["memoryService"]["agentId"] == "research-box"


def test_uninstall_preserves_a_user_config_after_agent_id_merge(tmp_path):
    original = {
        "memoryService": {"endpoint": "http://127.0.0.1:9999"},
        "custom": True,
        "projectNote": "mine",
    }
    config = tmp_path / "memory-plugin.json"
    _write(config, json.dumps(original, indent=2) + "\n")

    assert _install(tmp_path, "--agent-id", "research-box") == 0
    assert _uninstall(tmp_path) == 0

    assert config.is_file(), "uninstall deleted a configuration the operator owned"
    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["custom"] is True
    assert data["projectNote"] == "mine"
    assert data["memoryService"]["endpoint"] == "http://127.0.0.1:9999"
    assert data["memoryService"]["agentId"] == "research-box"


def test_uninstall_removes_an_unedited_installer_config_after_agent_id_merge(tmp_path):
    assert _install(tmp_path) == 0
    config = tmp_path / "memory-plugin.json"
    assert config.is_file(), "the clean install did not create the plugin config"

    assert _install(tmp_path, "--agent-id", "research-box") == 0
    assert _uninstall(tmp_path) == 0

    assert not config.exists(), (
        "an unedited config created by the installer must remain removable after the merge"
    )
