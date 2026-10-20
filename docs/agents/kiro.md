# Kiro Integration Guide

Connect [Kiro](https://kiro.dev) (CLI and IDE share the global `mcp.json`) to mcp-memory-service.

## Install

```bash
python scripts/harness/instalar.py --harness kiro --port 8000
```

Surfaces the installer writes, relative to the Kiro root (`~/.kiro`):

| surface | path |
|---|---|
| MCP registration | `settings/mcp.json` → `mcpServers.mms` |
| steering (read every prompt) | `steering/mms.md` |
| usage skill | `skills/mms-uso/SKILL.md` |

The MCP entry is **merged**, never replacing the file: your other servers stay untouched.
`autoApprove` intentionally lists only the cheap tools — `memory_store`, `memory_search`,
`memory_update`, `memory_delete` and the mistake-note pair. Inventory tools (`memory_list`,
`memory_stats`) and LLM-backed tools (`memory_context`, `memory_consolidate`, `memory_harvest`)
require confirmation because they return whole records and dominate the context window.

The IDE reads the same global `mcp.json` (agents inherit it via `includeMcpJson: true`), so one
deposit serves CLI and IDE. Kiro Crew is out of scope.

## Verify

```bash
mms-doctor --db-path <path-to-sqlite> --repo-path <repo>
```

Same six checks as the Hermes guide; the doctor is harness-agnostic.

## Why the payload has a steering file

Kiro reads `steering/*.md` on every prompt. That is the right place to state the cost rule — search
with `limit=3` and `max_response_chars`, do not call `memory_context` for named project state — because
it applies before the agent chooses a tool, not after it has already spent the context.
