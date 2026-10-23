# SPEC-F007 — `memory install opencode` CLI entry point

| Field | Value |
|-------|-------|
| Status | planned |
| Impact | High — moves installer code into the shipped package |
| Depends on | F001, F002, F003, F004 |
| Blocks | F009 |
| Branch | `feat/opencode-installer` |
| Date | 2026-10-23 |

## 1. Context

Today the installer is `scripts/harness/instalar.py` in the source tree. Users
who install MMS from PyPI do not have the repository checkout, so "one command"
means cloning the repo. `codebase-memory-mcp` exposes `codebase-memory-mcp
install`; MMS should expose the equivalent through its existing `memory` CLI.

The `memory` CLI is a Click group in `src/mcp_memory_service/cli/main.py`. The
payload (skills, steering, hooks, `AGENTS.md`) currently lives under
`scripts/harness/payload/`, outside the package.

## 2. Objective

Ship the installer inside the wheel and expose `memory install opencode`
(plus `memory install list`) with the same plan/apply/verify/uninstall
semantics already proven by the script.

## 3. Non-goals

- Changing the behaviour defined in F001–F005.
- Auto-detecting and installing every harness from the CLI (explicit subcommand
  first; `--harness auto` remains available in the script).
- A package index for third-party harnesses.

## 4. Requirements

**R1 — Package location.**
Installer logic lives in `src/mcp_memory_service/installers/` and the payload
lives inside the package.

EARS: WHEN the wheel is built, THE wheel SHALL contain the installer modules
and the payload files.

**R2 — Script compatibility.**
`scripts/harness/instalar.py` remains executable and delegates to the package,
so existing tests and muscle memory keep working.

EARS: WHEN `python scripts/harness/instalar.py --list` runs, THE script SHALL
delegate to the packaged installer and SHALL exit 0.

**R3 — OpenCode subcommand.**
`memory install opencode` installs all OpenCode surfaces, with `--dry-run`,
`--uninstall`, `--port`, `--agent-id`, `--root`, and `--skip-health`.

EARS: WHEN `memory install opencode --dry-run` runs, THE command SHALL print the
plan and SHALL NOT write any file.

**R4 — List subcommand.**
`memory install list` prints supported harnesses, their default roots, and the
surfaces each deposits.

EARS: WHEN `memory install list` runs, THE command SHALL list each harness and
its surfaces.

**R5 — Exit codes.**
`0` on success or nothing-to-do, `1` on a failed action/verification, `2` on a
usage error (Click default).

EARS: IF any action or verification fails, THEN THE command SHALL exit 1.

**R6 — Same semantics.**
The CLI uses the same plan/verify/manifest code path as the script; it is a thin
adapter, not a second implementation.

EARS: THE CLI SHALL call the packaged installer functions directly and SHALL NOT
duplicate planning or uninstall logic.

**R7 — Offline.**
Install, verify, and uninstall perform no network access besides the local
health check, which `--skip-health` disables.

EARS: WHEN `--skip-health` is set, THE command SHALL make no network request.

**R8 — No new runtime dependency.**
The installer uses only the standard library and Click (already a dependency).

EARS: THE installer package SHALL import only the standard library and Click.

## 5. Technical contract

### 5.1 Layout

```
src/mcp_memory_service/installers/
├── __init__.py
├── jsonc.py          # F001
├── core.py           # Harness, Action, plan_for, run_action, verify, manifest
├── harnesses.py      # registry: hermes, kiro, opencode
└── payload/
    ├── skills/mms-uso/SKILL.md
    ├── steering/mms.md
    ├── agent-hooks/mms_agent_stamp.py
    └── opencode/AGENTS.md
```

`scripts/harness/instalar.py`:

```python
from mcp_memory_service.installers.core import main
if __name__ == "__main__":
    raise SystemExit(main())
```

The script adds the repo `src/` to `sys.path` only when the package is not
installed, to keep the checkout workflow working.

### 5.2 CLI wiring

```python
@main.group("install")
def install_group(): ...

@install_group.command("opencode")
@click.option("--root")
@click.option("--port", type=int, default=8000)
@click.option("--agent-id", default=None)
@click.option("--dry-run", is_flag=True)
@click.option("--uninstall", is_flag=True)
@click.option("--skip-health", is_flag=True)
def install_opencode(...): ...
```

### 5.3 Packaging

`pyproject.toml` includes the payload via `[tool.hatch.build.targets.wheel]`
`packages` plus `artifacts`/`include`, or `[tool.hatch.build] include`. The exact
hatch syntax is chosen during implementation and verified by inspecting the
built wheel.

## 6. Edge cases

| Case | Behaviour |
|------|-----------|
| `memory install opencode` without the OpenCode dir | Creates the config directory (install intent is explicit) |
| Unknown harness | Click usage error, exit 2 |
| `--uninstall` with the service down | Works |
| Wheel installed without payload | ImportError at install time is a build failure caught by AC4 |
| Running from an editable install | Payload resolves via `importlib.resources` |

## 7. Acceptance criteria (measurable)

| AC | Command | Expected |
|----|---------|----------|
| AC1 | `pytest tests/harness -q` | all pass, including the 13 existing tests |
| AC2 | `memory install opencode --root "$SB/opencode" --dry-run` | plan printed, no files created |
| AC3 | `memory install opencode --root "$SB/opencode" --skip-health` | exit 0, surfaces present |
| AC4 | `uv build --wheel` then `unzip -l dist/*.whl \| grep installers/payload` | payload present |
| AC5 | `memory install list` | lists `hermes`, `kiro`, `opencode` |
| AC6 | `memory install opencode --uninstall` | exit 0, surfaces removed |

## 8. Test plan (RED-on-main)

1. CLI runner tests (`click.testing.CliRunner`) for dry-run, install, uninstall,
   list, and exit codes.
2. Import-path tests from the packaged layout.
3. Wheel-content test (marked `slow`, skipped when `uv` is absent).
4. Differential test: script and CLI produce the same plan for the same root.

RED proof: `memory install` does not exist on the current branch, so CliRunner
exits 2 with "No such command"; the script wrapper import fails because the
package module is absent.

## 9. Risks and rollback

| Risk | Mitigation |
|------|------------|
| Moving code breaks the 13 existing tests | Wrapper keeps the old import path; differential tests |
| Payload missing from the wheel | Wheel-content AC |
| CLI grows into a second implementation | R6 + review |

Rollback: the script remains the source of truth until the move is verified;
revert the packaging commit if the wheel check fails.

## 10. Out of scope

- `memory uninstall` for other harnesses.
- Auto-install on `pip install`.
- Shell completions.
