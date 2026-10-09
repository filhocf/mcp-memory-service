"""Tests for server-side context injection in memory_search."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp import types
from mcp_memory_service.server.handlers.memory import handle_memory_search


@pytest.fixture
def mock_server():
    """Create a mock server with storage."""
    server = MagicMock()
    server._ensure_storage_initialized = AsyncMock()
    return server


@pytest.fixture
def mock_storage(mock_server):
    """Create mock storage with configurable search results."""
    storage = AsyncMock()
    mock_server._ensure_storage_initialized.return_value = storage
    return storage


@pytest.mark.asyncio
async def test_context_injection_flag_on_with_beliefs(mock_server, mock_storage, monkeypatch):
    """Flag ON + busca com beliefs relevantes → resposta CONTÉM o bloco 'Related distilled context'."""
    # Set flag ON
    monkeypatch.setenv("MCP_SEARCH_INJECT_CONTEXT", "true")
    
    # Mock successful memory search
    mock_storage.search_memories.return_value = {
        "memories": [
            {"content": "test memory", "content_hash": "hash1", "similarity_score": 0.9}
        ],
        "total": 1,
        "query": "test query",
        "mode": "semantic",
    }
    
    # Mock memory_context to return beliefs with count > 0
    mock_context_result = {
        "items": [
            {"content": "relevant belief", "confidence": 0.8, "relevance": 0.9, "belief_hash": "belief1"}
        ],
        "beliefs": [
            {"content": "relevant belief", "confidence": 0.8, "relevance": 0.9, "belief_hash": "belief1"}
        ],
        "count": 1,
        "injected": True,
        "belief_hashes": ["belief1"],
        "budget_tokens": 500,
        "truncated": False
    }
    
    with patch("mcp_memory_service.storage.context_injection.memory_context", return_value=mock_context_result):
        result = await handle_memory_search(mock_server, {"query": "test query"})
    
    # Should contain the context injection block
    response_text = result[0].text
    assert "---" in response_text
    assert "Related distilled context:" in response_text
    assert "relevant belief" in response_text


@pytest.mark.asyncio 
async def test_context_injection_flag_off_default(mock_server, mock_storage, monkeypatch):
    """Flag OFF (default/unset) → resposta NÃO contém o bloco (regressão nula)."""
    # Do not set the flag (default OFF)
    monkeypatch.delenv("MCP_SEARCH_INJECT_CONTEXT", raising=False)
    
    # Mock successful memory search
    mock_storage.search_memories.return_value = {
        "memories": [
            {"content": "test memory", "content_hash": "hash1", "similarity_score": 0.9}
        ],
        "total": 1,
        "query": "test query",
        "mode": "semantic",
    }
    
    # Mock memory_context (should not be called when flag is OFF)
    with patch("mcp_memory_service.storage.context_injection.memory_context") as mock_context:
        result = await handle_memory_search(mock_server, {"query": "test query"})
        
        # memory_context should not be called when flag is off
        mock_context.assert_not_called()
    
    # Should NOT contain the context injection block
    response_text = result[0].text
    assert "Related distilled context:" not in response_text


@pytest.mark.asyncio
async def test_context_injection_no_beliefs_found(mock_server, mock_storage, monkeypatch):
    """memory_context count==0 → nenhum bloco anexado mesmo com flag ON."""
    # Set flag ON
    monkeypatch.setenv("MCP_SEARCH_INJECT_CONTEXT", "true")
    
    # Mock successful memory search
    mock_storage.search_memories.return_value = {
        "memories": [
            {"content": "test memory", "content_hash": "hash1", "similarity_score": 0.9}
        ],
        "total": 1,
        "query": "test query", 
        "mode": "semantic",
    }
    
    # Mock memory_context to return empty beliefs (count = 0)
    mock_context_result = {
        "items": [],
        "beliefs": [],
        "count": 0,
        "injected": True,
        "belief_hashes": [],
        "budget_tokens": 500,
        "truncated": False
    }
    
    with patch("mcp_memory_service.storage.context_injection.memory_context", return_value=mock_context_result):
        result = await handle_memory_search(mock_server, {"query": "test query"})
    
    # Should NOT contain the context injection block when count=0
    response_text = result[0].text
    assert "Related distilled context:" not in response_text


@pytest.mark.asyncio
async def test_context_injection_error_non_fatal(mock_server, mock_storage, monkeypatch):
    """memory_context raise → busca retorna normal (não propaga exceção)."""
    # Set flag ON
    monkeypatch.setenv("MCP_SEARCH_INJECT_CONTEXT", "true")
    
    # Mock successful memory search
    mock_storage.search_memories.return_value = {
        "memories": [
            {"content": "test memory", "content_hash": "hash1", "similarity_score": 0.9}
        ],
        "total": 1,
        "query": "test query",
        "mode": "semantic",
    }
    
    # Mock memory_context to raise an exception
    with patch("mcp_memory_service.storage.context_injection.memory_context", side_effect=Exception("Context injection failed")):
        result = await handle_memory_search(mock_server, {"query": "test query"})
    
    # Search should succeed despite context injection failure
    
    
@pytest.mark.asyncio
async def test_flag_off_preserves_truncated_format_legacy_behavior(mock_server, mock_storage, monkeypatch):
    """Flag OFF + max_response_chars pequeno + 3 mems → resposta deve conter 'Showing 1 of' (fit-at-least-one preservado), NÃO 'Showing 0 of'."""
    # Ensure flag is OFF (default behavior)
    monkeypatch.delenv("MCP_SEARCH_INJECT_CONTEXT", raising=False)
    
    # Mock search with 3 memories and a smaller limit to force format_bounded_response to show 0 results
    mock_storage.search_memories.return_value = {
        "memories": [
            {"content": "Memory content 1 - " + "x" * 400, "content_hash": "hash1", "similarity_score": 0.9, "created_at": "2024-01-01T00:00:00Z", "tags": []},
            {"content": "Memory content 2 - " + "x" * 400, "content_hash": "hash2", "similarity_score": 0.8, "created_at": "2024-01-02T00:00:00Z", "tags": []},
            {"content": "Memory content 3 - " + "x" * 400, "content_hash": "hash3", "similarity_score": 0.7, "created_at": "2024-01-03T00:00:00Z", "tags": []}
        ],
        "total": 3,
        "query": "test query",
        "mode": "semantic",
    }
    
    # Use very small max_response_chars to trigger the regression where format_bounded_response
    # would return 0 results instead of the legacy truncate_memories fit-at-least-one behavior
    result = await handle_memory_search(mock_server, {"query": "test query", "max_response_chars": 200})
    
    response_text = result[0].text
    
    # With the current bug (format_bounded_response used unconditionally),
    # this would show "Showing 0 of 3" instead of the legacy "Showing 1 of 3"
    print(f"Response length: {len(response_text)}")
    print(f"Response text: {response_text}")
    
    # This test will initially FAIL because the bug is present
    # After the fix, it should show fit-at-least-one behavior: "Showing 1 of 3"
    assert "Showing 1 of 3" in response_text, f"Expected 'Showing 1 of 3' (legacy fit-at-least-one) but got: {response_text}"
    assert "Showing 0 of 3" not in response_text, f"Regression detected: 'Showing 0 of 3' found in: {response_text}"


@pytest.mark.asyncio
async def test_flag_on_uses_bounded_response_budget_control(mock_server, mock_storage, monkeypatch):
    """Flag ON + max_response_chars pequeno + 3 mems → usa format_bounded_response (budget strict), pode mostrar 'Showing 0 of'."""
    # Set flag ON
    monkeypatch.setenv("MCP_SEARCH_INJECT_CONTEXT", "true")
    
    # Mock search with 3 memories and small limit
    mock_storage.search_memories.return_value = {
        "memories": [
            {"content": "Memory content 1 - " + "x" * 400, "content_hash": "hash1", "similarity_score": 0.9, "created_at": "2024-01-01T00:00:00Z", "tags": []},
            {"content": "Memory content 2 - " + "x" * 400, "content_hash": "hash2", "similarity_score": 0.8, "created_at": "2024-01-02T00:00:00Z", "tags": []},
            {"content": "Memory content 3 - " + "x" * 400, "content_hash": "hash3", "similarity_score": 0.7, "created_at": "2024-01-03T00:00:00Z", "tags": []}
        ],
        "total": 3,
        "query": "test query",
        "mode": "semantic",
    }
    
    # Mock empty context injection (no beliefs found)
    mock_context_result = {
        "items": [],
        "beliefs": [],
        "count": 0,
        "injected": True,
        "belief_hashes": [],
        "budget_tokens": 500,
        "truncated": False
    }
    
    with patch("mcp_memory_service.storage.context_injection.memory_context", return_value=mock_context_result):
        result = await handle_memory_search(mock_server, {"query": "test query", "max_response_chars": 200})
    
    response_text = result[0].text
    
    # With flag ON, format_bounded_response respects the budget strictly
    # Should respect the 200 char limit, may show "0 of 3" if nothing fits in budget
    assert len(response_text) <= 200, f"Response exceeds budget: {len(response_text)} > 200 chars"
    # This is the budget-respecting behavior - different from legacy fit-at-least-one


@pytest.mark.asyncio
async def test_context_injection_summarize_path_missing(mock_server, mock_storage, monkeypatch):
    """P1 #1: summarize=True + flag on → payload tem related_context (prova P1#1, red-on-main)."""
    # Set flag ON  
    monkeypatch.setenv("MCP_SEARCH_INJECT_CONTEXT", "true")
    
    # Mock successful memory search
    mock_storage.search_memories.return_value = {
        "memories": [
            {"content": "test memory", "content_hash": "hash1", "similarity_score": 0.9}
        ],
        "total": 1,
        "query": "test query",
        "mode": "semantic",
    }
    
    # Mock memory_context to return beliefs
    mock_context_result = {
        "items": [
            {"content": "relevant belief", "confidence": 0.8, "relevance": 0.9, "belief_hash": "belief1"}
        ],
        "count": 1,
        "injected": True,
        "belief_hashes": ["belief1"],
        "budget_tokens": 500,
        "truncated": False
    }
    
    # Mock the summarizer to return a summary
    mock_summary = MagicMock()
    mock_summary.text = "This is a summary"
    mock_summary.source_hashes = ["hash1"]
    mock_summary.snapshot = "snapshot"
    mock_summary.summarized_count = 1
    mock_summary.omitted_count = 0
    mock_summary.provider = "test"
    mock_summary.model = "test-model"
    
    with patch("mcp_memory_service.storage.context_injection.memory_context", return_value=mock_context_result):
        with patch("mcp_memory_service.services.search_summarizer.MemorySearchSummarizer") as mock_summarizer_class:
            mock_summarizer = AsyncMock()
            mock_summarizer.summarize.return_value = mock_summary
            mock_summarizer_class.return_value = mock_summarizer
            
            result = await handle_memory_search(mock_server, {"query": "test query", "summarize": True})
    
    # Should be JSON response with related_context field
    import json
    response_text = result[0].text
    payload = json.loads(response_text)
    
    # The payload should contain related_context field when injection is enabled
    assert "related_context" in payload, "Summary response missing related_context field with injection enabled"


@pytest.mark.asyncio  
async def test_context_injection_truncation_budget_overflow(mock_server, mock_storage, monkeypatch):
    """P1 #2: teste com max_response_chars PEQUENO + flag on → len(resposta) <= limite (prova P1#2, red-on-main)."""
    # Set flag ON
    monkeypatch.setenv("MCP_SEARCH_INJECT_CONTEXT", "true")
    
    # Mock successful memory search with large content
    large_content = "X" * 500  # Large content to trigger truncation
    mock_storage.search_memories.return_value = {
        "memories": [
            {"content": large_content, "content_hash": "hash1", "similarity_score": 0.9, "created_at": "2024-01-01T10:00:00Z", "tags": []}
        ],
        "total": 1,
        "query": "test query",
        "mode": "semantic",
    }
    
    # Mock memory_context to return large context that would blow the budget
    large_context = "Y" * 300
    mock_context_result = {
        "items": [
            {"content": large_context, "confidence": 0.8, "relevance": 0.9, "belief_hash": "belief1"}
        ],
        "count": 1,
        "injected": True,
        "belief_hashes": ["belief1"], 
        "budget_tokens": 500,
        "truncated": False
    }
    
    with patch("mcp_memory_service.storage.context_injection.memory_context", return_value=mock_context_result):
        # Use a very small max_response_chars limit
        result = await handle_memory_search(mock_server, {
            "query": "test query", 
            "max_response_chars": 200
        })
    
    # The response should respect the character limit including footer
    response_text = result[0].text
    assert len(response_text) <= 200, f"Response length {len(response_text)} exceeds limit 200"


@pytest.mark.asyncio
async def test_context_injection_empty_query_no_injection(mock_server, mock_storage, monkeypatch):
    """P2 #2: query vazia → injeção traz beliefs top-N sem relação temática. Early-return '' se query vazia/whitespace."""
    # Set flag ON
    monkeypatch.setenv("MCP_SEARCH_INJECT_CONTEXT", "true")
    
    # Mock successful memory search with empty/whitespace query (tag search)
    mock_storage.search_memories.return_value = {
        "memories": [
            {"content": "test memory", "content_hash": "hash1", "similarity_score": 0.9}
        ],
        "total": 1,
        "query": "",  # Empty query
        "mode": "semantic",
    }
    
    # Mock memory_context (should not be called for empty query)
    with patch("mcp_memory_service.storage.context_injection.memory_context") as mock_context:
        result = await handle_memory_search(mock_server, {
            "tags": ["testtag"],  # Tag search without textual query
            "query": ""           # Explicit empty query
        })
        
        # memory_context should not be called when query is empty
        mock_context.assert_not_called()
    
    # Should NOT contain the context injection block for empty query
    response_text = result[0].text
    assert "Related distilled context:" not in response_text


@pytest.mark.asyncio
async def test_context_injection_format_empty_path(mock_server, mock_storage, monkeypatch):
    """P2 #1: Ensure _format_empty path with injection ON exercises context injection."""
    # Set flag ON
    monkeypatch.setenv("MCP_SEARCH_INJECT_CONTEXT", "true")
    
    # Mock empty search result to trigger _format_empty path
    mock_storage.search_memories.return_value = {
        "memories": [],  # Empty result
        "total": 0,
        "query": "test query",
        "mode": "semantic",
    }
    
    # Mock memory_context to return beliefs
    mock_context_result = {
        "items": [
            {"content": "relevant belief", "confidence": 0.8, "relevance": 0.9, "belief_hash": "belief1"}
        ],
        "count": 1,
        "injected": True,
        "belief_hashes": ["belief1"],
        "budget_tokens": 500,
        "truncated": False
    }
    
    with patch("mcp_memory_service.storage.context_injection.memory_context", return_value=mock_context_result):
        result = await handle_memory_search(mock_server, {"query": "test query"})
    
    # Should contain the context injection block even with empty results
    response_text = result[0].text
    assert "No memories found" in response_text
    assert "Related distilled context:" in response_text
    assert "relevant belief" in response_text


@pytest.mark.asyncio
async def test_context_injection_format_truncated_path_exercise(mock_server, mock_storage, monkeypatch):
    """P2 #1: Ensure _format_truncated path with injection ON exercises context injection with bounded response."""
    # Set flag ON
    monkeypatch.setenv("MCP_SEARCH_INJECT_CONTEXT", "true")
    
    # Mock search result that will trigger truncation
    large_content = "X" * 100
    mock_storage.search_memories.return_value = {
        "memories": [
            {"content": large_content, "content_hash": "hash1", "similarity_score": 0.9, "created_at": "2024-01-01T10:00:00Z", "tags": []}
        ],
        "total": 1,
        "query": "test query",
        "mode": "semantic",
    }
    
    # Mock memory_context to return context
    mock_context_result = {
        "items": [
            {"content": "relevant context", "confidence": 0.8, "relevance": 0.9, "belief_hash": "belief1"}
        ],
        "count": 1,
        "injected": True,
        "belief_hashes": ["belief1"],
        "budget_tokens": 500,
        "truncated": False
    }
    
    with patch("mcp_memory_service.storage.context_injection.memory_context", return_value=mock_context_result):
        # Use moderate max_response_chars to trigger truncation path but still fit content
        result = await handle_memory_search(mock_server, {
            "query": "test query",
            "max_response_chars": 800
        })
    
    # Should contain context injection in truncated response
    response_text = result[0].text
    assert "Related distilled context:" in response_text
    assert "relevant context" in response_text
    # Should be bounded by max_response_chars
    assert len(response_text) <= 800