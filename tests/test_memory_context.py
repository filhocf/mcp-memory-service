"""Tests for handle_memory_context in memory.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class FakeRetrieveResult:
    """Mimics the object returned by retrieve_memories with .memories list."""
    def __init__(self, memories=None):
        self.memories = memories or []


@pytest.fixture
def server():
    srv = MagicMock()
    srv.memory_service = MagicMock()
    srv.memory_service.retrieve_memories = AsyncMock()
    return srv


@pytest.mark.asyncio
async def test_returns_all_three_sections(server):
    """Returns formatted text with beliefs, mistakes, and relevant context sections."""
    from mcp_memory_service.server.handlers.memory import handle_memory_context

    server.memory_service.retrieve_memories.side_effect = [
        FakeRetrieveResult([{"content": "Always use type hints"}]),
        FakeRetrieveResult([{"content": "Forgot to validate input twice"}]),
        FakeRetrieveResult([{"content": "Project uses FastAPI + SQLAlchemy"}]),
    ]

    result = await handle_memory_context(server, {"task": "implement endpoint", "budget_tokens": 4000, "agent_id": "kiro"})

    text = result[0].text
    assert "Active Beliefs" in text
    assert "Mistake Notes" in text
    assert "Relevant Context" in text
    assert "Always use type hints" in text
    assert "Forgot to validate input" in text
    assert "FastAPI + SQLAlchemy" in text


@pytest.mark.asyncio
async def test_respects_budget_tokens(server):
    """Truncates output when content exceeds budget_tokens (budget_chars = budget_tokens * 4)."""
    from mcp_memory_service.server.handlers.memory import handle_memory_context

    # Empty beliefs and mistakes, many long memories for the general section
    server.memory_service.retrieve_memories.side_effect = [
        FakeRetrieveResult([]),
        FakeRetrieveResult([]),
        FakeRetrieveResult([{"content": "x" * 300} for _ in range(50)]),
    ]

    budget = 100  # 400 chars budget — very tight
    result = await handle_memory_context(server, {"task": "test", "budget_tokens": budget, "agent_id": "kiro"})

    text = result[0].text
    # The output should respect the budget (header adds some overhead, but content should be limited)
    # At minimum, not all 50 memories should appear
    assert text.count("- xxx") < 50


@pytest.mark.asyncio
async def test_returns_gracefully_no_results(server):
    """Returns graceful message when no memories are found in any section."""
    from mcp_memory_service.server.handlers.memory import handle_memory_context

    server.memory_service.retrieve_memories.side_effect = [
        FakeRetrieveResult([]),
        FakeRetrieveResult([]),
        FakeRetrieveResult([]),
    ]

    result = await handle_memory_context(server, {"task": "unknown topic", "budget_tokens": 4000, "agent_id": "kiro"})

    text = result[0].text
    assert "no relevant context found" in text
    assert "MEMORY CONTEXT" in text


@pytest.mark.asyncio
async def test_handles_exception_in_retrieve(server):
    """Returns error message when retrieve_memories raises an exception."""
    from mcp_memory_service.server.handlers.memory import handle_memory_context

    server.memory_service.retrieve_memories.side_effect = RuntimeError("DB connection lost")

    result = await handle_memory_context(server, {"task": "anything", "budget_tokens": 4000, "agent_id": "kiro"})

    text = result[0].text
    assert "Error" in text
    assert "DB connection lost" in text
