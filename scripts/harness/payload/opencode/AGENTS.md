<!-- mms:start -->
## Memory service (mcp-memory-service)

You have a persistent memory service registered as the `mms` MCP server.

- Before answering questions about prior state, decisions, or "where we left
  off", call `memory_search` first.
- Keep reads cheap: `memory_search(query=..., limit=3, max_response_chars=2000)`.
- Store decisions, measured numbers, procedures, and pitfalls. Do not store
  what is already in the repository or the transcript.
- Prefer specific tags: `decision`, `procedure`, `measured`, `pitfall`,
  `<project>-system`.
- `agent_id` is stamped by the client; do not invent an identity.

Full doctrine: load the `mms-uso` skill.
<!-- mms:end -->
