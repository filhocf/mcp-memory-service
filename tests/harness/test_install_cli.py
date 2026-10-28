"""RED tests for SPEC-F007 — ship the installer and expose `memory install`.

The installer stops being a script-only feature: its logic moves into
``mcp_memory_service.installers`` and the payload moves inside the package, so a
wheel installed from PyPI can run ``memory install opencode``. These tests pin
the package layout (R1), script delegation (R2/R6), the OpenCode subcommand with
its dry-run/apply/uninstall flags (R3/R5), the list subcommand (R4), the exit
codes (R5), and the wheel contents (R1/AC4).

Everything runs in ``tmp_path`` via ``--root``: no real harness directory and no
real ``$HOME`` is read or written.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = REPO_ROOT / "scripts" / "harness"
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(HARNESS_DIR))
sys.path.insert(0, str(SRC_DIR))

from mcp_memory_service.cli.main import cli  # noqa: E402

START = "<!-- mms:start -->"
END = "<!-- mms:end -->"
PORT = "39123"


def _invoke(*args: str):
    return CliRunner().invoke(cli, ["install", *args])


def _install_root(root: Path, *extra: str):
    return _invoke("opencode", "--root", str(root), *extra)


def _opencode_default_root() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return (Path(xdg) if xdg else Path.home() / ".config") / "opencode"


# --- R4 / AC5: list ----------------------------------------------------------


def test_list_names_every_harness_its_default_root_and_its_surfaces():
    result = _invoke("list")

    assert result.exit_code == 0, result.output
    output = result.output
    for harness in ("hermes", "kiro", "opencode"):
        assert harness in output, f"`install list` does not name {harness}:\n{output}"

    for default_root in (Path.home() / ".hermes", Path.home() / ".kiro", _opencode_default_root()):
        assert str(default_root) in output, (
            f"`install list` does not print the default root {default_root}:\n{output}"
        )

    # The surfaces each harness deposits, not just its config file.
    assert "mms-uso" in output, "the skill surface is missing from the list"
    assert "SKILL.md" in output, "the skill surface is missing from the list"
    assert "AGENTS.md" in output, "the OpenCode AGENTS.md surface is missing"
    assert "hooks" in output, "the Hermes hooks surface is missing"
    assert "steering" in output, "the Kiro steering surface is missing"


# --- R3 / AC2: dry run -------------------------------------------------------


def test_dry_run_prints_the_plan_and_writes_nothing(tmp_path):
    root = tmp_path / "opencode"

    result = _install_root(root, "--dry-run", "--skip-health")

    assert result.exit_code == 0, result.output
    output = result.output
    assert "opencode.json" in output, f"the plan does not name opencode.json:\n{output}"
    assert "AGENTS.md" in output, f"the plan does not name AGENTS.md:\n{output}"
    assert "mms-uso" in output, f"the plan does not name the skill:\n{output}"
    assert "plugin" in output.lower(), f"the plan does not name the plugin:\n{output}"
    assert not root.exists(), f"a dry run created {root}: {list(root.iterdir())}"


# --- R3 / AC3: install -------------------------------------------------------


def test_install_opencode_deposits_every_surface(tmp_path):
    root = tmp_path / "opencode"

    result = _install_root(root, "--skip-health", "--port", PORT)

    assert result.exit_code == 0, result.output

    config = root / "opencode.json"
    assert config.is_file(), "install must create <root>/opencode.json"
    data = json.loads(config.read_text(encoding="utf-8"))
    assert "mms" in data["mcp"]["servers"], "the mms server is not registered"

    agents = root / "AGENTS.md"
    assert agents.is_file(), "install must create <root>/AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    assert text.count(START) == 1, f"expected exactly one {START!r}:\n{text}"
    assert text.count(END) == 1, f"expected exactly one {END!r}:\n{text}"

    skill = root / "skills" / "mms-uso" / "SKILL.md"
    assert skill.is_file(), "install must deposit the usage skill"

    plugin_dir = root / "plugins" / "opencode-memory"
    assert (plugin_dir / "index.js").is_file(), "install must deposit the plugin"
    assert (plugin_dir / "package.json").is_file(), "install must deposit the plugin manifest"

    plugin_config = root / "memory-plugin.json"
    assert plugin_config.is_file(), "install must bootstrap the plugin configuration"
    plugin_data = json.loads(plugin_config.read_text(encoding="utf-8"))
    assert "agentId" in plugin_data["memoryService"], "the plugin config carries no agentId"


# --- R5 / AC6: uninstall -----------------------------------------------------


def test_uninstall_removes_the_deposited_surfaces_and_keeps_the_config(tmp_path):
    root = tmp_path / "opencode"
    assert _install_root(root, "--skip-health", "--port", PORT).exit_code == 0

    result = _invoke("opencode", "--root", str(root), "--uninstall")

    assert result.exit_code == 0, result.output

    assert not (root / "plugins" / "opencode-memory").exists(), "the plugin was not removed"
    assert not (root / "plugins").exists(), "the created plugins directory was not pruned"
    assert not (root / "skills" / "mms-uso" / "SKILL.md").exists(), "the skill was not removed"
    assert not (root / "AGENTS.md").exists(), "the AGENTS.md we created was not removed"
    assert not (root / "memory-plugin.json").exists(), "the plugin config we created was not removed"

    # The config pre-existed only because the install edited it: uninstall must
    # remove the registration and never delete the operator's file.
    config = root / "opencode.json"
    assert config.is_file(), "uninstall must not delete an edited config file"
    data = json.loads(config.read_text(encoding="utf-8"))
    servers = data.get("mcp", {}).get("servers", {})
    assert "mms" not in servers, "uninstall did not remove the mms registration"


# --- R5: unknown harness is a usage error ------------------------------------


def test_unknown_harness_is_a_click_usage_error():
    result = _invoke("kiro")

    assert result.exit_code == 2, f"expected a Click usage error (2):\n{result.output}"
    assert "kiro" in result.output, (
        f"the usage error must be about the unknown harness kiro:\n{result.output}"
    )


# --- R5: a failed action exits 1 ---------------------------------------------


def test_ambiguous_config_exits_1_without_depositing_anything(tmp_path):
    root = tmp_path / "opencode"
    root.mkdir()
    (root / "opencode.json").write_text("{}\n", encoding="utf-8")
    (root / "opencode.jsonc").write_text("{}\n", encoding="utf-8")

    result = _install_root(root, "--skip-health")

    assert result.exit_code == 1, f"an ambiguous config must exit 1:\n{result.output}"
    assert not (root / "AGENTS.md").exists(), "abort must happen before any deposit"
    assert not (root / "skills").exists(), "abort must happen before any deposit"
    assert not (root / "plugins").exists(), "abort must happen before any deposit"
    assert not (root / "memory-plugin.json").exists(), "abort must happen before any deposit"


# --- R2 / R6: script delegates to the packaged installer ---------------------


def test_script_and_cli_delegate_to_the_packaged_core(monkeypatch):
    from mcp_memory_service.installers import core

    monkeypatch.setattr(core, "main", lambda *args, **kwargs: 7)

    import instalar

    assert instalar.main([]) == 7, "the script must delegate to installers.core.main"

    result = _invoke("opencode")
    assert result.exit_code == 7, (
        "the CLI must forward the packaged installer's return code, not swallow it:\n"
        f"{result.output}"
    )


def test_script_still_lists_opencode_via_subprocess():
    source = (HARNESS_DIR / "instalar.py").read_text(encoding="utf-8")
    assert "mcp_memory_service.installers" in source, (
        "the script no longer delegates to the packaged installer"
    )

    proc = subprocess.run(
        [sys.executable, str(HARNESS_DIR / "instalar.py"), "--list"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert proc.returncode == 0, f"the script wrapper failed:\n{proc.stdout}\n{proc.stderr}"
    assert "opencode" in proc.stdout, f"the script does not list opencode:\n{proc.stdout}"


# --- R1: the packaged layout -------------------------------------------------


def test_payload_and_modules_live_inside_the_package():
    from mcp_memory_service.installers import core, harnesses, jsonc  # noqa: F401

    payload = core.PAYLOAD
    assert payload.is_dir(), f"core.PAYLOAD is not a directory: {payload}"

    for relative in (
        Path("skills") / "mms-uso" / "SKILL.md",
        Path("opencode") / "AGENTS.md",
        Path("steering") / "mms.md",
        Path("agent-hooks") / "mms_agent_stamp.py",
    ):
        assert (payload / relative).is_file(), f"the packaged payload is missing {relative}"

    assert not (HARNESS_DIR / "payload").exists(), (
        "the payload still lives outside the package at scripts/harness/payload"
    )


# --- R1 / AC4: the wheel ships the installer --------------------------------

REQUIRED_WHEEL_ENTRIES = (
    "mcp_memory_service/installers/core.py",
    "mcp_memory_service/installers/jsonc.py",
    "mcp_memory_service/installers/harnesses.py",
    "mcp_memory_service/installers/payload/skills/mms-uso/SKILL.md",
    "mcp_memory_service/installers/payload/steering/mms.md",
    "mcp_memory_service/installers/payload/agent-hooks/mms_agent_stamp.py",
    "mcp_memory_service/installers/payload/opencode/AGENTS.md",
)


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_wheel_contains_the_installer_and_its_payload(tmp_path):
    out_dir = tmp_path / "wheel"
    proc = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert proc.returncode == 0, (
        "`uv build --wheel` failed; the wheel cannot be inspected:\n"
        f"{proc.stdout}\n{proc.stderr}"
    )

    wheels = sorted(out_dir.glob("*.whl"))
    assert wheels, f"uv build produced no wheel in {out_dir}"

    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())

    missing = [entry for entry in REQUIRED_WHEEL_ENTRIES if entry not in names]
    assert missing == [], (
        f"the wheel {wheels[0].name} is missing the installer files: {missing}"
    )
