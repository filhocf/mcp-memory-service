"""Tests for BeliefService._group_observations"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass, field
from typing import Optional

from mcp_memory_service.consolidation.belief_service import BeliefService


@dataclass
class FakeMemory:
    content: str
    content_hash: str
    memory_type: str = "observation"
    created_at: Optional[float] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class FakeSearchResult:
    memory: FakeMemory
    relevance_score: float


@pytest.fixture
def service():
    storage = MagicMock()
    storage.search = AsyncMock(return_value=[])
    return BeliefService(storage)


@pytest.mark.asyncio
async def test_empty_input_returns_empty_groups(service):
    result = await service._group_observations([])
    assert result == {}


@pytest.mark.asyncio
async def test_single_observation_returns_one_group(service):
    obs = FakeMemory(content="the sky is blue", content_hash="abc123")
    service.storage.search.return_value = []

    result = await service._group_observations([obs])

    assert len(result) == 1
    assert result["the sky is blue"] == [obs]


@pytest.mark.asyncio
async def test_similar_observations_grouped_together(service):
    obs1 = FakeMemory(content="the sky is blue", content_hash="hash1")
    obs2 = FakeMemory(content="the sky appears blue", content_hash="hash2")

    # When searching for obs1's content, return obs2 with high similarity
    async def mock_search(query, n_results=50):
        if query == "the sky is blue":
            return [FakeSearchResult(memory=obs2, relevance_score=0.92)]
        return []

    service.storage.search = mock_search

    result = await service._group_observations([obs1, obs2])

    assert len(result) == 1
    group = list(result.values())[0]
    assert len(group) == 2
    assert obs1 in group
    assert obs2 in group


@pytest.mark.asyncio
async def test_dissimilar_observations_in_separate_groups(service):
    obs1 = FakeMemory(content="the sky is blue", content_hash="hash1")
    obs2 = FakeMemory(content="python uses indentation", content_hash="hash2")

    # Return obs2 with low similarity for obs1's search
    async def mock_search(query, n_results=50):
        if query == "the sky is blue":
            return [FakeSearchResult(memory=obs2, relevance_score=0.40)]
        if query == "python uses indentation":
            return [FakeSearchResult(memory=obs1, relevance_score=0.40)]
        return []

    service.storage.search = mock_search

    result = await service._group_observations([obs1, obs2])

    assert len(result) == 2
    assert result["the sky is blue"] == [obs1]
    assert result["python uses indentation"] == [obs2]


@pytest.mark.asyncio
async def test_already_assigned_observations_not_regrouped(service):
    obs1 = FakeMemory(content="the sky is blue", content_hash="hash1")
    obs2 = FakeMemory(content="the sky looks blue today", content_hash="hash2")
    obs3 = FakeMemory(content="blue sky above", content_hash="hash3")

    # obs1 search returns both obs2 and obs3 as similar
    # obs2 should be assigned to obs1's group and NOT start its own
    async def mock_search(query, n_results=50):
        if query == "the sky is blue":
            return [
                FakeSearchResult(memory=obs2, relevance_score=0.90),
                FakeSearchResult(memory=obs3, relevance_score=0.88),
            ]
        # obs2 and obs3 won't get searched because they're already assigned
        return []

    service.storage.search = mock_search

    result = await service._group_observations([obs1, obs2, obs3])

    # All 3 should be in one group (obs1's), no separate groups for obs2/obs3
    assert len(result) == 1
    group = result["the sky is blue"]
    assert len(group) == 3


@pytest.mark.asyncio
async def test_empty_content_observation_skipped(service):
    """HIGH: observation with empty content should be silently skipped."""
    obs_empty = FakeMemory(content="", content_hash="empty1")
    obs_valid = FakeMemory(content="valid observation", content_hash="valid1")
    service.storage.search.return_value = []

    result = await service._group_observations([obs_empty, obs_valid])

    assert len(result) == 1
    assert "valid observation" in result
    assert "" not in result


@pytest.mark.asyncio
async def test_search_exception_creates_isolated_group(service):
    """HIGH: if storage.search raises, observation gets its own group."""
    obs = FakeMemory(content="some observation", content_hash="hash1")

    async def mock_search_raises(query, n_results=50):
        raise ConnectionError("storage unavailable")

    service.storage.search = mock_search_raises

    result = await service._group_observations([obs])

    assert len(result) == 1
    assert result["some observation"] == [obs]


@pytest.mark.asyncio
async def test_non_observation_results_filtered_out(service):
    """MEDIUM: search results with memory_type != 'observation' excluded from cluster."""
    obs1 = FakeMemory(content="the sky is blue", content_hash="hash1")
    obs2 = FakeMemory(content="the sky is azure", content_hash="hash2")
    belief = FakeMemory(content="sky is always blue", content_hash="belief1", memory_type="belief")

    async def mock_search(query, n_results=50):
        if query == "the sky is blue":
            return [
                FakeSearchResult(memory=belief, relevance_score=0.95),  # filtered out
                FakeSearchResult(memory=obs2, relevance_score=0.90),    # included
            ]
        return []

    service.storage.search = mock_search

    result = await service._group_observations([obs1, obs2])

    assert len(result) == 1
    group = result["the sky is blue"]
    assert obs1 in group
    assert obs2 in group
    # belief should NOT be in any group
    for g in result.values():
        assert belief not in g
