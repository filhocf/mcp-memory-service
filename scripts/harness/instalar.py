#!/usr/bin/env python3
"""Install the memory-service as a first-class client of a harness.

Installing an MCP server is not one config line: it is depositing a payload into
every surface the harness reads — registration, steering, skill, hooks. This
installer does that for the harnesses we actually run, detects which are present,
prints the exact plan before writing, and verifies the effect afterwards.

Method modelled on `codebase-memory-mcp install` (see docs/agents/installer-method.md).

Usage:
    python scripts/harness/instalar.py                      # detect and install
    python scripts/harness/instalar.py --dry-run            # print the plan only
    python scripts/harness/instalar.py --harness kiro       # force one harness
    python scripts/harness/instalar.py --root /tmp/sandbox  # ad-hoc sandbox
    python scripts/harness/instalar.py --uninstall
    python scripts/harness/instalar.py --list
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PAYLOAD = Path(__file__).resolve().parent / "payload"
DEFAULT_PORT = 3202
SERVER_NAME = "mms"
MANIFEST_NAME = "mms-install-manifest.json"


# --- harness descriptors -----------------------------------------------------


@dataclass(frozen=True)
class Harness:
    """Where a harness keeps each surface, relative to its root."""

    name: str
    root_default: Path
    mcp_file: Path | None = None  # JSON config we can merge
    uses_cli: tuple[str, ...] = ()  # CLI used for registration instead of JSON merge
    steering: Path | None = None
    skill: Path | None = None
    hooks: Path | None = None


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
    }


def detect(roots: dict[str, Path] | None = None) -> list[str]:
    """Harnesses present on this machine (only those with a marker directory)."""
    roots = roots or {k: v.root_default for k, v in harnesses().items()}
    return [name for name, root in roots.items() if root.is_dir()]


# --- plan --------------------------------------------------------------------


@dataclass
class Action:
    kind: str  # "cli" | "merge-mcp" | "copy"
    description: str
    argv: list[str] = field(default_factory=list)
    source: Path | None = None
    target: Path | None = None

    def render(self) -> str:
        if self.kind == "cli":
            return f"cli     {' '.join(self.argv)}"
        if self.kind == "merge-mcp":
            return f"merge   {self.target}"
        return f"copy    {self.source} -> {self.target}"


def _mcp_url(port: int) -> str:
    return f"http://localhost:{port}/mcp"


def read_mcp_names(path: Path) -> set[str]:
    """Server names registered in a harness JSON config (tolerates corruption)."""
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    servers = data.get("mcpServers") or data.get("mcp_servers") or {}
    return set(servers) if isinstance(servers, dict) else set()


def cli_mcp_present(argv_prefix: tuple[str, ...], root: Path) -> bool:
    """Ask the harness CLI about *this* root, not the developer's real one."""
    env = {**os.environ, "HERMES_HOME": str(root)}
    try:
        proc = subprocess.run(
            [*argv_prefix[:2], "list"],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return any(line.split()[:1] == [SERVER_NAME] for line in proc.stdout.splitlines())


def plan_for(
    harness: Harness, root: Path, port: int, installed: bool, cli_present: bool
) -> list[Action]:
    actions: list[Action] = []

    if not (installed or cli_present):
        if harness.mcp_file is not None:
            actions.append(
                Action(
                    kind="merge-mcp",
                    description=f"registrar {SERVER_NAME} em {harness.mcp_file}",
                    target=root / harness.mcp_file,
                )
            )
        elif harness.uses_cli:
            actions.append(
                Action(
                    kind="cli",
                    description=f"registrar {SERVER_NAME} via CLI do harness",
                    argv=[*harness.uses_cli, SERVER_NAME, "--url", _mcp_url(port)],
                )
            )

    for surface, rel in (("steering", harness.steering), ("skill", harness.skill)):
        if rel is None:
            continue
        source = PAYLOAD / surface / rel.name
        if surface == "skill":
            source = PAYLOAD / "skills" / rel.parent.name / rel.name
        target = root / rel
        if source.is_file() and not target.is_file():
            actions.append(
                Action(kind="copy", description=f"depositar {surface}", source=source, target=target)
            )

    if harness.hooks is not None:
        source = PAYLOAD / "agent-hooks" / harness.hooks.name
        target = root / harness.hooks
        if source.is_file() and not target.is_file():
            actions.append(
                Action(kind="copy", description="depositar hook", source=source, target=target)
            )

    return actions


# --- apply -------------------------------------------------------------------


def merge_mcp(path: Path, port: int) -> None:
    """Merge the server into a harness JSON config, preserving everything else."""
    data: dict = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            raise RuntimeError(f"{path} nao e JSON valido; abortando sem sobrescrever")
    servers = data.setdefault("mcpServers", {})
    servers[SERVER_NAME] = {"url": _mcp_url(port), "autoApprove": _safe_autoapprove()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _safe_autoapprove() -> list[str]:
    """Tools cheap enough to approve blindly; inventory/LLM ones stay manual."""
    return [
        "memory_store",
        "memory_search",
        "memory_update",
        "memory_delete",
        "mistake_note_add",
        "mistake_note_search",
    ]


def run_action(action: Action, port: int, dry_run: bool, root: Path) -> bool:
    if dry_run:
        return True
    if action.kind == "cli":
        proc = subprocess.run(
            action.argv,
            capture_output=True,
            text=True,
            timeout=180,
            input="Y\n" * 5,
            env={**os.environ, "HERMES_HOME": str(root)},
        )
        if proc.returncode != 0:
            print(
                f"  falhou: {' '.join(action.argv)}: "
                f"{(proc.stdout + proc.stderr).strip()[:160]}",
                file=sys.stderr,
            )
            return False
        return True
    if action.kind == "merge-mcp":
        if action.target is None:
            raise RuntimeError("merge-mcp sem target")
        merge_mcp(action.target, port)
        return True
    if action.kind == "copy":
        if action.source is None or action.target is None:
            raise RuntimeError("copy sem origem ou destino")
        action.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(action.source, action.target)
        return True
    return False


# --- verify ------------------------------------------------------------------


def verify(harness: Harness, root: Path, port: int) -> list[str]:
    """Post-write effects that must hold; returns the failures."""
    failures: list[str] = []

    if harness.mcp_file is not None:
        if SERVER_NAME not in read_mcp_names(root / harness.mcp_file):
            failures.append(f"{SERVER_NAME} ausente em {harness.mcp_file}")
    elif harness.uses_cli:
        if not cli_mcp_present(harness.uses_cli, root):
            failures.append(f"{SERVER_NAME} nao aparece no `hermes mcp list`")

    for surface, rel in (("steering", harness.steering), ("skill", harness.skill)):
        if rel is not None and not (root / rel).is_file():
            failures.append(f"{surface} nao depositado em {rel}")

    if harness.hooks is not None and not (root / harness.hooks).is_file():
        failures.append(f"hook nao depositado em {harness.hooks}")

    return failures


def write_manifest(root: Path, actions: list[Action]) -> None:
    """Record only files this installer CREATED.

    A `merge-mcp` target is a pre-existing config file that we edited, never a
    file we own: listing it here would make `uninstall` delete the harness's whole
    MCP config (14 servers on a real machine). The server is removed by key.
    """
    entries = [
        str(a.target) for a in actions if a.kind == "copy" and a.target is not None
    ]
    (root / MANIFEST_NAME).write_text(json.dumps({"created": entries}, indent=2) + "\n")


def uninstall(harness: Harness, root: Path) -> list[str]:
    """Undo the installation: remove the server by key, then created files."""
    removed: list[str] = []

    if harness.mcp_file is not None:
        config = root / harness.mcp_file
        if config.is_file():
            try:
                data = json.loads(config.read_text())
            except json.JSONDecodeError:
                data = None
            servers = (data or {}).get("mcpServers", {})
            if servers.pop(SERVER_NAME, None) is not None:
                config.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
                removed.append(f"{SERVER_NAME} de {config}")
    elif harness.uses_cli:
        try:
            subprocess.run(
                [*harness.uses_cli[:2], "remove", SERVER_NAME],
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "HERMES_HOME": str(root)},
            )
            removed.append(f"{SERVER_NAME} via CLI do harness")
        except (OSError, subprocess.SubprocessError):
            pass

    path = root / MANIFEST_NAME
    if path.is_file():
        try:
            entries = json.loads(path.read_text()).get("created") or []
        except (OSError, json.JSONDecodeError):
            entries = []
        for entry in entries:
            target = Path(entry)
            if target.is_file():
                target.unlink()
                removed.append(str(target))
        path.unlink()
        removed.append(str(path))

    return removed


# --- CLI ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", default="auto", choices=["auto", *harnesses()])
    parser.add_argument("--root", default=None, help="harness root (ad-hoc sandbox)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--list", action="store_true", help="list supported harnesses")
    parser.add_argument("--skip-health", action="store_true")
    args = parser.parse_args(argv)

    registry = harnesses()

    if args.list:
        for name, h in registry.items():
            print(f"{name:8s} root={h.root_default}  mcp={h.mcp_file or h.uses_cli}")
        return 0

    names = [args.harness] if args.harness != "auto" else detect()
    if not names:
        print("nenhum harness detectado (procurando ~/.hermes e ~/.kiro)")
        return 1

    if not args.skip_health and not args.dry_run:
        try:
            import urllib.request

            urllib.request.urlopen(f"http://localhost:{args.port}/health", timeout=5)
        except Exception as exc:  # noqa: BLE001
            print(f"erro: servico nao responde em :{args.port} ({exc}); nada foi escrito")
            return 1

    rc = 0
    for name in names:
        harness = registry[name]
        root = Path(args.root) if args.root else harness.root_default

        if args.uninstall:
            print(f"{name}: uninstall em {root}")
            for item in uninstall(harness, root) if not args.dry_run else []:
                print(f"  removido: {item}")
            continue

        installed = (
            SERVER_NAME in read_mcp_names(root / harness.mcp_file)
            if harness.mcp_file
            else False
        )
        cli_present = cli_mcp_present(harness.uses_cli, root) if harness.uses_cli else False
        actions = plan_for(harness, root, args.port, installed, cli_present)

        print(f"\n{name} ({root})")
        if not actions:
            print("  nada a fazer: instalacao ja completa")
            continue
        for action in actions:
            print(f"  {action.render()}")

        if args.dry_run:
            continue

        ok = all(run_action(a, args.port, dry_run=False, root=root) for a in actions)
        if not ok:
            rc = 1
            continue

        failures = verify(harness, root, args.port)
        if failures:
            rc = 1
            for failure in failures:
                print(f"  ERRO: {failure}", file=sys.stderr)
            continue

        write_manifest(root, actions)
        print(f"  OK: {len(actions)} acao(oes), efeito verificado")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
