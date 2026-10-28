"""Tests for SPEC-F001 — the OpenCode harness and its MCP registration.

Every test runs in tmp_path (via --root): neither the developer's
~/.config/opencode nor the real OpenCode configuration is ever touched.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "harness"))

URL = "http://127.0.0.1:39123/mcp"
ENTRY = {"type": "remote", "url": URL, "headers": {"X-Agent-ID": "opencode"}}


def _mod():
    return importlib.import_module("instalar")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


JSONC_WITH_OTHER_SERVER = """{
  // keep this comment
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "other": {
        "type": "remote",
        "url": "http://127.0.0.1:9000/mcp"
      }
    }
  }
}
"""

INSTALLED_JSONC = """{
  // keep this comment
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "mms": {
        "type": "remote",
        "url": "http://127.0.0.1:39123/mcp"
      },
      "other": {
        "type": "remote",
        "url": "http://127.0.0.1:9000/mcp"
      }
    }
  }
}
"""

INSTALLED_JSONC_AFTER_UNINSTALL = """{
  // keep this comment
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "other": {
        "type": "remote",
        "url": "http://127.0.0.1:9000/mcp"
      }
    }
  }
}
"""


# --- 1. detection ------------------------------------------------------------


def test_opencode_harness_exists_and_honours_xdg_config_home(tmp_path, monkeypatch):
    instalar = _mod()

    assert "opencode" in instalar.harnesses()

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert instalar.harnesses()["opencode"].root_default == tmp_path / "xdg" / "opencode"

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert instalar.harnesses()["opencode"].root_default == Path.home() / ".config" / "opencode"


# --- 2. file resolution ------------------------------------------------------


def test_resolve_mcp_file_creates_json_edits_jsonc_and_rejects_both(tmp_path):
    instalar = _mod()
    opencode = instalar.harnesses()["opencode"]

    assert instalar.resolve_mcp_file(opencode, tmp_path) == tmp_path / "opencode.json"

    _write(tmp_path / "opencode.jsonc", "{}\n")
    assert instalar.resolve_mcp_file(opencode, tmp_path) == tmp_path / "opencode.jsonc"

    (tmp_path / "opencode.jsonc").unlink()
    _write(tmp_path / "opencode.json", "{}\n")
    assert instalar.resolve_mcp_file(opencode, tmp_path) == tmp_path / "opencode.json"

    _write(tmp_path / "opencode.jsonc", "{}\n")
    with pytest.raises(RuntimeError):
        instalar.resolve_mcp_file(opencode, tmp_path)


# --- 3. planning -------------------------------------------------------------


def test_plan_for_a_clean_root_emits_the_jsonc_mcp_and_agents_md_actions(tmp_path):
    instalar = _mod()
    opencode = instalar.harnesses()["opencode"]

    actions = instalar.plan_for(opencode, tmp_path, 39123, installed=False, cli_present=False)

    mcp_actions = [a for a in actions if a.kind == "jsonc-mcp"]
    assert len(mcp_actions) == 1
    assert mcp_actions[0].target == tmp_path / "opencode.json"

    agents_actions = [a for a in actions if a.kind == "agents-md"]
    assert len(agents_actions) == 1
    assert agents_actions[0].target == tmp_path / "AGENTS.md"


# --- 4. clean install --------------------------------------------------------


def test_clean_install_writes_the_v2_shape_and_a_schema(tmp_path):
    instalar = _mod()

    rc = instalar.main(
        [
            "--harness",
            "opencode",
            "--root",
            str(tmp_path),
            "--port",
            "39123",
            "--skip-health",
        ]
    )

    assert rc == 0
    target = tmp_path / "opencode.json"
    assert target.is_file()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["mcp"]["servers"]["mms"] == ENTRY
    assert "$schema" in data


# --- 5. install over an existing JSONC file ----------------------------------


def test_install_preserves_comment_and_other_server_in_jsonc(tmp_path):
    instalar = _mod()
    _write(tmp_path / "opencode.jsonc", JSONC_WITH_OTHER_SERVER)

    rc = instalar.main(
        [
            "--harness",
            "opencode",
            "--root",
            str(tmp_path),
            "--port",
            "39123",
            "--skip-health",
        ]
    )

    assert rc == 0
    target = tmp_path / "opencode.jsonc"
    text = target.read_text(encoding="utf-8")
    assert text.count("// keep this comment") == 1
    assert '"other"' in text
    assert "http://127.0.0.1:9000/mcp" in text
    assert instalar.opencode_entry(target)["url"] == URL


# --- 6. idempotence ----------------------------------------------------------


def test_second_install_reports_nothing_to_do_and_leaves_the_bytes(tmp_path, capsys):
    instalar = _mod()
    argv = [
        "--harness",
        "opencode",
        "--root",
        str(tmp_path),
        "--port",
        "39123",
        "--skip-health",
    ]
    assert instalar.main(argv) == 0
    target = tmp_path / "opencode.json"
    before = _digest(target)

    assert instalar.main(argv) == 0

    assert _digest(target) == before
    assert "nothing to do" in capsys.readouterr().out


# --- 7. usability, not mere presence -----------------------------------------


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(
            {"type": "remote", "url": "http://127.0.0.1:9999/mcp"},
            id="wrong-port",
        ),
        pytest.param({"type": "remote", "url": URL, "disabled": True}, id="disabled"),
    ],
)
def test_wrong_port_and_disabled_entries_are_replaced(tmp_path, entry):
    instalar = _mod()
    _write(
        tmp_path / "opencode.json",
        json.dumps({"mcp": {"servers": {"mms": entry}}}, indent=2),
    )

    rc = instalar.main(
        [
            "--harness",
            "opencode",
            "--root",
            str(tmp_path),
            "--port",
            "39123",
            "--skip-health",
        ]
    )

    assert rc == 0
    data = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    written = data["mcp"]["servers"]["mms"]
    assert written["url"] == URL
    assert written.get("disabled") is not True


# --- 8. legacy mcp.mms -------------------------------------------------------


def test_matching_legacy_entry_is_honoured_and_removed_on_uninstall(tmp_path):
    instalar = _mod()
    _write(
        tmp_path / "opencode.json",
        json.dumps(
            {"mcp": {"mms": {"type": "remote", "url": URL}}},
            indent=2,
        ),
    )
    target = tmp_path / "opencode.json"

    assert instalar.opencode_entry(target) == {"type": "remote", "url": URL}

    opencode = instalar.harnesses()["opencode"]
    actions = instalar.plan_for(opencode, tmp_path, 39123, installed=True, cli_present=False)
    assert [a for a in actions if a.kind == "jsonc-mcp"] == []

    rc = instalar.main(["--harness", "opencode", "--root", str(tmp_path), "--uninstall"])

    assert rc == 0
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "mms" not in data["mcp"]
    assert "mms" not in data["mcp"].get("servers", {})


# --- 9. surgical uninstall ---------------------------------------------------


def test_uninstall_removes_only_mcp_servers_mms(tmp_path):
    instalar = _mod()
    _write(tmp_path / "opencode.jsonc", INSTALLED_JSONC)
    target = tmp_path / "opencode.jsonc"

    rc = instalar.main(["--harness", "opencode", "--root", str(tmp_path), "--uninstall"])

    assert rc == 0
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == INSTALLED_JSONC_AFTER_UNINSTALL
    assert instalar.opencode_entry(target) == {}


# --- 10. ambiguous configuration ---------------------------------------------


def test_both_files_present_abort_without_writing(tmp_path):
    instalar = _mod()
    _write(tmp_path / "opencode.json", '{"mcp": {"servers": {}}}\n')
    _write(tmp_path / "opencode.jsonc", '{"mcp": {"servers": {}}}\n')
    json_before = _digest(tmp_path / "opencode.json")
    jsonc_before = _digest(tmp_path / "opencode.jsonc")

    rc = instalar.main(
        [
            "--harness",
            "opencode",
            "--root",
            str(tmp_path),
            "--port",
            "39123",
            "--skip-health",
        ]
    )

    assert rc == 1
    assert _digest(tmp_path / "opencode.json") == json_before
    assert _digest(tmp_path / "opencode.jsonc") == jsonc_before


# --- 11. corrupt JSONC -------------------------------------------------------


def test_corrupt_jsonc_aborts_and_leaves_the_file_byte_identical(tmp_path):
    instalar = _mod()
    corrupt = '{\n  // keep this comment\n  "mcp": {"servers": {\n'
    _write(tmp_path / "opencode.jsonc", corrupt)
    target = tmp_path / "opencode.jsonc"
    before = _digest(target)

    rc = instalar.main(
        [
            "--harness",
            "opencode",
            "--root",
            str(tmp_path),
            "--port",
            "39123",
            "--skip-health",
        ]
    )

    assert rc == 1
    assert _digest(target) == before


# --- 12. uninstall with the service down -------------------------------------


def test_uninstall_works_with_the_service_down(tmp_path):
    instalar = _mod()
    _write(tmp_path / "opencode.json", json.dumps({"mcp": {"servers": {"mms": ENTRY}}}, indent=2))
    target = tmp_path / "opencode.json"

    rc = instalar.main(
        ["--harness", "opencode", "--root", str(tmp_path), "--port", "1", "--uninstall"]
    )

    assert rc == 0
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "mms" not in data["mcp"]["servers"]


# --- 13. verify --------------------------------------------------------------


def test_verify_reports_no_failures_after_a_successful_install(tmp_path):
    instalar = _mod()
    assert (
        instalar.main(
            [
                "--harness",
                "opencode",
                "--root",
                str(tmp_path),
                "--port",
                "39123",
                "--skip-health",
            ]
        )
        == 0
    )

    failures = instalar.verify(instalar.harnesses()["opencode"], tmp_path, 39123)

    assert failures == []


# --- G5 regression: byte preservation, permissions, isolation ----------------


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_crlf_survives_install_and_uninstall(tmp_path):
    instalar = _mod()
    original = (
        b'{\r\n'
        b'  // keep this comment\r\n'
        b'  "mcp": {\r\n'
        b'    "servers": {\r\n'
        b'      "other": {}\r\n'
        b'    }\r\n'
        b'  }\r\n'
        b'}\r\n'
    )
    target = tmp_path / "opencode.jsonc"
    _write_bytes(target, original)

    assert instalar.main(["--harness", "opencode", "--root", str(tmp_path), "--port", "39123", "--skip-health"]) == 0
    installed = target.read_bytes()
    assert b"\r\n" in installed
    assert b"\n" not in installed.replace(b"\r\n", b"")

    assert instalar.main(["--harness", "opencode", "--root", str(tmp_path), "--uninstall"]) == 0
    assert target.read_bytes() == original


def test_uninstall_works_on_a_compact_document(tmp_path):
    instalar = _mod()
    text = '{"mcp":{"servers":{"mms":{"type":"remote","url":"%s"},"other":{}}},"theme":"dark"}\n' % URL
    target = tmp_path / "opencode.json"
    _write(target, text)

    assert instalar.main(["--harness", "opencode", "--root", str(tmp_path), "--uninstall"]) == 0
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "mms" not in data["mcp"]["servers"]
    assert data["mcp"]["servers"]["other"] == {}
    assert data["theme"] == "dark"


def test_install_keeps_a_comment_inside_servers(tmp_path):
    instalar = _mod()
    text = """{
  "mcp": {
    "servers": {
      // our servers live here
    }
  }
}
"""
    target = tmp_path / "opencode.jsonc"
    _write(target, text)

    assert instalar.main(["--harness", "opencode", "--root", str(tmp_path), "--port", "39123", "--skip-health"]) == 0
    result = target.read_text(encoding="utf-8")
    assert "// our servers live here" in result
    assert instalar.opencode_entry(target)["url"] == URL


def test_read_only_config_aborts_without_writing(tmp_path):
    instalar = _mod()
    target = tmp_path / "opencode.json"
    _write(target, '{"mcp": {"servers": {}}}\n')
    before = _digest(target)
    os.chmod(target, 0o444)
    try:
        rc = instalar.main(["--harness", "opencode", "--root", str(tmp_path), "--port", "39123", "--skip-health"])
    finally:
        os.chmod(target, 0o644)

    assert rc == 1
    assert _digest(target) == before


def test_new_config_is_private_and_existing_mode_is_preserved(tmp_path):
    instalar = _mod()

    assert instalar.main(["--harness", "opencode", "--root", str(tmp_path / "new"), "--port", "39123", "--skip-health"]) == 0
    created = tmp_path / "new" / "opencode.json"
    assert stat.S_IMODE(created.stat().st_mode) == 0o600

    existing = tmp_path / "existing"
    existing.mkdir()
    target = existing / "opencode.json"
    _write(target, '{"mcp": {"servers": {}}}\n')
    os.chmod(target, 0o640)
    assert instalar.main(["--harness", "opencode", "--root", str(existing), "--port", "39123", "--skip-health"]) == 0
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_uninstall_does_not_delete_a_manifest_path_outside_the_root(tmp_path):
    instalar = _mod()
    victim = tmp_path / "victim.txt"
    victim.write_text("do not delete", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "mms-install-manifest.json").write_text(json.dumps({"created": [str(victim)]}), encoding="utf-8")

    assert instalar.main(["--harness", "opencode", "--root", str(root), "--uninstall"]) == 0
    assert victim.exists()


def test_symlinked_config_stays_a_symlink_and_updates_its_target(tmp_path):
    instalar = _mod()
    real = tmp_path / "dotfiles" / "opencode.jsonc"
    _write(real, '{"mcp": {"servers": {}}}\n')
    link = tmp_path / "opencode.jsonc"
    link.symlink_to(real)

    assert instalar.main(["--harness", "opencode", "--root", str(tmp_path), "--port", "39123", "--skip-health"]) == 0
    assert link.is_symlink()
    assert instalar.opencode_entry(real)["url"] == URL


def test_a_remote_host_on_the_same_port_is_replaced(tmp_path):
    instalar = _mod()
    target = tmp_path / "opencode.json"
    _write(
        target,
        json.dumps({"mcp": {"servers": {"mms": {"type": "remote", "url": "http://192.168.1.9:39123/mcp"}}}}),
    )

    assert instalar.main(["--harness", "opencode", "--root", str(tmp_path), "--port", "39123", "--skip-health"]) == 0
    assert instalar.opencode_entry(target)["url"] == URL


def test_entry_is_usable_rejects_a_non_http_scheme():
    instalar = _mod()

    assert not instalar.entry_is_usable({"type": "remote", "url": "ftp://127.0.0.1:39123/mcp"}, 39123)


def test_opencode_root_default_follows_the_measured_client(monkeypatch):
    # Measured (OpenCode 2.1.3, Oct 2026): the client resolves its config from
    # $HOME/.config/opencode and does NOT consult XDG_CONFIG_HOME — the
    # default root must match, or mms lands in a file the client never reads.
    from mcp_memory_service.installers.harnesses import _opencode_root

    monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg/elsewhere")
    assert _opencode_root(Path("/real/home")) == Path("/real/home/.config/opencode")
