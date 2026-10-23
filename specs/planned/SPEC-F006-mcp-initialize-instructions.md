# SPEC-F006 — `instructions` in the MCP `initialize` response

| Field | Value |
|-------|-------|
| Status | GREEN, G5 (approved with reservations) |
| Impact | Medium — protocol payload consumed by every MCP client |
| Depends on | — (server-side, independent of the installer) |
| Blocks | — |
| Branch | `feat/opencode-installer` |
| Date | 2026-10-23 |

## 1. Context

The MCP specification allows the server to return `instructions` from
`initialize` — a short, human-readable usage note that the client may surface to
the model. OpenCode and other clients use it to shape how tools are called
without requiring an `AGENTS.md` file.

`src/mcp_memory_service/web/api/mcp.py` currently returns only
`protocolVersion`, `capabilities`, and `serverInfo`. A client that connects
without any harness-specific instructions gets the tools but not the doctrine:
search before answering state questions, keep reads cheap, do not invent
`agent_id`.

The managed `AGENTS.md` block (F003) covers OpenCode, but every other MCP client
passes through the same `initialize` handshake.

## 2. Objective

Return a short, stable `instructions` string from the HTTP MCP `initialize`
response, with an environment switch to suppress it.

## 3. Non-goals

- Changing the stdio MCP server's initialize handling (SDK-owned).
- Returning the full usage skill body (too large for a handshake).
- Client-specific instructions.

## 4. Requirements

**R1 — Field present.**
The HTTP `initialize` result includes a non-empty `instructions` string.

EARS: WHEN an HTTP client sends `initialize`, THE server SHALL include
`result.instructions`.

**R2 — Doctrine content.**
The text states: search before state questions, the cheap-read limits, what to
store, and that `agent_id` is transport-supplied.

EARS: THE `instructions` value SHALL mention `memory_search`, `limit`,
`max_response_chars`, storage guidance, and `agent_id`.

**R3 — Size budget.**
The value is at most 1200 characters so it does not bloat every session.

EARS: THE `instructions` value SHALL NOT exceed 1200 characters.

**R4 — Suppression switch.**
`MCP_DISABLE_INSTRUCTIONS=1` (or `true`) omits the field entirely.

EARS: WHERE `MCP_DISABLE_INSTRUCTIONS` is set to `1` or `true`, THE server SHALL
omit `result.instructions`.

**R5 — Stability.**
The string is a module constant, not generated per request; two calls return
byte-identical text.

EARS: THE server SHALL return the same `instructions` text on every request
within a process.

**R6 — Protocol shape preserved.**
Adding the field does not change `protocolVersion`, `capabilities`, or
`serverInfo`.

EARS: WHEN `instructions` is added, THE server SHALL keep the existing
`initialize` fields unchanged.

## 5. Technical contract

### 5.1 Module

`src/mcp_memory_service/web/api/mcp_instructions.py`:

```python
MCP_INSTRUCTIONS = (
    "This server is persistent long-term memory. "
    "Before answering questions about prior state, decisions, or where work "
    "left off, call memory_search first. "
    "Keep reads cheap: memory_search(query=..., limit<=3, "
    "max_response_chars<=2000). "
    "Store decisions, measured numbers, procedures, and pitfalls; do not store "
    "what is already in the repository or the conversation. "
    "agent_id is supplied by the transport (X-Agent-ID); do not invent one."
)

def instructions_enabled() -> bool:
    return os.environ.get("MCP_DISABLE_INSTRUCTIONS", "").strip().lower() not in {"1", "true"}
```

### 5.2 Endpoint change

```python
result = {
    "protocolVersion": "2024-11-05",
    "capabilities": {"tools": {}},
    "serverInfo": {...},
}
if instructions_enabled():
    result["instructions"] = MCP_INSTRUCTIONS
```

## 6. Edge cases

| Case | Behaviour |
|------|-----------|
| `MCP_DISABLE_INSTRUCTIONS=TRUE` | Omitted (case-insensitive) |
| `MCP_DISABLE_INSTRUCTIONS=0` | Included |
| Client ignores the field | No behaviour change |
| Non-ASCII in future edits | Allowed; the budget counts characters |

## 7. Acceptance criteria (measurable)

| AC | Command | Expected |
|----|---------|----------|
| AC1 | `pytest tests/web/test_mcp_initialize_instructions.py -q` | all pass |
| AC2 | POST `initialize` to the lab server | `result.instructions` length `> 0` and `<= 1200` |
| AC3 | same call twice | identical strings |
| AC4 | `MCP_DISABLE_INSTRUCTIONS=1` server | key absent |
| AC5 | shape assertion | `protocolVersion`, `capabilities`, `serverInfo` unchanged |

## 8. Test plan (RED-on-main)

1. Route-level test with the existing `TestClient` fixture pattern: assert the
   key exists and content constraints hold.
2. Suppression test with `monkeypatch.setenv`.
3. Shape regression test (deep-equal minus `instructions`).
4. Budget test (`len <= 1200`).

RED proof: current response has no `instructions` key, so assertions fail with
`KeyError: 'instructions'`; the shape test passes on both sides and is marked as
a regression guard, not as RED evidence.

## 9. Risks and rollback

| Risk | Mitigation |
|------|------------|
| Instructions conflict with a harness's own guidance | Text is additive and short; `MCP_DISABLE_INSTRUCTIONS` opts out |
| Token overhead per session | Hard 1200-character budget |

Rollback: set `MCP_DISABLE_INSTRUCTIONS=1` without a release; remove the field
in the next release.

## 10. Out of scope

- Stdio transport.
- Dynamic/user-specific instructions.
- Surfacing instructions in the dashboard.
