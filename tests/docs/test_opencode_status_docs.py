"""Documentation tests for the OpenCode first-class status and agent onboarding.

These are RED on the merged upstream tree: the status section, the five-layer
table, and the eight-item onboarding checklist do not exist yet. They become
green with SPEC-F010.

The tests assert the promises a reader relies on, not prose: the table has one
row per layer, layer 4 is honestly red, the existing plugin is credited, the
OpenCode row in the index points at the status, and no upstream-facing page
leaks the internal `specs/` tree.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATUS_README = REPO / "opencode" / "README.md"
AGENTS_README = REPO / "agents" / "README.md"
CONTRIBUTING = REPO / "CONTRIBUTING.md"
UPSTREAM_FACING = [
    AGENTS_README,
    STATUS_README,
    REPO / "docs" / "integrations.md",
    REPO / "README.md",
]

STATUS_HEADING = "## First-class status"
ADDING_HEADING = "## Adding an agent"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """Return the body of a level-2 section, up to the next level-2 heading."""
    match = re.search(rf"^{re.escape(heading)}\s*$", text, re.MULTILINE)
    assert match, f"missing heading {heading!r}"
    body = text[match.end() :]
    next_heading = re.search(r"^## ", body, re.MULTILINE)
    return body[: next_heading.start()] if next_heading else body


def _table_rows(section: str) -> list[str]:
    return [line for line in section.splitlines() if line.startswith("|")]


# --- opencode/README.md: first-class status ---------------------------------


def test_status_section_exists() -> None:
    assert STATUS_HEADING in _read(STATUS_README)


def test_status_table_has_one_row_per_layer() -> None:
    rows = _table_rows(_section(_read(STATUS_README), STATUS_HEADING))
    numbered = [int(m.group(1)) for row in rows if (m := re.match(r"\|\s*([1-5])\.", row))]
    assert numbered == [1, 2, 3, 4, 5], f"layer rows: {numbered}"


def test_layer_four_is_not_overclaimed() -> None:
    rows = _table_rows(_section(_read(STATUS_README), STATUS_HEADING))
    layer_four = next(row for row in rows if re.match(r"\|\s*4\.", row))
    assert "🔴" in layer_four, layer_four


def test_existing_contribution_is_credited() -> None:
    section = _section(_read(STATUS_README), STATUS_HEADING)
    assert "memory-plugin.js" in section
    assert re.search(r"V1/V2|V2 adapter", section), "the V1/V2 adapter is not named"


def test_document_does_not_claim_a_model_backed_test() -> None:
    section = _section(_read(STATUS_README), STATUS_HEADING).lower()
    assert "not claimed" in section or "not claim" in section
    assert "model-backed" in section


# --- agents/README.md: index row and onboarding ------------------------------


def test_opencode_index_row_points_at_the_status() -> None:
    text = _read(AGENTS_README)
    row = next(line for line in text.splitlines() if "OpenCode" in line and line.startswith("|"))
    assert "opencode/README.md#first-class-status" in row, row
    assert "installer" in row.lower(), row
    assert "skill" in row.lower(), row
    assert "none shipped" not in row.lower(), row


def test_onboarding_checklist_has_eight_items() -> None:
    section = _section(_read(AGENTS_README), ADDING_HEADING)
    numbers = [int(m.group(1)) for line in section.splitlines() if (m := re.match(r"^(\d+)\. \*\*", line))]
    assert numbers == list(range(1, 9)), numbers


def test_onboarding_checklist_names_every_surface_and_the_lab() -> None:
    section = _section(_read(AGENTS_README), ADDING_HEADING)
    for surface in (
        "`agents/README.md`",
        "`docs/integrations.md`",
        "root `README.md`",
        "integration README",
        "`changelog.d/`",
        "wiki",
    ):
        assert surface in section, f"checklist omits {surface}"
    assert "sandbox" in section.lower(), "checklist omits the sandbox requirement"


def test_contributing_links_to_the_checklist() -> None:
    assert "agents/README.md#adding-an-agent" in _read(CONTRIBUTING)


# --- boundaries and links ----------------------------------------------------


def test_upstream_facing_docs_do_not_link_internal_specs() -> None:
    for path in UPSTREAM_FACING:
        assert "specs/" not in _read(path), f"{path} leaks the internal specs tree"


def _slug(heading: str) -> str:
    text = heading.lstrip("#").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text)


def test_relative_links_in_touched_docs_resolve() -> None:
    for path in (AGENTS_README, STATUS_README):
        text = _read(path)
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            file_part, _, anchor = target.partition("#")
            resolved = (path.parent / file_part).resolve()
            assert resolved.exists(), f"{path}: broken link {target}"
            if anchor and resolved.suffix == ".md":
                headings = [_slug(line) for line in _read(resolved).splitlines() if line.startswith("#")]
                assert anchor in headings, f"{path}: missing anchor {target}"
