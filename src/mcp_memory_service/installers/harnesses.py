"""Where each supported harness keeps every surface, relative to its root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Harness:
    """Where a harness keeps each surface, relative to its root."""

    name: str
    root_default: Path
    mcp_file: Path | None = None  # JSON config we can merge
    mcp_candidates: tuple[Path, ...] = ()  # ordered alternatives; last is the creation target
    uses_cli: tuple[str, ...] = ()  # CLI used for registration instead of JSON merge
    steering: Path | None = None
    skill: Path | None = None
    hooks: Path | None = None
    agents: Path | None = None  # a file with a marker-delimited managed block


def _opencode_root(home: Path) -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return (Path(xdg) if xdg else home / ".config") / "opencode"


def harnesses() -> dict[str, Harness]:
    home = Path.home()
    return {
        "hermes": Harness(
            name="hermes",
            root_default=home / ".hermes",
            uses_cli=("hermes", "mcp", "add"),
            skill=Path("skills") / "mms-uso" / "SKILL.md",
            hooks=Path("agent-hooks") / "mms_agent_stamp.py",
        ),
        "kiro": Harness(
            name="kiro",
            root_default=home / ".kiro",
            mcp_file=Path("settings") / "mcp.json",
            steering=Path("steering") / "mms.md",
            skill=Path("skills") / "mms-uso" / "SKILL.md",
        ),
        "opencode": Harness(
            name="opencode",
            root_default=_opencode_root(home),
            mcp_candidates=(Path("opencode.jsonc"), Path("opencode.json")),
            skill=Path("skills") / "mms-uso" / "SKILL.md",
            agents=Path("AGENTS.md"),
        ),
    }


__all__ = ["Harness", "harnesses"]
