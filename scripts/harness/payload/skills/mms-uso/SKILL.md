---
name: mms-uso
description: "Operating the mcp-memory-service (mms) as long-term project memory: when to search before answering about prior decisions, project state, or where we left off, how to keep reads cheap, what to store, and the measured pitfalls."
---

# mms-uso — operating the memory service

The `mms` MCP server registered by the installer is the long-term memory for this
machine and its projects. This is the doctrine for using it: search cheaply, store
deliberately, and never answer a state question from guesswork.

## Before acting

| Situation | Action |
|---|---|
| "how are we doing", "what did we decide", "where did we leave off" | `memory_search` first — do **not** answer from memory |
| about to repeat an investigation | search first; if it was measured, cite the number instead of redoing it |
| about to propose a procedure (deploy, publish, migration) | search the `procedure` tag |
| a conceptual question, or code already on screen | **do not** consult the service |

Rule of thumb: a question about **state** goes to the memory service; a question
about a **concept** goes to your own knowledge.

## How to search

```
memory_search(query="<distinctive token>", limit=3, max_response_chars=2000)
```

- `limit` ≤ 3: five results rarely change a decision and cost far more.
- Search by the most distinctive, short token (acronym, product name, hash). A full
  sentence rarely exists verbatim.
- `mode="exact"` requires a **contiguous** substring — two words separated by
  anything return nothing even when the memory is stored.
- If the reply says `Showing 0 of N results`, retry **without** `max_response_chars`.
- Absence in search is **not** absence in the database. Confirm with a read-only SQL
  query before claiming a memory does not exist.

## Store and tag

`store` is a locked partition, not a shared folder: a search **without** a `store`
returns only `default`. The inventory is **per host** and changes — measure it before
citing it.

For project-specific memory, prefer `default` plus a tag (`<project>-system`) and let
the transport stamp the author. `store: null` is **rejected** by the schema — omit the
field instead of sending null.

## What to store

Store what **saves tokens later**:

- a decision with its reason, dated;
- a measurement with the number and the method (not "it improved", but
  "+10pp, 95% CI [0.05, 0.1583]");
- a procedure that worked, with the exact commands;
- a pitfall: the error, the cause, and the fix.

Do not store: what is already in the repository or a commit, what is in the session
transcript, or an opinion without a measurement.

Useful tags: `procedure`, `measured`, `<project>-system`, `pitfall`, `decision`.

## Pitfalls (measured 2026-10-20)

- **`memory_context` is not a project-state tool.** It ranks by semantic belief
  neighbourhood: asking for one project returned another project's memories at the
  top. Use a tag query instead.
- **`memory_context` returns every item twice** (`items` and `beliefs`) and carries
  ~9 KB of fixed metadata that `budget_tokens` does not count.
- **`memory_list` costs ~4,875 tokens per call** — inventory belongs in SQL.
- **`memory_store` is cheap** (~98 tokens). Writing is not the problem; reading is.
- **`memory_health`/`memory_stats` titles mislead** when tombstones exist: count the
  live rows in SQL.

## Authorship

The `agent_id` comes from the client transport, which stamps it on every call; it is
never invented in the tool call. If a stored memory appears without an author, the
defect is in the transport, not in the tool.
