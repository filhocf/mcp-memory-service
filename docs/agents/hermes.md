# Hermes Integration Guide

Connect [Hermes Agent](https://hermes-agent.nousresearch.com) to mcp-memory-service as its
memory backend, with one command.

## Install

```bash
python scripts/harness/instalar.py --harness hermes --port 8000
```

The installer:

1. aborts **before writing** if `/health` does not answer on the given port;
2. detects what is already in place (`hermes mcp list`, health) and plans only the gap;
3. registers the server with `hermes mcp add mms --url http://localhost:<port>/mcp`;
4. deposits the usage skill into `<hermes-home>/skills/mms-uso/` and the authoring hook into
   `<hermes-home>/agent-hooks/`;
5. verifies the effect — it refuses to report success unless `hermes mcp list` shows the server on
   the installed port.

Re-running is a no-op. `--uninstall` removes the server and only the files it created;
`--dry-run` prints the plan; `--root` installs into a sandbox instead of `~/.hermes`.

## Two channels, two roles

| channel | content | when |
|---|---|---|
| `MEMORY.md` / `USER.md` | identity, durable preferences, short rules — injected every turn | always present; **not** a source of state |
| this server | dated decisions, measurements, procedures — semantic search on demand | questions about state, pending work, "what did we do" |

A rule that prevents the classic mistake: **a question about state goes to the MCP first.**
`MEMORY.md` answers "who is the user and what are the rules", not "where did we stop".

## CLI behaviours that shape the installer

Measured on Hermes 0.22.x (Linux, Oct 2026):

1. **`hermes mcp add` is interactive.** It asks which tools to enable; with no stdin answered it
   prints `Cancelled.` and **exits 0**. Trusting the exit code reports success while registering
   nothing — hence the post-write effect check.
2. **`hermes config get` does not exist** (`show/edit/set/path/env-path/check/migrate` only).
3. **`hermes config unset` does not exist** — the reverse of `config set X true` is `config set X false`.
4. **`hermes hooks add` does not exist** (`list/test/remove/doctor`), and
   `hermes config set hooks.pre_tool_call[0].command …` writes the literal key `pre_tool_call[0]`
   instead of a list — registering hooks needs a config merge.

## Verify

```bash
mms-doctor --db-path <path-to-sqlite> --repo-path <repo>
```

Six checks with evidence: health (restarting only a `failed`/`inactive` unit, never one still
`activating`), declared vs. listening port, installed vs. `pyproject` version, sync cursor age,
author stamping, and live-vs-tombstone embedding coverage.
