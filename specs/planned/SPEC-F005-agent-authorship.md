# SPEC-F005 — `X-Agent-ID` authorship (MCP and plugin REST)

| Field | Value |
|-------|-------|
| Status | GREEN, G5 |
| Impact | High — writes authorship tags on stored memories |
| Depends on | F001, F002 |
| Blocks | F008 |
| Branch | `feat/opencode-installer` |
| Date | 2026-10-23 |

## 1. Context

The server already supports authorship: `web/api/mcp.py` copies the
`X-Agent-ID` request header into `arguments["agent_id"]` when the tool call does
not set one, and REST store requests append `agent:<id>` to the tags.

OpenCode reaches MMS through two paths:

1. the MCP server registered by the installer (tools such as `memory_store`);
2. the plugin, which calls the REST API directly for auto-capture and session
   summaries.

Today neither path sends `X-Agent-ID`: the installer writes only the URL, and
`buildHeaders()` in `memory-plugin.js` sends only `X-API-Key`. Memories captured
from OpenCode therefore have no author, which breaks the "agent_id comes from
the harness" rule in the usage skill.

## 2. Objective

Stamp every OpenCode-originated write with a stable agent identity, overridable
per installation, without asking the model to supply one.

## 3. Non-goals

- Changing the server's precedence rules.
- Deriving identity from the OS user or project path automatically.
- Per-session unique IDs (those already exist as session tags).

## 4. Requirements

**R1 — Installer default.**
The installer writes a default agent ID of `opencode` when the operator does not
provide one.

EARS: WHEN `--agent-id` is omitted, THE installer SHALL use `opencode`.

**R2 — Installer override.**
`--agent-id <id>` sets the identity used for both surfaces of that installation.

EARS: WHEN `--agent-id research-box` is passed, THE installer SHALL write
`research-box` as the MCP header value and as the plugin `agentId`.

In an existing installation the installer merges only
`memoryService.agentId` into the active plugin configuration (new file name
first, then the legacy `memory-awareness.json`), preserving every other key.
Without an explicit flag, an existing configuration is never rewritten.

**R3 — MCP header.**
The registration carries `X-Agent-ID: <id>` as a header on the remote server.

EARS: WHEN OpenCode opens the `mms` MCP connection, THE server SHALL receive
`X-Agent-ID: <id>` on `tools/call` requests.

**R4 — Plugin REST header.**
The plugin sends `X-Agent-ID` on every REST request it makes, including memory
search, store, delete, harvest, and health.

EARS: WHEN the plugin calls any `/api/...` endpoint, THE request SHALL include
`X-Agent-ID: <id>`.

**R5 — Plugin configuration precedence.**
The plugin resolves the identity from `OPENCODE_MEMORY_AGENT_ID`, then
`memoryService.agentId` in the config file, then the literal `opencode`.

EARS: WHEN both the environment variable and the config key are set, THE plugin
SHALL use the environment variable.

**R6 — No identity invention.**
Neither the managed instructions nor the skill tell the model to pass
`agent_id`; the transport supplies it.

EARS: THE managed instructions and the usage skill SHALL NOT instruct a model to
choose an `agent_id` value.

**R7 — Backward compatibility.**
An existing configuration without `agentId` keeps working and falls back to
`opencode`.

EARS: WHEN `memoryService.agentId` is absent, THE plugin SHALL use `opencode`.

**R8 — Header hygiene.**
The identity is trimmed and rejected when it contains control characters or is
longer than 64 characters; the plugin then falls back to `opencode` and logs one
warning.

EARS: IF the configured identity is invalid, THEN THE plugin SHALL fall back to
`opencode` and SHALL log a single warning.

## 5. Technical contract

### 5.1 Installer

`--agent-id` is added to the installer CLI and threaded into:

- MCP registration: header `X-Agent-ID: <id>`; an existing registration keeps
  its other headers (for example `Authorization`) and unrelated keys;
- plugin config bootstrap: `memoryService.agentId = <id>`.

`MMS_AGENT_ID` is read as the default when `--agent-id` is absent; the literal
`opencode` is the final fallback. An existing plugin configuration is updated
only for an explicit, valid `--agent-id`; an invalid value falls back with a
warning and never rewrites the file.

### 5.2 Plugin

```js
function resolveAgentId(config) {
  const raw = process.env.OPENCODE_MEMORY_AGENT_ID
    || config.memoryService.agentId
    || "opencode"
  return validAgentId(raw) ? raw.trim() : "opencode"
}

function buildHeaders(config) {
  const headers = {
    Accept: "application/json",
    "X-Agent-ID": config.memoryService.agentId,
  }
  if (config.memoryService.apiKey) headers["X-API-Key"] = config.memoryService.apiKey
  return headers
}
```

`agentId` is resolved once at config load and stored in
`config.memoryService.agentId`, so `buildHeaders` stays pure.

For tests, the plugin exposes `resolveAgentId`, `buildHeaders`, `requestJson`,
and `loadConfig` under `_internal`. Invalid identities are validated after
trimming: control characters or more than 64 characters fall back to
`opencode`, and repeated resolution of the same invalid value warns once.

### 5.3 Server

No change. The existing `X-Agent-ID` → `arguments.agent_id` injection and REST
tagging are reused.

## 6. Edge cases

| Case | Behaviour |
|------|-----------|
| `--agent-id` with spaces around it | Trimmed |
| `--agent-id ""` | Falls back to `opencode` |
| 65-character ID | Rejected, fallback, warning |
| ID with `\n` | Rejected, fallback, warning |
| Explicit `agent_id` in a tool call | Server keeps the explicit value (existing precedence) |
| Legacy config file | Falls back to `opencode` |

## 7. Acceptance criteria (measurable)

| AC | Command | Expected |
|----|---------|----------|
| AC1 | `python3 -m pytest tests/harness/test_agent_id.py -q` and `node --test opencode/tests/agent-id.test.js` | all pass |
| AC2 | install with `--agent-id research-box`; read config | MCP header and `memoryService.agentId` both `research-box` |
| AC3 | MCP `initialize` + `tools/call memory_store` against the lab | `memory_search` filtered by `agent_id: research-box` returns the record |
| AC4 | plugin store request against a fake HTTP server | header `X-Agent-ID` present on every request |
| AC5 | no flag, no env | `opencode` on both surfaces |

## 8. Test plan (RED-on-main)

1. Installer unit tests for default, flag, env, and invalid values.
2. Plugin test with a local `http.createServer` capturing headers for search,
   store, delete, and health.
3. Config precedence tests (env > file > default).
4. Lab test: MCP `memory_store` then `memory_search` by tag
   `agent:<id>` returns the record (server-level integration).
5. Regression: explicit `agent_id` in the tool call still wins.

RED proof: current `buildHeaders()` has no `X-Agent-ID`, so the fake-server test
fails with `received headers: {accept, x-api-key}`. The installer test fails
because `--agent-id` is unknown.

## 9. Risks and rollback

| Risk | Mitigation |
|------|------------|
| Wrong identity pollutes tags | Explicit flag/config; documented override |
| Header leaks into logs | It is an identity, not a secret; never include API keys in logs |
| Duplicate `agent:` tags | Server deduplicates tags; verify in AC3 |

Rollback: install again with `--agent-id` or remove the header/config key.

## 10. Out of scope

- Server-side identity derivation.
- Hermes hook changes (already stamps identity).
- Per-project identity switching.
