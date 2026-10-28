# SPEC-F001 — OpenCode harness and MCP registration

| Field | Value |
|-------|-------|
| Status | GREEN — G5 aprovado com ressalvas (não bloqueantes) |
| Impact | High — edits the user's OpenCode configuration file |
| Depends on | — |
| Blocks | F002–F005, F007–F009 |
| Branch | `feat/opencode-installer` |
| Date | 2026-10-23 |

## 1. Context

`scripts/harness/instalar.py` already installs MMS for Hermes and Kiro. OpenCode
is not in the registry, so `--harness auto` never touches it.

OpenCode V2 stores remote servers under `mcp.servers.<name>` and accepts JSONC
(`opencode.jsonc`). The developer's real file also contains comments and other
servers, so a naive `json.load` / `json.dump` would destroy them. There is no
`opencode mcp remove`; removal must be done by the installer.

`opencode mcp add` writes only to the global configuration directory (resolved
from `HOME`/`XDG_CONFIG_HOME`), which cannot target an arbitrary `--root`
sandbox without moving the file, and it cannot undo itself. A bounded JSONC
editor gives one code path for install, verify, and uninstall, and keeps the
isolation guarantee exact.

## 2. Objective

Add `opencode` as a first-class harness in the installer, registering `mms` in
the V2 shape, preserving every byte outside the `mms` entry, and uninstalling by
key only.

## 3. Non-goals

- Migrating an existing legacy `mcp.mms` entry into `mcp.servers.mms`
  automatically (it is detected and honoured, not rewritten).
- Editing `opencode.json` when both `.json` and `.jsonc` exist.
- Writing plugin, `AGENTS.md`, or skill surfaces (F002–F004).

## 4. Requirements

**R1 — Harness detection.**
The installer treats OpenCode as present when its configuration directory exists,
using `$XDG_CONFIG_HOME/opencode` when `XDG_CONFIG_HOME` is set and
`~/.config/opencode` otherwise.

EARS: WHERE `XDG_CONFIG_HOME` is set, THE installer SHALL resolve the OpenCode
root as `$XDG_CONFIG_HOME/opencode`; WHERE it is unset, THE installer SHALL
resolve it as `~/.config/opencode`.

> **Emenda medida (28/out/2026, lab F008).** O OpenCode 2.1.3 resolve seu
> config por `$HOME/.config/opencode` e **não consulta** `XDG_CONFIG_HOME`
> (medido no lab: registro escrito em `$XDG_CONFIG_HOME/opencode` não aparece
> em `opencode mcp list`; o mesmo arquivo em `$HOME/.config/opencode` aparece
> e conecta). O root default do instalador passou a ser sempre
> `~/.config/opencode` — um `--root` explícito continua disponível para
> sandboxes.

**R2 — V2 registration shape.**
On a clean install the installer writes the `mms` server under `mcp.servers`
with `type: "remote"` and the `/mcp` URL of the selected port.

EARS: WHEN `mms` is absent, THE installer SHALL add
`mcp.servers.mms = {"type":"remote","url":"http://127.0.0.1:<port>/mcp"}`.

**R3 — Byte preservation.**
Installing or uninstalling changes only the `mms` member; comments, key order,
indentation, trailing commas, and every other server stay byte-identical.

EARS: WHEN the installer edits a JSONC configuration, THE installer SHALL leave
every byte outside the replaced `mms` member unchanged.

**R4 — Idempotence.**
A second install against a usable `mms` entry plans no action and writes
nothing.

EARS: WHEN the existing `mms` entry points at `:${port}/mcp` and is not
disabled, THE installer SHALL report `nothing to do` and SHALL NOT write the
file.

**R5 — Usability, not mere presence.**
An entry counts as installed only when it is enabled and its URL targets the
selected port.

EARS: IF the existing entry is disabled or targets another port, THEN THE
installer SHALL replace it.

**R6 — Legacy compatibility.**
A legacy `mcp.mms` entry that targets the selected port is honoured as
installed, so the installer does not create a duplicate registration.

EARS: WHEN a matching legacy `mcp.mms` entry exists and `mcp.servers.mms` does
not, THE installer SHALL treat the registration as installed and SHALL NOT add a
V2 duplicate.

**R7 — Surgical uninstall.**
Uninstall removes `mcp.servers.mms` (and a matching legacy `mcp.mms`) and
nothing else; it must work with the service down.

EARS: WHEN `--uninstall` runs, THE installer SHALL remove only the `mms`
registration and SHALL leave the configuration file in place.

**R8 — Refuse ambiguous or invalid input.**
The installer aborts without writing when the configuration is invalid JSONC,
contains duplicate `mms` keys, both `opencode.json` and `opencode.jsonc` exist,
or the JSONC structure is not the expected object shape.

EARS: IF the configuration cannot be parsed or the target file is ambiguous,
THEN THE installer SHALL abort with a non-zero exit code and SHALL NOT modify
any file.

**R9 — Atomic write.**
Configuration writes go through a temporary file in the same directory followed
by `os.replace`, so an interrupted write cannot truncate the user's file.

EARS: WHEN the installer writes the configuration, THE installer SHALL replace
it atomically and SHALL preserve its file mode.

## 5. Technical contract

### 5.1 File resolution

```
root = $XDG_CONFIG_HOME/opencode | ~/.config/opencode
jsonc = root/opencode.jsonc
json  = root/opencode.json
```

- Both present → abort (`ambiguous configuration`).
- Neither present → create `opencode.json` with `$schema` and the entry.
- Otherwise edit the existing file.

### 5.2 New module

`scripts/harness/jsonc.py` (moved to the package in F007):

```python
class JsoncError(ValueError): ...

def load(text: str) -> dict            # comment-tolerant parse for validation
def find_span(text: str, path: list[str]) -> tuple[int, int] | None
def upsert(text: str, path: list[str], value: dict) -> str
def remove(text: str, path: list[str]) -> str
```

- `find_span` raises `JsoncError` when the path occurs more than once.
- `upsert` creates missing intermediate objects and replaces an existing value.
- `remove` leaves the text unchanged when any segment of the path is absent.
- The span scanner understands strings, escapes, `//` and `/* */` comments,
  trailing commas, and nested braces/brackets.
- After every edit, `load()` must succeed and a semantic diff must show exactly
  the intended change; otherwise raise and leave the file untouched.
- Serialization of the inserted member uses two-space indentation relative to
  its container.

### 5.3 Harness descriptor

The `Harness` dataclass gains an ordered candidate list; `mcp_file` stays as the
single-file field used by Hermes/Kiro.

```python
@dataclass(frozen=True)
class Harness:
    ...
    mcp_file: Path | None = None
    mcp_candidates: tuple[Path, ...] = ()
```

```python
"opencode": Harness(
    name="opencode",
    root_default=<config dir>,
    mcp_candidates=(Path("opencode.jsonc"), Path("opencode.json")),
    steering=None,
    skill=None,
)

def resolve_mcp_file(harness: Harness, root: Path) -> Path | None:
    """Existing candidate first; the last candidate when none exists."""
```

Resolution rules:

- zero candidate files exist → return `opencode.json` (creation target);
- exactly one exists → return it;
- both exist → raise `RuntimeError("ambiguous configuration")`;
- `plan_for`, `verify`, `uninstall`, and `main` all use `resolve_mcp_file`,
  never `harness.mcp_file` directly.

### 5.4 Action and entry reader

- The plan emits `Action(kind="jsonc-mcp", target=<resolved file>)`.
- `run_action` for `jsonc-mcp` calls `jsonc.upsert(text, ["mcp","servers","mms"],
  entry)` and writes atomically.
- Test-facing reader:

```python
def opencode_entry(path: Path) -> dict:
    """`mcp.servers.mms`, else legacy `mcp.mms`, else {} (unreadable/invalid)."""
```

- Install treats the registration as present when `entry_is_usable` accepts
  either shape.
- Uninstall removes `mcp.servers.mms` first, then `mcp.mms` when present.
- `main` maps `JsoncError` and ambiguity to exit code `1` with the message on
  stderr and performs no write.

## 6. Edge cases

| Case | Behaviour |
|------|-----------|
| Comment contains the text `"mms"` | Ignored by the string/comment scanner |
| `mms` is the only member | Removal deletes the member and leaves `mcp.servers` as `{}` |
| `mcp.servers` absent | Install creates `mcp.servers`; uninstall is a no-op |
| Legacy `mcp.mms` matches the port | Install is a no-op; uninstall removes the legacy key |
| `mms` appears twice | Abort, no write |
| File is read-only | Abort with the OS error surfaced; no partial write |
| Trailing comma after the removed member | Result stays valid JSONC |
| Windows line endings | Preserved byte-for-byte outside the member |

## 7. Acceptance criteria (measurable)

| AC | Command | Expected |
|----|---------|----------|
| AC1 | `pytest tests/harness/test_jsonc_config.py tests/harness/test_instalar_opencode.py -q` | all pass |
| AC2 | `python scripts/harness/instalar.py --harness opencode --root "$SB/opencode" --port 39123 --skip-health` | exit 0, `mcp.servers.mms` present |
| AC3 | `grep -c 'keep this comment' "$SB/opencode/opencode.jsonc"` | `1` (comment preserved) |
| AC4 | rerun AC2 | prints `nothing to do` and does not change the file hash |
| AC5 | `python scripts/harness/instalar.py --harness opencode --root "$SB/opencode" --uninstall` | exit 0; `mms` gone; other server and comment intact |
| AC6 | corrupt JSONC then install | non-zero exit; file hash unchanged |

## 8. Test plan (RED-on-main)

`tests/harness/test_jsonc_config.py`:

1. Parse and edit a config with `//` and `/* */` comments and trailing commas.
2. `"mms"` inside a comment or string does not create a false span.
3. Insert, replace, and remove preserve all other bytes.
4. Duplicate key and invalid JSONC raise without writing.
5. CRLF round-trip.

`tests/harness/test_instalar_opencode.py`:

1. Detection honours `XDG_CONFIG_HOME`.
2. Clean install writes the V2 shape.
3. Second install is a no-op (file hash equal).
4. Wrong-port and disabled entries are replaced.
5. Legacy `mcp.mms` is honoured and removed on uninstall.
6. Uninstall keeps the other 13 servers and the comment.
7. Both `.json` and `.jsonc` present → abort, no write.
8. Uninstall works with the service down.

RED proof: run these tests against the current `feat/opencode-installer`
(no `opencode` harness, no `jsonc` module) and record the failure count grouped
by cause (`KeyError: 'opencode'`, `ModuleNotFoundError: jsonc`, …).

## 9. Risks and rollback

| Risk | Mitigation |
|------|------------|
| JSONC scanner corrupts a user file | Semantic diff gate + atomic write + chaos tests |
| Existing duplicate registration | Legacy detection prevents a second entry |
| User edits config between plan and apply | Re-read and re-validate immediately before the atomic replace |

Rollback: `--uninstall`; the manifest does not own the configuration file, so
the file is never deleted.

## 10. Out of scope

- `opencode mcp add` integration.
- Project-local `.opencode/opencode.json`.
- OAuth configuration.
