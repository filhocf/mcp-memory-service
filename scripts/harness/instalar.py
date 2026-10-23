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
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import jsonc

PAYLOAD = Path(__file__).resolve().parent / "payload"
DEFAULT_PORT = 8000
SERVER_NAME = "mms"
MANIFEST_NAME = "mms-install-manifest.json"
OPENCODE_SCHEMA = "https://opencode.ai/config.json"


# --- harness descriptors -----------------------------------------------------


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
        ),
    }


def resolve_mcp_file(harness: Harness, root: Path) -> Path | None:
    """The file the installer should edit; the last candidate when none exists.

    Two candidate files at once are ambiguous: picking one would leave the other
    silently authoritative. Abort instead of guessing.
    """
    if harness.mcp_candidates:
        existing = [root / candidate for candidate in harness.mcp_candidates if (root / candidate).is_file()]
        if len(existing) > 1:
            raise RuntimeError("ambiguous configuration: both opencode.json and opencode.jsonc exist")
        if existing:
            return existing[0]
        return root / harness.mcp_candidates[-1]
    if harness.mcp_file is not None:
        return root / harness.mcp_file
    return None


def detect(roots: dict[str, Path] | None = None) -> list[str]:
    """Harnesses present on this machine (only those with a marker directory)."""
    roots = roots or {k: v.root_default for k, v in harnesses().items()}
    return [name for name, root in roots.items() if root.is_dir()]


# --- plan --------------------------------------------------------------------


@dataclass
class Action:
    kind: str  # "cli" | "merge-mcp" | "jsonc-mcp" | "copy"
    description: str
    argv: list[str] = field(default_factory=list)
    source: Path | None = None
    target: Path | None = None

    def render(self) -> str:
        if self.kind == "cli":
            return f"cli     {' '.join(self.argv)}"
        if self.kind == "merge-mcp":
            return f"merge   {self.target}"
        if self.kind == "jsonc-mcp":
            return f"jsonc   {self.target}"
        return f"copy    {self.source} -> {self.target}"


def _mcp_url(port: int) -> str:
    return f"http://localhost:{port}/mcp"


def api_key() -> str:
    """Bearer token for a key-protected server, when the operator set one.

    The streamable-http transport requires it on /mcp whenever MCP_API_KEY or
    OAuth is configured; assuming an open loopback server breaks the moment
    someone protects theirs.
    """
    return os.environ.get("MCP_API_KEY", "").strip()


def read_mcp_entry(path: Path) -> dict:
    """The `mms` entry from a harness JSON config, or {} when absent/unreadable."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    servers = data.get("mcpServers") or data.get("mcp_servers") or {}
    entry = servers.get(SERVER_NAME) if isinstance(servers, dict) else None
    return entry if isinstance(entry, dict) else {}


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


def entry_is_usable(entry: dict, port: int) -> bool:
    """A registration counts only if it is local, on THIS port, and enabled.

    Matching the name alone accepted a stale entry for another host on the same
    port, and a disabled one.
    """
    if not entry or entry.get("disabled") is True:
        return False
    try:
        parsed = urlparse(str(entry.get("url") or ""))
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return False
        if parsed.port != port:
            return False
    except ValueError:
        return False
    return parsed.path.rstrip("/") == "/mcp"


def _read_config(path: Path) -> str:
    """Read bytes and decode, so universal-newline translation cannot eat CRLF."""
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise jsonc.JsoncError(f"{path} is not valid UTF-8") from exc


def _opencode_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/mcp"


def opencode_entry(path: Path) -> dict:
    """`mcp.servers.mms`, else legacy `mcp.mms`, else {} (unreadable/invalid)."""
    if not path.is_file():
        return {}
    try:
        data = jsonc.load(_read_config(path))
    except (OSError, jsonc.JsoncError):
        return {}
    mcp = data.get("mcp")
    if not isinstance(mcp, dict):
        return {}
    servers = mcp.get("servers")
    if isinstance(servers, dict) and isinstance(servers.get(SERVER_NAME), dict):
        return servers[SERVER_NAME]
    legacy = mcp.get(SERVER_NAME)
    return legacy if isinstance(legacy, dict) else {}


def _write_atomic(path: Path, text: str) -> None:
    """Write through a same-directory temporary file, preserving the target.

    A symlinked config keeps its link: the real path is replaced, not the link.
    An existing read-only file is refused instead of silently rewritten, and a
    new file starts at 0600 because it may hold a bearer token.
    """
    real = Path(os.path.realpath(path))
    real.parent.mkdir(parents=True, exist_ok=True)
    mode = real.stat().st_mode & 0o777 if real.exists() else 0o600
    if real.exists() and not mode & 0o222:
        raise PermissionError(f"{real} is read-only; refusing to overwrite it")
    fd, temporary = tempfile.mkstemp(dir=real.parent, prefix=f"{real.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, real)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _opencode_registration(port: int) -> dict:
    entry: dict = {"type": "remote", "url": _opencode_url(port)}
    key = api_key()
    if key:
        entry["headers"] = {"Authorization": f"Bearer {key}"}
    return entry


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
        if harness.mcp_candidates:
            target = resolve_mcp_file(harness, root)
            actions.append(
                Action(
                    kind="jsonc-mcp",
                    description=f"register {SERVER_NAME} in {target.name}",
                    target=target,
                )
            )
        elif harness.mcp_file is not None:
            actions.append(
                Action(
                    kind="merge-mcp",
                    description=f"register {SERVER_NAME} in {harness.mcp_file}",
                    target=root / harness.mcp_file,
                )
            )
        elif harness.uses_cli:
            actions.append(
                Action(
                    kind="cli",
                    description=f"register {SERVER_NAME} via the harness CLI",
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
                Action(kind="copy", description=f"deposit {surface}", source=source, target=target)
            )

    if harness.hooks is not None:
        source = PAYLOAD / "agent-hooks" / harness.hooks.name
        target = root / harness.hooks
        if source.is_file() and not target.is_file():
            actions.append(
                Action(kind="copy", description="deposit hook", source=source, target=target)
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
            raise RuntimeError(f"{path} is not valid JSON; aborting without overwriting")
    servers = data.setdefault("mcpServers", {})
    entry: dict = {"url": _mcp_url(port), "autoApprove": _safe_autoapprove()}
    key = api_key()
    if key:
        entry["headers"] = {"Authorization": f"Bearer {key}"}
    servers[SERVER_NAME] = entry
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
                f"  failed: {' '.join(action.argv)}: "
                f"{(proc.stdout + proc.stderr).strip()[:160]}",
                file=sys.stderr,
            )
            return False
        return True
    if action.kind == "jsonc-mcp":
        if action.target is None:
            raise RuntimeError("jsonc-mcp action without a target")
        if action.target.is_file():
            text = _read_config(action.target)
        else:
            text = f'{{\n  "$schema": "{OPENCODE_SCHEMA}"\n}}\n'
        updated = jsonc.upsert(text, ["mcp", "servers", SERVER_NAME], _opencode_registration(port))
        _write_atomic(action.target, updated)
        return True
    if action.kind == "merge-mcp":
        if action.target is None:
            raise RuntimeError("merge-mcp action without a target")
        merge_mcp(action.target, port)
        return True
    if action.kind == "copy":
        if action.source is None or action.target is None:
            raise RuntimeError("copy action without source or target")
        action.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(action.source, action.target)
        return True
    return False


# --- verify ------------------------------------------------------------------


def verify(harness: Harness, root: Path, port: int) -> list[str]:
    """Post-write effects that must hold; returns the failures."""
    failures: list[str] = []

    if harness.mcp_candidates:
        target = resolve_mcp_file(harness, root)
        if target is None or not entry_is_usable(opencode_entry(target), port):
            failures.append(
                f"{SERVER_NAME} missing, disabled, or not pointing at :{port}/mcp "
                f"in {target.name if target else 'the OpenCode config'}"
            )
    elif harness.mcp_file is not None:
        if not entry_is_usable(read_mcp_entry(root / harness.mcp_file), port):
            failures.append(
                f"{SERVER_NAME} missing, disabled, or not pointing at :{port}/mcp "
                f"in {harness.mcp_file}"
            )
    elif harness.uses_cli:
        if not cli_mcp_present(harness.uses_cli, root):
            failures.append(f"{SERVER_NAME} not listed by the harness CLI")

    for surface, rel in (("steering", harness.steering), ("skill", harness.skill)):
        if rel is not None and not (root / rel).is_file():
            failures.append(f"{surface} not deposited at {rel}")

    if harness.hooks is not None and not (root / harness.hooks).is_file():
        failures.append(f"hook not deposited at {harness.hooks}")

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

    if harness.mcp_candidates:
        target = resolve_mcp_file(harness, root)
        if target is not None and target.is_file():
            text = _read_config(target)
            updated = jsonc.remove(text, ["mcp", "servers", SERVER_NAME])
            updated = jsonc.remove(updated, ["mcp", SERVER_NAME])
            if updated != text:
                _write_atomic(target, updated)
                removed.append(f"{SERVER_NAME} de {target}")
    elif harness.mcp_file is not None:
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
        root_resolved = root.resolve()
        for entry in entries:
            target = Path(entry)
            resolved = Path(os.path.realpath(target))
            if not resolved.is_relative_to(root_resolved):
                continue
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
            target = h.mcp_file or (h.mcp_candidates[-1] if h.mcp_candidates else None) or h.uses_cli
            print(f"{name:8s} root={h.root_default}  mcp={target}")
        return 0

    names = [args.harness] if args.harness != "auto" else detect()
    if not names:
        print("no harness detected (looked for ~/.hermes, ~/.kiro, and the OpenCode config)")
        return 1

    # Uninstalling must work with the service down: that is often why you are uninstalling.
    if not args.skip_health and not args.dry_run and not args.uninstall:
        try:
            import urllib.error
            import urllib.request

            request = urllib.request.Request(f"http://localhost:{args.port}/health")
            key = api_key()
            if key:
                request.add_header("Authorization", f"Bearer {key}")
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            hint = " (the server requires a key: set MCP_API_KEY)" if exc.code == 401 else ""
            print(f"error: /health returned {exc.code}{hint}; nothing was written")
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"error: service not answering on :{args.port} ({exc}); nothing was written")
            return 1

    rc = 0
    for name in names:
        harness = registry[name]
        root = Path(args.root) if args.root else harness.root_default

        if args.uninstall:
            print(f"{name}: uninstall from {root}")
            try:
                removed = uninstall(harness, root) if not args.dry_run else []
            except (RuntimeError, jsonc.JsoncError, OSError) as exc:
                print(f"  error: {exc}; nothing was written", file=sys.stderr)
                rc = 1
                continue
            for item in removed:
                print(f"  removed: {item}")
            continue

        try:
            if harness.mcp_candidates:
                target = resolve_mcp_file(harness, root)
                installed = target is not None and entry_is_usable(opencode_entry(target), args.port)
            else:
                installed = (
                    entry_is_usable(read_mcp_entry(root / harness.mcp_file), args.port)
                    if harness.mcp_file
                    else False
                )
            cli_present = cli_mcp_present(harness.uses_cli, root) if harness.uses_cli else False
            actions = plan_for(harness, root, args.port, installed, cli_present)
        except (RuntimeError, jsonc.JsoncError, OSError) as exc:
            print(f"  error: {exc}; nothing was written", file=sys.stderr)
            rc = 1
            continue

        print(f"\n{name} ({root})")
        if not actions:
            print("  nothing to do: already installed")
            continue
        for action in actions:
            print(f"  {action.render()}")

        if args.dry_run:
            continue

        try:
            ok = all(run_action(a, args.port, dry_run=False, root=root) for a in actions)
        except (RuntimeError, jsonc.JsoncError, OSError) as exc:
            print(f"  error: {exc}; nothing was written", file=sys.stderr)
            rc = 1
            continue
        if not ok:
            rc = 1
            continue

        try:
            failures = verify(harness, root, args.port)
        except (RuntimeError, jsonc.JsoncError, OSError) as exc:
            print(f"  error: {exc}; the effect could not be verified", file=sys.stderr)
            rc = 1
            continue
        if failures:
            rc = 1
            for failure in failures:
                print(f"  ERRO: {failure}", file=sys.stderr)
            continue

        write_manifest(root, actions)
        print(f"  OK: {len(actions)} action(s), effect verified")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
