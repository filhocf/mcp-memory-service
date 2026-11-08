"""Where each supported harness keeps every surface, relative to its root."""

from __future__ import annotations

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
    # Measured (OpenCode 2.1.3, Oct 2026): the client resolves its config from
    # $HOME/.config/opencode and does NOT consult XDG_CONFIG_HOME — honouring
    # XDG here would register mms into a file the client never reads.
    return home / ".config" / "opencode"


def harnesses() -> dict[str, Harness]:
    home = Path.home()
    return {
        "opencode": Harness(
            name="opencode",
            root_default=_opencode_root(home),
            mcp_candidates=(Path("opencode.jsonc"), Path("opencode.json")),
            skill=Path("skills") / "mms-uso" / "SKILL.md",
            agents=Path("AGENTS.md"),
        ),
    }


__all__ = ["Harness", "harnesses"]
