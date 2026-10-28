"""RED tests for SPEC-F003 — the managed block in OpenCode's global `AGENTS.md`.

Every test runs against a tmp_path root passed via `--root`: neither the real
`~/.config/opencode` nor the developer's own `AGENTS.md` is ever read or written.

The feature does not exist yet, so these tests are expected to fail. They must
fail on the missing behaviour (no block written, no payload, no refusal, no
removal), never on collection or syntax.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "harness"))

PAYLOAD = (
    REPO_ROOT / "src" / "mcp_memory_service" / "installers" / "payload" / "opencode" / "AGENTS.md"
)
START = "<!-- mms:start -->"
END = "<!-- mms:end -->"
PORT = "39123"


def _mod():
    return importlib.import_module("instalar")


def _argv(root: Path, *extra: str) -> list[str]:
    return ["--harness", "opencode", "--root", str(root), "--port", PORT, *extra]


def _install(root: Path) -> int:
    return _mod().main(_argv(root, "--skip-health"))


def _uninstall(root: Path) -> int:
    return _mod().main(_argv(root, "--uninstall"))


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_text() -> str:
    if not PAYLOAD.is_file():
        pytest.fail(f"SPEC-F003 payload is missing: {PAYLOAD}")
    return PAYLOAD.read_text(encoding="utf-8")


def _payload_body() -> str:
    return _segments(_payload_text())[1]


def _payload_block() -> str:
    """The payload from the start marker through the end marker's newline."""
    text = _payload_text()
    start = text.index(START)
    end = text.index(END, start) + len(END)
    if text[end : end + 2] == "\r\n":
        end += 2
    elif text[end : end + 1] == "\n":
        end += 1
    return text[start:end]


def _segments(text: str) -> tuple[str, str, str]:
    """Split around the managed pair: (through start line, body, from end line)."""
    start = text.index(START)
    body_from = text.index("\n", start) + 1
    end = text.index(END, body_from)
    return text[:body_from], text[body_from:end], text[end:]


def _manifest_entries(root: Path) -> list[object]:
    path = root / "mms-install-manifest.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("created") if isinstance(data, dict) else None
    return entries if isinstance(entries, list) else []


def _manifest_entry(root: Path, name: str) -> dict | None:
    for entry in _manifest_entries(root):
        if not isinstance(entry, dict):
            continue
        raw = entry.get("path")
        if isinstance(raw, str) and Path(raw).name == name:
            return entry
    return None


def _assert_one_pair(text: str) -> None:
    assert text.count(START) == 1, f"expected exactly one {START!r} in:\n{text}"
    assert text.count(END) == 1, f"expected exactly one {END!r} in:\n{text}"


# --- R1/R2: clean root creates the block -------------------------------------


def test_clean_install_creates_agents_md_with_one_managed_block(tmp_path):
    assert _install(tmp_path) == 0

    target = tmp_path / "AGENTS.md"
    assert target.is_file(), "install must create <root>/AGENTS.md"

    text = target.read_text(encoding="utf-8")
    _assert_one_pair(text)
    assert text.startswith(START), "a file we created starts with the managed block"
    assert text.rstrip("\r\n").endswith(END)

    before, body, after = _segments(text)
    assert before == START + "\n"
    assert after == END + "\n"
    # Short doctrine, not a copy of the long steering payload.
    assert "mms-uso" in body, "the block must point at the mms-uso skill"
    assert "memory_search" in body, "the block must mention the search tool"


def test_manifest_records_the_created_agents_md_with_its_hash(tmp_path):
    assert _install(tmp_path) == 0

    target = tmp_path / "AGENTS.md"
    entry = _manifest_entry(tmp_path, "AGENTS.md")
    assert entry is not None, "a file the installer created must be recorded in the manifest"
    assert Path(entry["path"]).name == "AGENTS.md"
    assert entry["sha256"] == _digest(target)


# --- R8: payload lint --------------------------------------------------------


def test_payload_is_short_portable_and_marker_delimited():
    text = _payload_text()
    lines = text.splitlines()

    assert len(lines) <= 40, f"the block is paid for on every prompt; got {len(lines)} lines"
    assert "Kiro" not in text
    assert "Hermes" not in text
    assert not re.search(r":[0-9]{4,5}", text), "no hardcoded port in the block"
    _assert_one_pair(text)
    assert lines[0] == START
    assert lines[-1] == END
    assert "mms-uso" in text
    assert "memory_search" in text


# --- R4/R6: append and idempotence -------------------------------------------


def test_append_preserves_user_prefix_and_is_idempotent(tmp_path, capsys):
    user_text = "# Minhas notas\n\nlinha do usuário\n"
    target = tmp_path / "AGENTS.md"
    _write_bytes(target, user_text.encode("utf-8"))

    assert _install(tmp_path) == 0

    result = target.read_text(encoding="utf-8")
    _assert_one_pair(result)
    assert result.startswith(user_text), "user bytes must be preserved verbatim"
    remainder = result[len(user_text) :]
    assert remainder.startswith("\n"), "append must add one blank line before the block"
    assert not remainder.startswith("\n\n"), "exactly one blank line, not more"
    assert remainder == "\n" + _payload_block()

    # A pre-existing file is the operator's: append must not claim ownership.
    assert _manifest_entry(tmp_path, "AGENTS.md") is None

    before = _digest(target)
    capsys.readouterr()
    assert _install(tmp_path) == 0
    assert _digest(target) == before, "a second install must not rewrite the file"
    assert "nothing to do" in capsys.readouterr().out


def test_append_to_a_file_without_trailing_newline_adds_exactly_one(tmp_path):
    user_text = "sem newline final"
    target = tmp_path / "AGENTS.md"
    _write_bytes(target, user_text.encode("utf-8"))

    assert _install(tmp_path) == 0

    result = target.read_text(encoding="utf-8")
    _assert_one_pair(result)
    assert result.startswith(user_text)
    assert result == user_text + "\n" + _payload_block()


def test_uninstall_restores_a_file_that_had_no_trailing_newline(tmp_path):
    user = b"sem newline final"
    target = tmp_path / "AGENTS.md"
    _write_bytes(target, user)

    assert _install(tmp_path) == 0
    installed = target.read_text(encoding="utf-8")
    _assert_one_pair(installed)
    assert installed.startswith("sem newline final\n" + START)

    assert _uninstall(tmp_path) == 0

    assert target.is_file()
    assert _read_bytes(target) == user, "uninstall must restore the missing final newline"


def test_read_only_agents_md_aborts_before_any_write(tmp_path):
    target = tmp_path / "AGENTS.md"
    _write_bytes(target, b"mine\n")
    before = _digest(target)
    os.chmod(target, 0o444)
    try:
        rc = _install(tmp_path)
    finally:
        os.chmod(target, 0o644)

    assert rc != 0, "a read-only AGENTS.md must abort instead of being overwritten"
    assert _digest(target) == before
    assert not (tmp_path / "opencode.json").exists(), "abort must happen before any write"
    assert not (tmp_path / "plugins").exists()
    assert not (tmp_path / "mms-install-manifest.json").exists()


# --- R3: replace only the body -----------------------------------------------


def test_replace_rewrites_only_the_body_between_the_markers(tmp_path, capsys):
    original = (
        "# Projeto\n"
        "\n"
        "texto antes\n"
        + START
        + "\n"
        "corpo antigo que será substituído\n"
        + END
        + "\n"
        "texto depois\n"
    )
    target = tmp_path / "AGENTS.md"
    _write_bytes(target, original.encode("utf-8"))
    before, _, after = _segments(original)

    assert _install(tmp_path) == 0

    result = target.read_text(encoding="utf-8")
    _assert_one_pair(result)
    assert result.startswith(before), "bytes before the start marker must not change"
    assert result.endswith(after), "bytes from the end marker on must not change"
    assert result == before + _payload_body() + after
    assert "corpo antigo" not in result

    digest = _digest(target)
    capsys.readouterr()
    assert _install(tmp_path) == 0
    assert _digest(target) == digest, "replacing with the same body must not write"
    assert "nothing to do" in capsys.readouterr().out


# --- CRLF and missing final newline ------------------------------------------


def test_crlf_file_gets_a_crlf_block_and_keeps_user_bytes(tmp_path):
    user = b"# Notas\r\n\r\nlinha do usu\xc3\xa1rio\r\n"
    target = tmp_path / "AGENTS.md"
    _write_bytes(target, user)

    assert _install(tmp_path) == 0

    installed = _read_bytes(target)
    assert installed.startswith(user), "user bytes must survive a CRLF install"
    remainder = installed[len(user) :]
    assert remainder.startswith(b"\r\n"), "the separator blank line uses CRLF"
    assert not remainder.startswith(b"\r\n\r\n")
    assert b"<!-- mms:start -->\r\n" in installed
    assert b"<!-- mms:end -->\r\n" in installed
    assert b"\n" not in installed.replace(b"\r\n", b""), "no bare LF inside a CRLF file"


# --- R5: ambiguity refusal ---------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(
            START + "\ncorpo A\n" + END + "\n" + START + "\ncorpo B\n" + END + "\n",
            id="duplicate-pair",
        ),
        pytest.param(START + "\ncorpo sem fim\n", id="unbalanced-start"),
        pytest.param("corpo sem começo\n" + END + "\n", id="unbalanced-end"),
        pytest.param(START + "\n" + START + "\ncorpo\n" + END + "\n" + END + "\n", id="nested"),
        pytest.param(END + "\ncorpo\n" + START + "\n", id="inverted-order"),
    ],
)
def test_ambiguous_markers_abort_without_any_write(tmp_path, text):
    target = tmp_path / "AGENTS.md"
    _write_bytes(target, text.encode("utf-8"))
    before = _digest(target)

    rc = _install(tmp_path)

    assert rc != 0, "ambiguous markers must abort with a non-zero exit code"
    assert _digest(target) == before, "the ambiguous file must be left untouched"
    assert not (tmp_path / "opencode.json").exists(), "nothing at all may be written"


# --- R7: uninstall -----------------------------------------------------------


def test_uninstall_removes_a_created_block_and_keeps_later_user_text(tmp_path):
    assert _install(tmp_path) == 0
    target = tmp_path / "AGENTS.md"
    assert target.is_file(), "install must create <root>/AGENTS.md"
    _assert_one_pair(target.read_text(encoding="utf-8"))
    with target.open("a", encoding="utf-8") as handle:
        handle.write("\nminha nota posterior\n")

    assert _uninstall(tmp_path) == 0

    assert target.is_file(), "the file still holds user content, so it must stay"
    text = target.read_text(encoding="utf-8")
    assert START not in text and END not in text
    assert "minha nota posterior" in text


def test_uninstall_deletes_the_file_the_installer_created(tmp_path):
    assert _install(tmp_path) == 0
    target = tmp_path / "AGENTS.md"
    assert target.is_file()

    assert _uninstall(tmp_path) == 0

    assert not target.exists(), "a file we created, now empty, must be deleted"


def test_uninstall_restores_a_preexisting_user_file_byte_for_byte(tmp_path):
    user = b"# Projeto do usuario\n\nconteudo proprio\n"
    target = tmp_path / "AGENTS.md"
    _write_bytes(target, user)
    assert _install(tmp_path) == 0
    _assert_one_pair(target.read_text(encoding="utf-8"))

    assert _uninstall(tmp_path) == 0

    assert target.is_file()
    assert _read_bytes(target) == user


def test_uninstall_keeps_a_preexisting_empty_file_empty(tmp_path):
    target = tmp_path / "AGENTS.md"
    _write_bytes(target, b"")
    assert _install(tmp_path) == 0
    assert START in _read_bytes(target).decode("utf-8")

    assert _uninstall(tmp_path) == 0

    assert target.is_file(), "we did not create it, so it must not be deleted"
    assert _read_bytes(target) == b""


def test_uninstall_removes_an_appended_block_without_a_manifest_entry(tmp_path):
    user = b"texto do usuario\n"
    target = tmp_path / "AGENTS.md"
    _write_bytes(target, user)
    assert _install(tmp_path) == 0
    _assert_one_pair(target.read_text(encoding="utf-8"))
    # Simulates a stale/absent manifest: the append case must still be undone.
    (tmp_path / "mms-install-manifest.json").unlink()

    assert _uninstall(tmp_path) == 0

    assert target.is_file()
    assert _read_bytes(target) == user


def test_uninstall_is_idempotent(tmp_path):
    assert _install(tmp_path) == 0
    target = tmp_path / "AGENTS.md"
    assert target.is_file(), "install must create <root>/AGENTS.md"
    _assert_one_pair(target.read_text(encoding="utf-8"))

    assert _uninstall(tmp_path) == 0
    assert not target.exists()

    rc = _uninstall(tmp_path)

    assert rc == 0, "a second uninstall must not fail"
    assert not target.exists()


# --- G6 regression: read-only no-op, dry-run, and partial writes --------------


def test_read_only_with_the_current_block_is_a_noop(tmp_path, capsys):
    assert _install(tmp_path) == 0
    target = tmp_path / "AGENTS.md"
    before = _digest(target)
    os.chmod(target, 0o444)
    try:
        capsys.readouterr()
        rc = _install(tmp_path)
        out = capsys.readouterr().out
    finally:
        os.chmod(target, 0o644)

    assert rc == 0, "an up-to-date file needs no write, so read-only must not abort"
    assert _digest(target) == before
    assert "nothing to do" in out


def test_dry_run_on_a_read_only_file_reports_the_plan_without_writing(tmp_path, capsys):
    target = tmp_path / "AGENTS.md"
    user = b"texto do usuario\n"
    _write_bytes(target, user)
    before = _digest(target)
    os.chmod(target, 0o444)
    try:
        rc = _mod().main(_argv(tmp_path, "--dry-run", "--skip-health"))
        out = capsys.readouterr().out
    finally:
        os.chmod(target, 0o644)

    assert rc == 0, "a dry run never writes, so a read-only file must not abort it"
    assert "AGENTS.md" in out, "the plan must name the managed file"
    assert _digest(target) == before
    assert not (tmp_path / "opencode.json").exists()
    assert not (tmp_path / "plugins").exists()
    assert not (tmp_path / "mms-install-manifest.json").exists()


def test_uninstall_refuses_a_read_only_managed_file_before_touching_the_config(tmp_path):
    assert _install(tmp_path) == 0
    target = tmp_path / "AGENTS.md"
    config = tmp_path / "opencode.json"
    agents_before = _digest(target)
    config_before = _digest(config)
    os.chmod(target, 0o444)
    try:
        rc = _uninstall(tmp_path)
    finally:
        os.chmod(target, 0o644)

    assert rc != 0, "a read-only managed file must make uninstall abort"
    assert _digest(target) == agents_before
    assert _digest(config) == config_before, "the config must not be edited before the refusal"
    data = json.loads(config.read_text(encoding="utf-8"))
    assert "mms" in data["mcp"]["servers"]


def test_uninstall_keeps_trailing_blank_lines_after_a_created_block(tmp_path):
    assert _install(tmp_path) == 0
    target = tmp_path / "AGENTS.md"
    with target.open("ab") as handle:
        handle.write(b"\n\n\n")

    assert _uninstall(tmp_path) == 0

    assert target.is_file(), "trailing blank lines are content, not an empty file"
    assert _read_bytes(target).endswith(b"\n\n\n")
