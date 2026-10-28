"""RED tests for SPEC-F004 — the harness-neutral usage skill.

The payload skill is the only text the installer deposits into every harness
that declares a skill surface. These tests pin its contract: neutral identity
(R1), discovery and triggers (R2/R3), the measured doctrine (R4), a portable
endpoint (R5), the authorship rule (R6), the size budget (R7), and the deposit
path per harness (AC4).

Every install runs in tmp_path via --root: neither ~/.kiro, ~/.hermes, nor
~/.config/opencode is ever touched.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "harness"))

PAYLOAD_SKILL = (
    REPO_ROOT / "src" / "mcp_memory_service" / "installers" / "payload" / "skills" / "mms-uso" / "SKILL.md"
)

# R1: no harness name survives in neutral text.
FORBIDDEN_NAMES = ("kiro", "hermes", "opencode")
FORBIDDEN_PORT = re.compile(r":\d{4,5}")

# The English headings the shipped skill is expected to carry. The check is
# deliberately loose: any three of them prove the body is English prose.
ENGLISH_MARKERS = (
    "before acting",
    "how to search",
    "what to store",
    "pitfalls",
    "authorship",
    "store and tag",
)


def _mod():
    return importlib.import_module("instalar")


@pytest.fixture(scope="module")
def raw() -> str:
    return PAYLOAD_SKILL.read_text(encoding="utf-8")


def _frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Parse the leading `---` block, folding indented continuation lines.

    Only the two scalar fields the contract names are understood; anything else
    is ignored rather than interpreted, so the parser cannot reject a valid
    skill for a reason the spec never asked for.
    """
    lines = raw.splitlines()
    assert lines, "the payload skill is empty"
    assert lines[0].strip() == "---", "the payload skill has no opening frontmatter fence"
    close = next((i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if close is None:
        pytest.fail("the payload skill has no closing frontmatter fence")

    fields: dict[str, str] = {}
    current: str | None = None
    for line in lines[1:close]:
        match = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if match:
            current = match.group(1)
            fields[current] = match.group(2).strip()
        elif current is not None and line[:1] in {" ", "\t"}:
            fields[current] = f"{fields[current]} {line.strip()}".strip()
    fields = {key: value.strip().strip('"').strip("'").strip() for key, value in fields.items()}
    return fields, "\n".join(lines[close + 1 :])


def _line_of(raw: str, needle: str) -> int | None:
    for index, line in enumerate(raw.splitlines()):
        if needle in line:
            return index
    return None


# --- R1. neutral identity ----------------------------------------------------


def test_skill_names_no_harness_and_no_literal_port(raw):
    lowered = raw.lower()
    named = [name for name in FORBIDDEN_NAMES if name in lowered]
    port = FORBIDDEN_PORT.search(raw)

    assert named == [] and port is None, (
        "neutral identity broken: "
        f"harnesses named={named}, literal port={port.group(0) if port else None}"
    )


# --- R7. size budget ---------------------------------------------------------


def test_skill_stays_within_the_line_budget(raw):
    assert len(raw.splitlines()) <= 90


# --- R2/R3. discovery and trigger -------------------------------------------


def test_frontmatter_declares_the_skill_id_and_a_description(raw):
    fields, _ = _frontmatter(raw)

    assert fields.get("name") == "mms-uso"
    assert fields.get("description", "").strip(), "the description is empty"


def test_description_triggers_on_state_and_prior_decisions(raw):
    fields, _ = _frontmatter(raw)
    description = fields.get("description", "").lower()

    triggers = ("decision", "project state", "left off")
    assert any(trigger in description for trigger in triggers), (
        "the description must name state/recall questions, not a generic memory label: "
        f"{description!r}"
    )


# --- R4. measured doctrine ---------------------------------------------------


def test_search_instruction_caps_the_limit_at_three(raw):
    found = [int(value) for value in re.findall(r"\blimit\b[^\n]{0,24}?(\d+)", raw)]

    assert found, "the skill no longer documents the `limit` knob"
    assert min(found) <= 3, f"no search limit <= 3 is instructed: {found}"


def test_search_instruction_caps_the_response_size(raw):
    found = [int(value) for value in re.findall(r"\bmax_response_chars\b[^\n]{0,24}?(\d+)", raw)]

    assert found, "the skill no longer documents `max_response_chars`"
    assert min(found) <= 2000, f"no max_response_chars <= 2000 is instructed: {found}"


def test_cost_figures_carry_their_measurement_date(raw):
    lines = raw.splitlines()
    date_line = _line_of(raw, "2026-10-20")

    assert date_line is not None, "the measured cost figures lost their measurement date"
    window = "\n".join(lines[max(0, date_line - 10) : date_line + 11]).lower()
    assert "token" in window, "the measurement date is not next to any measured cost figure"


def test_store_and_tag_guidance_survives(raw):
    lowered = raw.lower()

    assert "store" in lowered, "the store/tag guidance is gone"
    assert "tag" in lowered, "the store/tag guidance is gone"
    assert "default" in lowered or "null" in lowered, (
        "the store guidance no longer says how to scope a project memory"
    )


# --- R5. portable endpoint ---------------------------------------------------


def test_endpoint_is_the_registered_server_without_a_url(raw):
    lowered = raw.lower()

    assert "mms" in lowered, "the skill does not name the `mms` server"
    assert "regist" in lowered, "the skill does not say the server is registered"
    assert "installer" in lowered, "the skill does not defer the endpoint to the installer"
    assert "http://" not in lowered and "https://" not in lowered, (
        "the skill embeds an endpoint URL"
    )


# --- R6. authorship ----------------------------------------------------------


def test_authorship_comes_from_the_transport_and_is_not_invented(raw):
    lowered = raw.lower()

    assert "agent_id" in lowered, "the authorship rule is gone"
    assert "transport" in lowered or "harness" in lowered, (
        "the skill does not say where agent_id comes from"
    )
    # Word boundary: the Portuguese "inventário" must not satisfy this.
    assert re.search(r"\binvent(?:ed|ing|s)?\b", lowered), (
        "the skill does not forbid inventing agent_id"
    )


def test_skill_does_not_offer_a_literal_agent_id_to_copy(raw):
    assert re.search(r"agent_id\s*=\s*[\"']?[A-Za-z<{]", raw) is None, (
        "the skill shows a literal agent_id, inviting the model to choose one"
    )


# --- language and scope ------------------------------------------------------


def test_body_is_english(raw):
    _, body = _frontmatter(raw)
    lowered = body.lower()
    present = [marker for marker in ENGLISH_MARKERS if marker in lowered]

    assert len(present) >= 3, f"the skill body is not English prose; found {present}"


def test_skill_does_not_reference_the_out_of_scope_cost_skill(raw):
    assert "mms-custo" not in raw.lower(), (
        "the skill still references the mms-custo skill, which this installer does not ship"
    )


# --- AC4. deposit per harness ------------------------------------------------


@pytest.mark.parametrize("harness_name", ["kiro", "hermes", "opencode"])
def test_installer_deposits_the_skill_for_each_harness(tmp_path, monkeypatch, harness_name):
    """The skill is a copy action, independent of the harness CLI being present.

    Hermes registers through its CLI, which may not exist on a given machine:
    stubbing the probe keeps this test about the deposit alone, and the clean
    root plus --skip-health keep it off the network and out of $HOME.
    """
    instalar = _mod()
    # Patch where `core.main` resolves the name: the script shim re-exports
    # copies, so patching the shim would silently miss `main`'s lookup.
    monkeypatch.setattr(instalar.core, "cli_mcp_present", lambda *args, **kwargs: True)
    root = tmp_path / harness_name

    rc = instalar.main(["--harness", harness_name, "--root", str(root), "--skip-health"])

    deposited = root / "skills" / "mms-uso" / "SKILL.md"
    assert rc == 0
    assert deposited.is_file(), f"{harness_name} install did not deposit the skill at {deposited}"
    assert deposited.read_bytes() == PAYLOAD_SKILL.read_bytes()
