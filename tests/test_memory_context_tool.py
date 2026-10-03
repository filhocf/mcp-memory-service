"""
Tests for exposing memory_context as a real MCP tool (closes gap D3).

The memory_context feature (src/mcp_memory_service/storage/context_injection.py)
previously had no MCP endpoint. These tests verify the tool is (1) registered in
the server's tool list and (2) routed by the call handler, returning the
injected context as JSON.

Molded on tests/test_bootstrap_profile.py::test_get_bootstrap_profile_tool_registered.
"""

import json

import pytest

from mcp_memory_service.server import MemoryServer


class TestMemoryContextTool:
    """D3: memory_context exposed as MCP tool."""

    @pytest.mark.asyncio
    async def test_memory_context_tool_registered(self):
        """The tool must be listed in available tools."""
        server = MemoryServer()
        tools = await server.handle_list_tools()
        tool_names = [t.name for t in tools]
        assert "memory_context" in tool_names

    @pytest.mark.asyncio
    async def test_memory_context_tool_input_schema(self):
        """Input schema must require 'task' and allow budget_tokens/limit."""
        server = MemoryServer()
        tools = await server.handle_list_tools()
        tool = next(t for t in tools if t.name == "memory_context")
        schema = tool.inputSchema
        assert "task" in schema["properties"]
        assert schema["required"] == ["task"]
        assert "budget_tokens" in schema["properties"]
        assert "limit" in schema["properties"]

    @pytest.mark.asyncio
    async def test_memory_context_handler_routes_and_returns(self):
        """The handler must route to context_injection.memory_context and
        return the context dict as JSON TextContent."""
        server = MemoryServer()
        result = await server.handle_call_tool("memory_context", {
            "task": "deploy without running tests",
        })
        assert isinstance(result, list)
        assert len(result) > 0
        payload = json.loads(result[0].text)
        # memory_context contract fields
        assert "items" in payload
        assert "beliefs" in payload
        assert "count" in payload
        assert "budget_tokens" in payload
        assert "injected" in payload
