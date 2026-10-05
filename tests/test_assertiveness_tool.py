"""RED tests for exposing get_assertiveness_metrics as a real MCP tool (Peça 3).

The assertiveness aggregator
(src/mcp_memory_service/storage/usage_telemetry.py::get_assertiveness_metrics)
computes re_query_rate / injection_coverage / lost_context_* but has ZERO
production callers — it is not reachable through the MCP surface.

These tests pin the wiring that must exist:
  1. registry.py (TOOL_REGISTRY) advertises a read-only tool named
     "get_assertiveness_metrics" (snake_case, consistent with the existing
     get_bootstrap_profile / get_onboarding_guide / get_quarantined_memories
     naming convention in the registry).
  2. routing.py (ROUTING_TABLE) routes it, and the server dispatches
     handle_call_tool("get_assertiveness_metrics", ...) returning the 3 metrics
     as JSON TextContent.

Molded on tests/test_memory_context_tool.py and tests/test_tool_registry.py.
Nothing here touches src/. RED on main: the tool is absent from the registry
and the routing table, so these assertions fail (missing tool / error payload).
"""

import json

import pytest

from mcp_memory_service.server import MemoryServer

TOOL_NAME = "get_assertiveness_metrics"


class TestAssertivenessToolRegistry:
    """Peça 3a: the tool is advertised in the registry/routing (static checks)."""

    def test_tool_in_registry(self):
        """get_assertiveness_metrics must be present in TOOL_REGISTRY.

        RED: tool absent from the registry today.
        """
        from mcp_memory_service.tools.registry import TOOL_REGISTRY
        names = [t.name for t in TOOL_REGISTRY]
        assert TOOL_NAME in names, f"{TOOL_NAME} missing from TOOL_REGISTRY"

    def test_tool_is_read_only(self):
        """A pure aggregator must declare readOnlyHint=True (OAuth scope,
        GHSA-2r68) — same contract the other get_* tools follow.

        RED: tool absent => StopIteration/next() fails to find it.
        """
        from mcp_memory_service.tools.registry import TOOL_REGISTRY
        tool = next(t for t in TOOL_REGISTRY if t.name == TOOL_NAME)
        assert tool.annotations.get("readOnlyHint") is True

    def test_tool_in_routing_table(self):
        """ROUTING_TABLE must route the tool so call_tool can dispatch it.

        RED: routing entry absent today.
        """
        from mcp_memory_service.tools.routing import ROUTING_TABLE
        assert TOOL_NAME in ROUTING_TABLE, (
            f"{TOOL_NAME} missing from ROUTING_TABLE"
        )


class TestAssertivenessTool:
    """Peça 3b: the tool is listed and dispatched end-to-end on the server."""

    @pytest.mark.asyncio
    async def test_tool_listed(self):
        """The tool must appear in the server's advertised tool list.

        RED: not registered => not listed.
        """
        server = MemoryServer()
        tools = await server.handle_list_tools()
        tool_names = [t.name for t in tools]
        assert TOOL_NAME in tool_names

    @pytest.mark.asyncio
    async def test_handler_routes_and_returns_metrics(self):
        """handle_call_tool must dispatch the tool and return the 3 assertiveness
        sub-metrics as JSON TextContent (empty dataset => all zeros, no error).

        RED: tool not routed => call_tool returns an {"error": "Unknown tool..."}
        payload (or raises), so the metric keys are absent.
        """
        server = MemoryServer()
        result = await server.handle_call_tool(TOOL_NAME, {})
        assert isinstance(result, list)
        assert len(result) > 0
        payload = json.loads(result[0].text)
        assert "error" not in payload, (
            f"tool dispatch returned an error payload: {payload}"
        )
        # get_assertiveness_metrics contract fields
        assert "re_query_rate" in payload
        assert "injection_coverage" in payload
        assert "lost_context_rate" in payload
