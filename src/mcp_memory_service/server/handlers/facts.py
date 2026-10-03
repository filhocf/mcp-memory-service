"""Handler for memory_facts tool (RFC-MM-02).

Provides manual trigger and status for the fact extraction pipeline.
"""

import json
import logging

from mcp import types

logger = logging.getLogger(__name__)


async def handle_memory_facts(server, arguments: dict) -> list[types.TextContent]:
    """Handle memory_facts tool calls.

    Actions:
        run: Trigger fact extraction now (up to 200 chunks).
        status: Show pending count, last run, facts total.
    """
    action = arguments.get("action", "status")

    storage = await server._ensure_storage_initialized()

    if action == "status":
        return await _handle_status(storage)
    elif action == "run":
        return await _handle_run(storage, arguments)
    else:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Unknown action: {action}. Use 'run' or 'status'."})
        )]


async def _handle_status(storage) -> list[types.TextContent]:
    """Get extraction pipeline status."""
    from mcp_memory_service.extraction.facts import get_extraction_status

    conn = storage.conn
    status = get_extraction_status(conn)
    return [types.TextContent(type="text", text=json.dumps(status, indent=2))]


async def _handle_run(storage, arguments: dict) -> list[types.TextContent]:
    """Trigger extraction run."""
    from mcp_memory_service.extraction.facts import get_llm_config, run_extraction

    config = get_llm_config()
    if not config:
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "error": "LLM not configured. Set MCP_NLI_LLM_BASE_URL and MCP_NLI_LLM_MODEL."
            })
        )]

    limit = int(arguments.get("limit", 200))
    conn = storage.conn
    result = await run_extraction(conn, limit=limit)
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
