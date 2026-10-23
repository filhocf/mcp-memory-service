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
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import jsonc

PAYLOAD = Path(__file__).resolve().parent / "payload"
DEFAULT_PORT = 8000
SERVER_NAME = "mms"
MANIFEST_NAME = "mms-install-manifest.json"
OPENCODE_SCHEMA = "https://opencode.ai/config.json"

# The plugin ships from the repository; nothing is transpiled or bundled.
REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SOURCE = REPO_ROOT / "opencode" / "memory-plugin.js"
PLUGIN_REL_DIR = Path("plugins") / "opencode-memory"
PLUGIN_CONFIG = "memory-plugin.json"
PLUGIN_LEGACY_CONFIG = "memory-awareness.json"
PLUGIN_PACKAGE_NAME = "opencode-memory"


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


# --- opencode plugin deposit -------------------------------------------------


@dataclass
class Deposit:
    """A file the installer creates for the OpenCode plugin surface."""

    kind: str  # "copy" | "write"
    description: str
    target: Path
    source: Path | None = None
    text: str | None = None

    def render(self) -> str:
        if self.kind == "copy":
            return f"deposit {self.description} -> {self.target}"
        return f"write   {self.description} -> {self.target}"


def project_version() -> str:
    """The MMS version, from pyproject.toml and then installed metadata."""
    try:
        with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
            return str(tomllib.load(handle)["project"]["version"])
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        try:
            from importlib.metadata import PackageNotFoundError, version

            try:
                return version("mcp-memory-service")
            except PackageNotFoundError:
                return "0.0.0"
        except Exception:  # noqa: BLE001 - the package metadata is best effort
            return "0.0.0"


def plugin_package_json(version: str | None = None) -> str:
    payload = {
        "name": PLUGIN_PACKAGE_NAME,
        "version": version or project_version(),
        "type": "module",
        "exports": {".": "./index.js"},
    }
    return json.dumps(payload, indent=2) + "\n"


def plugin_config_json(port: int) -> str:
    """Only the keys the installer decides; the plugin owns every other default."""
    payload = {
        "memoryService": {
            "endpoint": f"http://127.0.0.1:{port}",
            "timeoutMs": 5000,
            "loadTimeoutMs": 2500,
            "maxMemoriesPerSession": 8,
        }
    }
    return json.dumps(payload, indent=2) + "\n"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _resolved(path: Path) -> Path:
    return Path(os.path.realpath(path))


def read_manifest(root: Path) -> dict:
    """The manifest, tolerating corruption: an unreadable one records nothing."""
    empty: dict = {"created": [], "created_dirs": []}
    path = root / MANIFEST_NAME
    if not path.is_file():
        return empty
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(data, dict):
        return empty
    created = data.get("created") if isinstance(data.get("created"), list) else []
    dirs = data.get("created_dirs") if isinstance(data.get("created_dirs"), list) else []
    return {"created": created, "created_dirs": dirs}


def _entry_path(entry: object, root: Path) -> Path | None:
    """The path of a manifest entry, whether it is an object or a legacy string."""
    raw = entry.get("path") if isinstance(entry, dict) else entry
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else root / path


def owned_hashes(root: Path) -> dict[Path, str]:
    """Recorded hashes by resolved path; legacy strings carry no hash."""
    owned: dict[Path, str] = {}
    for entry in read_manifest(root)["created"]:
        if not isinstance(entry, dict):
            continue
        path = _entry_path(entry, root)
        digest = entry.get("sha256")
        if path is not None and isinstance(digest, str) and digest:
            owned[_resolved(path)] = digest
    return owned


def _plan_deposit(
    deposits: list[Deposit],
    target: Path,
    expected: bytes,
    description: str,
    owned: dict[Path, str],
    source: Path | None = None,
    text: str | None = None,
) -> None:
    """Plan a create, a no-op, or an upgrade; refuse a file we cannot prove is ours."""
    if not target.is_file():
        deposits.append(
            Deposit(kind="copy" if source else "write", description=description,
                    target=target, source=source, text=text)
        )
        return
    current = target.read_bytes()
    if current == expected:
        return
    recorded = owned.get(_resolved(target))
    if recorded is not None and recorded == _sha256_bytes(current):
        # The manifest proves we wrote this exact file: an upgrade may replace it.
        deposits.append(
            Deposit(kind="copy" if source else "write", description=description,
                    target=target, source=source, text=text)
        )
        return
    raise RuntimeError(
        f"foreign plugin file at {target}: it differs from the shipped plugin and the "
        "manifest does not record it; refusing to overwrite"
    )


def missing_dirs(root: Path, targets: list[Path]) -> list[Path]:
    """Directories a deposit creates, parents first, never including the root."""
    root_resolved = _resolved(root)
    missing: list[Path] = []
    for target in targets:
        parent = _resolved(target).parent
        chain: list[Path] = []
        while parent != root_resolved and parent.is_relative_to(root_resolved) and not parent.exists():
            chain.append(parent)
            parent = parent.parent
        for directory in reversed(chain):
            if directory not in missing:
                missing.append(directory)
    return missing


def _contained(path: Path, root: Path) -> Path:
    """The resolved path, refusing one that escapes the root.

    `plugins` may be a symlink pointing anywhere; resolving before writing keeps a
    deposit inside the sandbox the operator named.
    """
    resolved = _resolved(path)
    if not resolved.is_relative_to(_resolved(root)):
        raise RuntimeError(f"plugin path escapes the root: {path} -> {resolved}")
    return resolved


def plan_plugin(root: Path, port: int) -> tuple[list[Deposit], list[Path], list[str]]:
    """Plan the plugin package and its configuration bootstrap.

    Raises RuntimeError for a foreign `index.js`/`package.json`: overwriting a file
    the installer cannot prove it wrote would destroy someone's work. Also raises
    when any planned path resolves outside the root: a symlinked `plugins`
    directory must not smuggle the payload out of the sandbox.
    """
    if not PLUGIN_SOURCE.is_file():
        raise RuntimeError(f"plugin source not found at {PLUGIN_SOURCE}")

    plugin_dir = root / PLUGIN_REL_DIR
    index = plugin_dir / "index.js"
    package = plugin_dir / "package.json"
    # Validate containment before planning anything: nothing is written on abort.
    for target in (index, package, root / PLUGIN_CONFIG):
        _contained(target, root)
    owned = owned_hashes(root)
    deposits: list[Deposit] = []
    notes: list[str] = []

    _plan_deposit(
        deposits, index, PLUGIN_SOURCE.read_bytes(), "plugin index.js", owned,
        source=PLUGIN_SOURCE,
    )
    package_text = plugin_package_json()
    _plan_deposit(
        deposits, package, package_text.encode("utf-8"), "plugin package.json", owned,
        text=package_text,
    )

    config = root / PLUGIN_CONFIG
    legacy_config = root / PLUGIN_LEGACY_CONFIG
    if config.is_file():
        notes.append(f"configuration retained: {config}")
    elif legacy_config.is_file():
        notes.append(f"configuration retained: {legacy_config}")
    else:
        config_text = plugin_config_json(port)
        deposits.append(
            Deposit(kind="write", description="plugin configuration", target=config, text=config_text)
        )

    dirs = missing_dirs(root, [deposit.target for deposit in deposits])
    return deposits, dirs, notes


def run_deposit(deposit: Deposit, root: Path, dry_run: bool = False) -> bool:
    """Write one deposit, refusing a target that resolves outside the root."""
    _contained(deposit.target, root)
    if dry_run:
        return True
    deposit.target.parent.mkdir(parents=True, exist_ok=True)
    if deposit.kind == "copy":
        if deposit.source is None:
            raise RuntimeError("copy deposit without a source")
        shutil.copy2(deposit.source, deposit.target)
        return True
    if deposit.kind == "write":
        if deposit.text is None:
            raise RuntimeError("write deposit without content")
        _write_atomic(deposit.target, deposit.text)
        return True
    raise RuntimeError(f"unknown deposit kind {deposit.kind!r}")


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


def write_manifest(
    root: Path,
    actions: list[Action],
    deposits: list[Deposit] | None = None,
    created_dirs: list[Path] | None = None,
) -> None:
    """Record only files this installer CREATED, with their SHA-256.

    A `merge-mcp`/`jsonc-mcp` target is a pre-existing config file that we edited,
    never a file we own: listing it here would make `uninstall` delete the
    harness's whole MCP config (14 servers on a real machine).

    Called without plugin deposits it keeps the historical string-only shape for
    callers that record copies by hand; the installer itself records objects so
    uninstall can prove ownership by hash.
    """
    if deposits is None:
        entries: list[object] = [
            str(a.target.absolute()) for a in actions if a.kind == "copy" and a.target is not None
        ]
        (root / MANIFEST_NAME).write_text(json.dumps({"created": entries}, indent=2) + "\n")
        return

    existing = read_manifest(root)
    entries: list[object] = []
    by_path: dict[Path, int] = {}
    for entry in existing["created"]:
        path = _entry_path(entry, root)
        entries.append(entry)
        if path is not None:
            by_path[_resolved(path)] = len(entries) - 1

    targets = [a.target for a in actions if a.kind == "copy" and a.target is not None]
    targets.extend(deposit.target for deposit in deposits)
    for target in targets:
        if not target.is_file():
            continue
        resolved = _resolved(target)
        record = {"path": str(target.absolute()), "sha256": _sha256_file(target)}
        if resolved in by_path:
            entries[by_path[resolved]] = record
        else:
            by_path[resolved] = len(entries)
            entries.append(record)

    dirs: list[str] = []
    for directory in list(existing["created_dirs"]) + [str(d) for d in (created_dirs or [])]:
        if isinstance(directory, str) and directory not in dirs:
            dirs.append(directory)

    payload = {"created": entries, "created_dirs": dirs}
    _write_atomic(root / MANIFEST_NAME, json.dumps(payload, indent=2) + "\n")


def _legacy_expected_bytes(target: Path) -> bytes | None:
    """The current source for a legacy (hash-less) entry, when the installer has one.

    Legacy manifests stored bare strings. For the files the installer can still
    reproduce byte-for-byte, ownership is provable; for anything else the older
    behaviour (treat as ours) is kept so a pre-hash install still uninstalls.
    """
    if target.name == "index.js" and target.parent.name == "opencode-memory":
        try:
            return PLUGIN_SOURCE.read_bytes()
        except OSError:
            return None
    return None


def uninstall(harness: Harness, root: Path) -> list[str]:
    """Undo the installation: remove the server by key, then files still ours."""
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
        manifest = read_manifest(root)
        root_resolved = _resolved(root)
        retained: list[str] = []

        for entry in manifest["created"]:
            target = _entry_path(entry, root)
            if target is None:
                continue
            resolved = _resolved(target)
            if not resolved.is_relative_to(root_resolved):
                # A tampered or stale manifest must never delete outside the root.
                retained.append(str(target))
                continue
            if not target.is_file():
                continue
            recorded = entry.get("sha256") if isinstance(entry, dict) else None
            if isinstance(recorded, str) and recorded:
                if _sha256_file(target) != recorded:
                    retained.append(str(target))
                    continue
            else:
                expected = _legacy_expected_bytes(resolved)
                if expected is not None and target.read_bytes() != expected:
                    retained.append(str(target))
                    continue
            target.unlink()
            removed.append(str(target))

        for item in retained:
            print(f"  retained: {item}")

        recorded_dirs = [
            directory
            for directory in manifest["created_dirs"]
            if isinstance(directory, str) and directory.strip()
        ]
        for directory in sorted(recorded_dirs, key=lambda d: len(Path(d).parts), reverse=True):
            resolved = _resolved(Path(directory) if Path(directory).is_absolute() else root / directory)
            if resolved == root_resolved or not resolved.is_relative_to(root_resolved):
                continue
            if not resolved.is_dir():
                continue
            try:
                resolved.rmdir()
            except OSError:
                continue
            removed.append(str(resolved))

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
        # A relative --root must not leak into the manifest: the manifest records
        # where files live, not where the operator happened to stand.
        root = root.expanduser()
        if not root.is_absolute():
            root = Path.cwd() / root
        root = _resolved(root)

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

        # The plugin surface is planned separately: it must never appear in the
        # MCP action list, and a foreign file aborts before anything is written.
        deposits: list[Deposit] = []
        created_dirs: list[Path] = []
        notes: list[str] = []
        if harness.name == "opencode":
            try:
                deposits, created_dirs, notes = plan_plugin(root, args.port)
            except (RuntimeError, OSError) as exc:
                print(f"  error: {exc}; nothing was written", file=sys.stderr)
                rc = 1
                continue

        print(f"\n{name} ({root})")
        for note in notes:
            print(f"  {note}")
        if not actions and not deposits:
            print("  nothing to do: already installed")
            continue
        for action in actions:
            print(f"  {action.render()}")
        for deposit in deposits:
            print(f"  {deposit.render()}")

        if args.dry_run:
            continue

        try:
            ok = all(run_action(a, args.port, dry_run=False, root=root) for a in actions)
            if ok:
                ok = all(run_deposit(d, root, dry_run=False) for d in deposits)
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

        write_manifest(root, actions, deposits=deposits, created_dirs=created_dirs)
        print(f"  OK: {len(actions) + len(deposits)} action(s), effect verified")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
