"""RED tests for SPEC-F009 — the OpenCode integration guide and upstream surfaces.

The upstream-facing pages must describe the shipped installer, not the manual
copy era: required headings (AC2), resolvable relative links (AC3), every
documented `memory install` command matching the CLI's `--help` (AC4), the
changelog fragment shape (AC8), installer mentions where users look (AC5/AC6),
and no `specs/` paths leaking into upstream documents (R10/AC7).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from click.testing import CliRunner  # noqa: E402

from mcp_memory_service.cli.main import cli  # noqa: E402

GUIDE = REPO_ROOT / "agents" / "opencode" / "README.md"
DOCS = {
    "guide": REPO_ROOT / "agents" / "opencode" / "README.md",
    "matrix": REPO_ROOT / "agents" / "README.md",
    "integrations": REPO_ROOT / "docs" / "integrations.md",
    "root": REPO_ROOT / "README.md",
}

REQUIRED_HEADINGS = [
    "First-class status",
    "Prerequisites",
    "Install",
    "What gets installed",
    "Verify",
    "Authentication and agent identity",
    "Configuration",
    "Uninstall",
    "Troubleshooting",
]


def _headings(path: Path) -> list[str]:
    return re.findall(r"^#{1,6} (.+)$", path.read_text(encoding="utf-8"), re.M)


# --- AC2: the guide carries the whole skeleton --------------------------------


def test_guide_has_the_required_headings():
    heads = [head.strip() for head in _headings(GUIDE)]

    for required in REQUIRED_HEADINGS:
        assert required in heads, f"opencode/README.md lacks the heading '{required}'"


# --- AC3: every relative doc link resolves -------------------------------------


@pytest.mark.parametrize(
    "name", ["guide", "matrix", "integrations", "root"], ids=str
)
def test_relative_links_resolve(name):
    path = DOCS[name]
    base = path.parent

    broken = []
    for target in re.findall(r"\]\(([^)#]+?)(?:#[^)]*)?\)", path.read_text(encoding="utf-8")):
        target = target.strip()
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if not target:
            continue  # pure anchor link
        resolved = (base / target).resolve()
        if not resolved.exists():
            broken.append(target)

    assert broken == [], f"{path.name} has broken relative links: {broken}"


# --- AC4: documented memory install commands match the shipped CLI -------------


@pytest.mark.parametrize(
    "name", ["guide", "integrations", "root"], ids=str
)
def test_documented_memory_install_commands_match_the_cli(name):
    text = DOCS[name].read_text(encoding="utf-8")
    commands = re.findall(r"^memory install .*$", text, re.M)
    assert commands, f"{DOCS[name].name} should document at least one memory install command"

    for command in commands:
        tokens = command.split()
        sub = tokens[2] if len(tokens) > 2 else None
        if sub is None:
            continue
        result = CliRunner().invoke(cli, ["install", sub, "--help"])
        assert result.exit_code == 0 and "Usage" in result.output, (
            f"'{command}' does not match the CLI: install {sub!r} --help exited {result.exit_code}"
        )


# --- R9: the Verify section names the commands that prove the install ---------
def test_verify_section_names_the_proofs():
    text = GUIDE.read_text(encoding="utf-8")
    match = re.search(r"^## Verify\n(.*?)(?=^## )", text, re.M | re.S)
    assert match, "opencode/README.md lacks a Verify section"

    verify = match.group(1)

    assert "opencode mcp list" in verify, "Verify must name `opencode mcp list`"
    assert "tests/harness" in verify, "Verify must name the clean-room lab command"


# --- AC5: the integrations index names the installer ---------------------------


def test_integrations_names_the_opencode_installer():
    text = (REPO_ROOT / "docs" / "integrations.md").read_text(encoding="utf-8")

    assert "memory install opencode" in text, (
        "docs/integrations.md must name the OpenCode installer next to the Hermes one"
    )


# --- AC6: the root README shows the one-command install ------------------------


def test_root_readme_shows_the_installer():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "memory install opencode" in text, (
        "the root README OpenCode section must show the installer command"
    )


# --- AC7: no specs/ path in upstream-facing documents --------------------------


@pytest.mark.parametrize(
    "name", ["guide", "matrix", "integrations", "root"], ids=str
)
def test_no_specs_paths_leak_upstream(name):
    text = DOCS[name].read_text(encoding="utf-8")

    assert "specs/" not in text, f"{DOCS[name].name} must not reference internal specs/"


# --- AC8: the changelog fragment shape -----------------------------------------


def test_changelog_fragments_are_short_and_lead_bold():
    # SPEC-F009 R7 governs the OpenCode fragment. The lead-bold shape is the
    # house convention (changelog.d/README.md); we only assert it on the
    # fragment this PR adds, since we do not own the other fragments.
    fragment = REPO_ROOT / "changelog.d" / "harness-installer.feature.md"
    lines = fragment.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) <= 5, "the installer fragment grew past the 5-line budget"
    assert lines[0].startswith("- **"), "the installer fragment must lead with '- **'"
