"""Tests for SPEC-F002 — OpenCode plugin deposit and XDG-aware paths.

Every test installs into ``tmp_path`` through ``--root``. The XDG seam is
exercised in a Node subprocess with a controlled environment, so neither the
developer's real ``$HOME`` nor the real OpenCode configuration is read or
written.

These are RED tests: they describe the contract of SPEC-F002 and fail on the
current implementation (no plugin deposit, no ``_internal.resolvePaths``).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "harness"))

SOURCE_PLUGIN = REPO_ROOT / "opencode" / "memory-plugin.js"
PORT = 39123
ENDPOINT = f"http://127.0.0.1:{PORT}"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


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


def _uninstall(root: Path) -> int:
    return _mod().main(["--harness", "opencode", "--root", str(root), "--uninstall"])


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plugin_dir(root: Path) -> Path:
    return root / "plugins" / "opencode-memory"


def _project_version() -> str:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def _resolved(path: Path | str) -> Path:
    return Path(os.path.realpath(path))


def _manifest_created_paths(manifest: dict, root: Path) -> list[Path]:
    """Paths recorded in ``created``, whether dicts (current) or strings (legacy)."""
    paths = []
    for entry in manifest.get("created") or []:
        raw = entry.get("path") if isinstance(entry, dict) else entry
        assert isinstance(raw, str) and raw, f"manifest entry has no path: {entry!r}"
        path = Path(raw)
        paths.append(path if path.is_absolute() else root / path)
    return paths


def _run_node(script: str, env: dict[str, str]) -> object:
    """Run an ES module script in Node and parse the JSONRESULT line."""
    assert NODE is not None, "node is not installed"
    completed = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    output = (completed.stdout + completed.stderr).strip()
    assert completed.returncode == 0, f"node failed (exit {completed.returncode}):\n{output}"
    for line in completed.stdout.splitlines():
        if line.startswith("JSONRESULT:"):
            return json.loads(line[len("JSONRESULT:") :])
    raise AssertionError(f"node produced no JSONRESULT line:\n{output}")


def _node_env(home: Path, **extra: str) -> dict[str, str]:
    env = {
        "HOME": str(home),
        "PATH": os.environ.get("PATH", ""),
        "NODE_NO_WARNINGS": "1",
    }
    env.update(extra)
    return env


def _resolve_paths(home: Path, options: dict, **env: str) -> dict:
    script = (
        f"const {{ _internal }} = await import({json.dumps(SOURCE_PLUGIN.as_uri())});\n"
        f"const result = _internal.resolvePaths({json.dumps(options)});\n"
        'console.log("JSONRESULT:" + JSON.stringify(result));\n'
    )
    return _run_node(script, _node_env(home, **env))


# --- 1. deposit (R1) ---------------------------------------------------------


def test_clean_install_deposits_the_plugin_package(tmp_path):
    assert _install(tmp_path) == 0

    index = _plugin_dir(tmp_path) / "index.js"
    package = _plugin_dir(tmp_path) / "package.json"

    assert index.is_file(), "plugins/opencode-memory/index.js was not deposited"
    assert package.is_file(), "plugins/opencode-memory/package.json was not deposited"
    assert index.read_bytes() == SOURCE_PLUGIN.read_bytes(), "index.js is not a byte-for-byte copy"

    data = json.loads(package.read_text(encoding="utf-8"))
    assert data["name"] == "opencode-memory"
    assert data["version"] == _project_version()
    assert data["type"] == "module"
    assert data["exports"] == {".": "./index.js"}


# --- 2. valid module (R2) ----------------------------------------------------


@needs_node
def test_deposited_index_imports_as_a_node_module(tmp_path):
    assert _install(tmp_path) == 0
    index = _plugin_dir(tmp_path) / "index.js"
    assert index.is_file(), "index.js was not deposited"

    script = (
        f"const m = await import({json.dumps(index.as_uri())});\n"
        'console.log("JSONRESULT:" + JSON.stringify({'
        "setup: typeof m.default?.setup, server: typeof m.default?.server}));\n"
    )
    result = _run_node(script, _node_env(tmp_path / "home"))

    assert result == {"setup": "function", "server": "function"}, result


# --- 3. no plugins entry (R3) ------------------------------------------------


def test_install_does_not_add_a_plugins_key(tmp_path):
    _write(
        tmp_path / "opencode.json",
        json.dumps({"$schema": "https://opencode.ai/config.json", "theme": "dark"}, indent=2) + "\n",
    )

    assert _install(tmp_path) == 0
    assert (_plugin_dir(tmp_path) / "index.js").is_file(), "the plugin was not deposited"

    data = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert "plugins" not in data, "the installer registered the plugin in opencode.json"
    assert data["theme"] == "dark"


def test_install_leaves_an_existing_plugins_list_untouched(tmp_path):
    _write(
        tmp_path / "opencode.json",
        json.dumps({"plugins": ["some-other-plugin"]}, indent=2) + "\n",
    )

    assert _install(tmp_path) == 0
    assert (_plugin_dir(tmp_path) / "index.js").is_file(), "the plugin was not deposited"

    data = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert data["plugins"] == ["some-other-plugin"]


# --- 4. configuration bootstrap (R4) -----------------------------------------


def test_clean_install_bootstraps_memory_plugin_json(tmp_path):
    assert _install(tmp_path) == 0

    config = tmp_path / "memory-plugin.json"
    assert config.is_file(), "memory-plugin.json was not bootstrapped"

    data = json.loads(config.read_text(encoding="utf-8"))
    service = data["memoryService"]
    assert service["endpoint"] == ENDPOINT
    assert service["timeoutMs"] == 5000
    assert service["loadTimeoutMs"] == 2500
    assert service["maxMemoriesPerSession"] == 8
    assert set(service) == {"endpoint", "timeoutMs", "loadTimeoutMs", "maxMemoriesPerSession"}


def test_existing_memory_plugin_json_is_never_modified(tmp_path):
    original = b'{\n  "memoryService": {"endpoint": "http://127.0.0.1:9999"},\n  "custom": true\n}\n'
    config = tmp_path / "memory-plugin.json"
    config.write_bytes(original)

    assert _install(tmp_path) == 0
    assert (_plugin_dir(tmp_path) / "index.js").is_file(), "the plugin was not deposited"

    assert config.read_bytes() == original, "the installer overwrote the user configuration"


def test_memory_awareness_json_suppresses_the_bootstrap(tmp_path):
    _write(tmp_path / "memory-awareness.json", '{"memoryService": {"endpoint": "http://127.0.0.1:8123"}}\n')

    assert _install(tmp_path) == 0
    assert (_plugin_dir(tmp_path) / "index.js").is_file(), "the plugin was not deposited"

    assert not (tmp_path / "memory-plugin.json").exists(), (
        "memory-awareness.json counts as configuration; memory-plugin.json must not be created"
    )


# --- 5. idempotence (R7) -----------------------------------------------------


def test_second_install_reports_nothing_to_do_and_keeps_the_bytes(tmp_path, capsys):
    assert _install(tmp_path) == 0
    index = _plugin_dir(tmp_path) / "index.js"
    package = _plugin_dir(tmp_path) / "package.json"
    assert index.is_file() and package.is_file(), "the first install did not deposit the plugin"
    before = (_digest(index), _digest(package))
    capsys.readouterr()  # drop the first install's output

    assert _install(tmp_path) == 0

    assert (_digest(index), _digest(package)) == before
    assert "nothing to do" in capsys.readouterr().out


# --- 6. manifest (R6) --------------------------------------------------------


def test_manifest_records_every_created_file_with_its_hash(tmp_path):
    assert _install(tmp_path) == 0

    manifest_path = tmp_path / "mms-install-manifest.json"
    assert manifest_path.is_file(), "mms-install-manifest.json was not written"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    created = manifest.get("created") or []
    assert created, "the manifest recorded no created file"
    assert all(isinstance(entry, dict) for entry in created), (
        f"current manifests must record hash objects, got {created!r}"
    )

    by_path = {_resolved(_manifest_entry_path(entry, tmp_path)): entry for entry in created}
    for expected in (
        _plugin_dir(tmp_path) / "index.js",
        _plugin_dir(tmp_path) / "package.json",
        tmp_path / "memory-plugin.json",
    ):
        assert _resolved(expected) in by_path, f"{expected} is missing from the manifest"
        assert by_path[_resolved(expected)]["sha256"] == _digest(expected)

    created_dirs = {_resolved(path) for path in manifest.get("created_dirs") or []}
    assert _resolved(_plugin_dir(tmp_path)) in created_dirs
    assert _resolved(tmp_path / "plugins") in created_dirs


def _manifest_entry_path(entry: dict, root: Path) -> Path:
    path = Path(entry["path"])
    return path if path.is_absolute() else root / path


def test_legacy_string_manifest_is_still_readable_on_uninstall(tmp_path):
    assert _install(tmp_path) == 0
    index = _plugin_dir(tmp_path) / "index.js"
    assert index.is_file()
    assert index.read_bytes() == SOURCE_PLUGIN.read_bytes()

    # Legacy manifests stored bare path strings.
    (tmp_path / "mms-install-manifest.json").write_text(
        json.dumps({"created": [str(index)]}, indent=2) + "\n", encoding="utf-8"
    )

    assert _uninstall(tmp_path) == 0

    assert not index.exists(), "a legacy string entry was not removed when the source matched"


# --- 7. uninstall ownership (R6) ---------------------------------------------


def test_uninstall_removes_owned_files_and_created_dirs(tmp_path):
    assert _install(tmp_path) == 0
    index = _plugin_dir(tmp_path) / "index.js"
    package = _plugin_dir(tmp_path) / "package.json"
    assert index.is_file() and package.is_file()

    assert _uninstall(tmp_path) == 0

    assert not index.exists()
    assert not package.exists()
    assert not _plugin_dir(tmp_path).exists(), "the created plugin directory was not removed"
    assert not (tmp_path / "plugins").exists(), "the created plugins directory was not removed"


def test_uninstall_retains_a_modified_index_js(tmp_path, capsys):
    assert _install(tmp_path) == 0
    index = _plugin_dir(tmp_path) / "index.js"
    package = _plugin_dir(tmp_path) / "package.json"
    assert index.is_file() and package.is_file()
    edited = index.read_bytes() + b"\n// local edit\n"
    index.write_bytes(edited)
    capsys.readouterr()

    assert _uninstall(tmp_path) == 0

    assert index.is_file(), "a user-modified index.js must be preserved"
    assert index.read_bytes() == edited
    assert not package.exists(), "package.json should still be removed"
    output = capsys.readouterr().out.lower()
    assert "retain" in output or "retid" in output or "mantid" in output, (
        "uninstall must report the retained file"
    )


def test_uninstall_keeps_a_created_dir_that_is_not_empty(tmp_path):
    assert _install(tmp_path) == 0
    index = _plugin_dir(tmp_path) / "index.js"
    assert index.is_file()
    user_file = _plugin_dir(tmp_path) / "notes.txt"
    user_file.write_text("mine\n", encoding="utf-8")

    assert _uninstall(tmp_path) == 0

    assert not index.exists()
    assert user_file.is_file(), "uninstall must not delete user files"
    assert _plugin_dir(tmp_path).is_dir(), "a non-empty directory must not be removed"
    assert (tmp_path / "plugins").is_dir(), "the parent of a retained directory stays"


# --- 8. foreign plugin (R6) --------------------------------------------------


def test_foreign_plugin_aborts_without_overwriting(tmp_path, capsys):
    index = _plugin_dir(tmp_path) / "index.js"
    foreign = b"// a plugin the installer did not deposit\n"
    index.parent.mkdir(parents=True)
    index.write_bytes(foreign)

    rc = _install(tmp_path)

    assert rc != 0, "install must abort when index.js is foreign"
    assert index.read_bytes() == foreign, "the foreign index.js was overwritten"
    captured = capsys.readouterr()
    output = (captured.out + captured.err).lower()
    assert "foreign" in output or "estrangeir" in output


# --- 9. XDG resolution seam (R5) ---------------------------------------------


@needs_node
def test_resolve_paths_falls_back_to_the_home_layout(tmp_path):
    home = tmp_path / "home"
    result = _resolve_paths(home, {"env": {}, "home": str(home)})

    assert Path(result["configDir"]) == home / ".config" / "opencode"
    assert Path(result["stateDir"]) == home / ".local" / "state" / "opencode"
    assert Path(result["dataDir"]) == home / ".local" / "share" / "opencode"
    assert Path(result["statusFile"]) == home / ".local" / "state" / "opencode" / ".memory-status.json"
    assert Path(result["inboxStateFile"]) == home / ".local" / "state" / "opencode" / ".memory-inbox-state.json"


@needs_node
def test_resolve_paths_honours_xdg_directories(tmp_path):
    home = tmp_path / "home"
    xdg_config = tmp_path / "xdg-config"
    xdg_state = tmp_path / "xdg-state"
    xdg_data = tmp_path / "xdg-data"
    env = {
        "XDG_CONFIG_HOME": str(xdg_config),
        "XDG_STATE_HOME": str(xdg_state),
        "XDG_DATA_HOME": str(xdg_data),
    }

    result = _resolve_paths(home, {"env": env, "home": str(home)}, **env)

    assert Path(result["configDir"]) == xdg_config / "opencode"
    assert Path(result["stateDir"]) == xdg_state / "opencode"
    assert Path(result["dataDir"]) == xdg_data / "opencode"
    assert Path(result["statusFile"]) == xdg_state / "opencode" / ".memory-status.json"
    assert Path(result["inboxStateFile"]) == xdg_state / "opencode" / ".memory-inbox-state.json"


@needs_node
def test_resolve_paths_honours_the_status_file_override(tmp_path):
    home = tmp_path / "home"
    custom = tmp_path / "custom" / "status.json"
    env = {"OPENCODE_MEMORY_STATUS_FILE": str(custom)}

    result = _resolve_paths(home, {"env": env, "home": str(home)}, **env)

    assert Path(result["statusFile"]) == custom


@needs_node
def test_config_paths_preserve_their_precedence(tmp_path):
    home = tmp_path / "home"
    config_dir = home / ".config" / "opencode"
    directory = tmp_path / "project"
    explicit = tmp_path / "explicit.json"
    from_env = tmp_path / "from-env.json"
    env = {"OPENCODE_MEMORY_PLUGIN_CONFIG": str(from_env)}

    result = _resolve_paths(
        home,
        {
            "env": env,
            "home": str(home),
            "directory": str(directory),
            "configPath": str(explicit),
        },
        **env,
    )

    expected = [
        explicit,
        from_env,
        config_dir / "memory-plugin.json",
        config_dir / "memory-awareness.json",
        directory / ".opencode" / "memory-plugin.json",
        directory / ".opencode" / "memory-awareness.json",
    ]
    assert [Path(path) for path in result["configPaths"]] == expected


@needs_node
def test_config_paths_default_to_the_config_dir_then_the_project(tmp_path):
    home = tmp_path / "home"
    config_dir = home / ".config" / "opencode"
    directory = tmp_path / "project"

    result = _resolve_paths(
        home, {"env": {}, "home": str(home), "directory": str(directory)}
    )

    expected = [
        config_dir / "memory-plugin.json",
        config_dir / "memory-awareness.json",
        directory / ".opencode" / "memory-plugin.json",
        directory / ".opencode" / "memory-awareness.json",
    ]
    assert [Path(path) for path in result["configPaths"]] == expected


# --- 10. adversarial review regressions (B1-B3) ------------------------------
#
# These are RED tests for the three blockers found in the adversarial review:
# a relative `--root` round-trips through the manifest as a relative path,
# `plugins` can be a symlink that escapes the root, and a corrupted
# `created_dirs` list crashes uninstall.


def test_install_and_uninstall_honour_a_relative_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = Path("lab")

    assert _install(root) == 0
    index = root / "plugins" / "opencode-memory" / "index.js"
    package = root / "plugins" / "opencode-memory" / "package.json"
    config = root / "memory-plugin.json"
    assert index.is_file(), "the plugin was not deposited under the relative root"

    assert _uninstall(root) == 0

    assert not index.exists(), "uninstall with the same relative root must remove index.js"
    assert not package.exists(), "uninstall with the same relative root must remove package.json"
    assert not config.exists(), "uninstall with the same relative root must remove memory-plugin.json"


def test_install_refuses_a_plugins_symlink_that_escapes_the_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "plugins").symlink_to(outside, target_is_directory=True)

    rc = _install(root)

    assert rc != 0, "install must refuse a plugins symlink that escapes the root"
    escaped = outside / "opencode-memory"
    assert not escaped.exists(), "the installer wrote the plugin outside the sandbox"


def test_uninstall_reports_a_manifest_file_outside_the_root_as_retained(tmp_path, capsys):
    root = tmp_path / "root"
    root.mkdir()
    outside_file = tmp_path / "outside-owned.txt"
    outside_file.write_text("not ours to delete\n", encoding="utf-8")
    _write(
        root / "mms-install-manifest.json",
        json.dumps(
            {
                "created": [{"path": str(outside_file), "sha256": _digest(outside_file)}],
                "created_dirs": [],
            },
            indent=2,
        )
        + "\n",
    )
    capsys.readouterr()

    assert _uninstall(root) == 0

    assert outside_file.is_file(), "a manifest path outside the root must never be deleted"
    output = capsys.readouterr().out.lower()
    assert "retain" in output or "retid" in output or "mantid" in output, (
        "uninstall must report a manifest path outside the root as retained"
    )


def test_uninstall_tolerates_corrupt_created_dirs_entries(tmp_path):
    assert _install(tmp_path) == 0
    root = tmp_path
    index = _plugin_dir(root) / "index.js"
    package = _plugin_dir(root) / "package.json"
    config = root / "memory-plugin.json"
    manifest_path = root / "mms-install-manifest.json"
    assert index.is_file() and package.is_file() and config.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("created"), "the install recorded no created file"
    manifest["created_dirs"] = [123, {"path": "x"}, None]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    assert _uninstall(root) == 0

    assert not index.exists(), "uninstall must still remove the owned files"
    assert not package.exists(), "uninstall must still remove the owned files"
    assert not config.exists(), "uninstall must still remove the owned files"
    assert not manifest_path.exists(), "uninstall must still delete the manifest"
