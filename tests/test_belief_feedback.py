"""Tests for belief feedback feature — down-rated observations affecting confidence.

Feature: L4 learning-loop with negative feedback. Observations with user_rating=-1
should penalize belief confidence when MCP_BELIEF_USE_FEEDBACK=1.

All tests FAIL by design — the feature doesn't exist yet.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from mcp_memory_service.consolidation.belief import derive_confidence
from mcp_memory_service.consolidation.belief_service import BeliefService


# Reuse fixtures from test_belief_store.py
@pytest.fixture
def belief_db():
    """Create an in-memory DB with beliefs table for service tests."""
    import sqlite3
    from pathlib import Path
    
    conn = sqlite3.connect(":memory:")
    migration_path = Path(__file__).parent.parent / "src" / "mcp_memory_service" / "storage" / "migrations" / "012_add_belief_store.sql"
    conn.executescript(migration_path.read_text())
    return conn


@pytest.fixture
def mock_storage(belief_db):
    """Create a mock storage with a real beliefs table."""
    storage = MagicMock()
    storage.conn = belief_db
    storage.graph = None
    storage.get_all_memories = AsyncMock(return_value=[])
    storage.get_memory_by_hash = AsyncMock(return_value=None)
    return storage


def test_down_rated_observation_counted_as_contradiction(monkeypatch):
    """R1: Observation with metadata user_rating=-1 + flag ON → becomes contradiction."""
    # Enable feedback feature
    monkeypatch.setenv("MCP_BELIEF_USE_FEEDBACK", "1")
    
    now = datetime.now(timezone.utc)
    
    # Supporting observation
    supporting_obs = {
        "created_at_iso": now.isoformat(),
        "metadata": {"observation_type": "user_correction"},
    }
    
    # Down-rated observation (should become contradiction when feedback enabled)
    down_rated_obs = {
        "created_at_iso": now.isoformat(),
        "metadata": {
            "observation_type": "user_correction",
            "user_rating": -1  # This should make it a contradiction
        },
    }
    
    # With feedback enabled, down-rated should be moved to contradicting
    confidence = derive_confidence_with_feedback(
        supporting=[supporting_obs], 
        contradicting=[],  # Empty — down-rated should be auto-moved here
        observations_with_feedback=[down_rated_obs],
        current_time=now
    )
    
    # Should be lower than without the down-rated observation
    baseline_confidence = derive_confidence([supporting_obs], [], current_time=now)
    assert confidence < baseline_confidence, "Down-rated observation should penalize confidence"


def test_negative_feedback_never_increases_confidence(monkeypatch):
    """R2: conf_com_downrate <= conf_sem_downrate, strict < when ≥1 down-rated."""
    monkeypatch.setenv("MCP_BELIEF_USE_FEEDBACK", "1")
    
    now = datetime.now(timezone.utc)
    
    supporting_obs = {
        "created_at_iso": now.isoformat(),
        "metadata": {"observation_type": "automated"},
    }
    
    down_rated_obs = {
        "created_at_iso": now.isoformat(),
        "metadata": {
            "observation_type": "automated",
            "user_rating": -1
        },
    }
    
    # Baseline without down-rated observation
    conf_baseline = derive_confidence([supporting_obs], [], current_time=now)
    
    # With down-rated observation and feedback enabled
    conf_with_downrate = derive_confidence_with_feedback(
        supporting=[supporting_obs],
        contradicting=[],
        observations_with_feedback=[down_rated_obs],
        current_time=now
    )
    
    # Must be strictly less when there's down-rated feedback
    assert conf_with_downrate < conf_baseline, "Negative feedback must decrease confidence"
    assert conf_with_downrate <= conf_baseline, "Negative feedback never increases confidence"


def test_feedback_disabled_matches_baseline(monkeypatch):
    """R3: Flag OFF → confidence identical to baseline even with user_rating=-1."""
    monkeypatch.setenv("MCP_BELIEF_USE_FEEDBACK", "0")  # Explicitly disabled
    
    now = datetime.now(timezone.utc)
    
    supporting_obs = {
        "created_at_iso": now.isoformat(),
        "metadata": {"observation_type": "user_correction"},
    }
    
    down_rated_obs = {
        "created_at_iso": now.isoformat(),
        "metadata": {
            "observation_type": "user_correction",
            "user_rating": -1  # Should be ignored when disabled
        },
    }
    
    # Baseline calculation
    baseline_confidence = derive_confidence([supporting_obs], [], current_time=now)
    
    # With feedback disabled, should ignore user_rating
    disabled_confidence = derive_confidence_with_feedback(
        supporting=[supporting_obs],
        contradicting=[],
        observations_with_feedback=[down_rated_obs],
        current_time=now
    )
    
    # Should be almost equal (within floating point precision)
    assert abs(disabled_confidence - baseline_confidence) < 1e-10, "Disabled feedback should match baseline"


def test_feedback_opt_in_defaults_off(monkeypatch):
    """R4: Without env var → behavior == baseline (flag resolves False)."""
    # Ensure no env var is set
    monkeypatch.delenv("MCP_BELIEF_USE_FEEDBACK", raising=False)
    
    now = datetime.now(timezone.utc)
    
    supporting_obs = {
        "created_at_iso": now.isoformat(),
        "metadata": {"observation_type": "automated"},
    }
    
    down_rated_obs = {
        "created_at_iso": now.isoformat(),
        "metadata": {
            "observation_type": "automated", 
            "user_rating": -1
        },
    }
    
    # Check that feedback feature defaults to OFF
    feedback_enabled = get_feedback_flag_value()
    assert feedback_enabled is False, "Feedback should default to OFF"
    
    # Should behave identical to baseline
    baseline = derive_confidence([supporting_obs], [], current_time=now)
    default_behavior = derive_confidence_with_feedback(
        supporting=[supporting_obs],
        contradicting=[],
        observations_with_feedback=[down_rated_obs],
        current_time=now
    )
    
    assert default_behavior == baseline, "Default behavior should match baseline"


def test_neutral_and_positive_ratings_remain_supporting(monkeypatch):
    """R5: Rating 0/1/None → support unchanged, confidence == baseline."""
    monkeypatch.setenv("MCP_BELIEF_USE_FEEDBACK", "1")
    
    now = datetime.now(timezone.utc)
    
    # Observations with neutral/positive ratings
    neutral_obs = {
        "created_at_iso": now.isoformat(),
        "metadata": {
            "observation_type": "user_correction",
            "user_rating": 0  # Neutral
        },
    }
    
    positive_obs = {
        "created_at_iso": now.isoformat(),
        "metadata": {
            "observation_type": "user_correction", 
            "user_rating": 1  # Positive
        },
    }
    
    no_rating_obs = {
        "created_at_iso": now.isoformat(),
        "metadata": {
            "observation_type": "user_correction"
            # No user_rating field (None)
        },
    }
    
    # These should all behave as normal supporting observations
    baseline = derive_confidence([neutral_obs, positive_obs, no_rating_obs], [], current_time=now)
    
    with_feedback = derive_confidence_with_feedback(
        supporting=[neutral_obs, positive_obs, no_rating_obs],
        contradicting=[],
        observations_with_feedback=[],
        current_time=now
    )
    
    assert abs(with_feedback - baseline) < 1e-10, "Neutral/positive ratings should not change behavior"


@pytest.mark.asyncio
async def test_down_rated_removed_from_supporting_monotonicidade(monkeypatch):
    """Test específico P2: observation down-rated é REMOVIDA de supporting ao ser movida para contradicting."""
    monkeypatch.setenv("MCP_BELIEF_USE_FEEDBACK", "1")
    
    now = datetime.now(timezone.utc)
    
    # Observation que inicialmente está em supporting mas será down-rated
    obs_to_downrate = {
        "content_hash": "hash_123",
        "created_at_iso": now.isoformat(),
        "metadata": {
            "observation_type": "user_correction",
            "user_rating": -1  # Down-rated
        },
    }
    
    # Baseline: sem a obs down-rated em supporting
    baseline_confidence = derive_confidence([], [], current_time=now)
    
    # Com feedback: obs está em supporting MAS é down-rated → deve ser MOVIDA para contradicting
    confidence_with_move = derive_confidence_with_feedback(
        supporting=[obs_to_downrate],  # Inicialmente em supporting
        contradicting=[],
        observations_with_feedback=[obs_to_downrate],  # Será processada como down-rated
        current_time=now
    )
    
    # Deve ser MENOR que baseline (obs contradicting penalty > obs supporting benefit)
    assert confidence_with_move < baseline_confidence, "Down-rated observation moved from supporting should decrease confidence vs baseline"
    
    # Também teste: confidence com obs em supporting vs mesma obs down-rated
    confidence_as_supporting = derive_confidence([obs_to_downrate], [], current_time=now)
    assert confidence_with_move < confidence_as_supporting, "Moving from supporting to contradicting must decrease confidence"


@pytest.mark.asyncio
async def test_derive_stats_report_down_rated_count(mock_storage, monkeypatch):
    """R6: Stats/return contains down_rated_count == N expected."""
    monkeypatch.setenv("MCP_BELIEF_USE_FEEDBACK", "1")
    
    now = datetime.now(timezone.utc)
    
    # Create observations with mixed ratings
    obs_list = []
    
    # 2 down-rated observations
    for i in range(2):
        obs = MagicMock()
        obs.content = f"Down-rated observation {i}"
        obs.content_hash = f"hash_down_{i}"
        obs.created_at = now.timestamp()
        obs.metadata = {
            "observation_type": "user_correction",
            "user_rating": -1
        }
        obs_list.append(obs)
    
    # 1 normal observation
    obs = MagicMock()
    obs.content = "Normal observation"
    obs.content_hash = "hash_normal"
    obs.created_at = now.timestamp()
    obs.metadata = {"observation_type": "user_correction"}
    obs_list.append(obs)
    
    mock_storage.get_all_memories = AsyncMock(return_value=obs_list)
    
    svc = BeliefService(mock_storage)
    stats = await svc.derive_beliefs()
    
    # Stats should report how many observations were down-rated
    assert "down_rated_count" in stats, "Stats should include down_rated_count field"
    assert stats["down_rated_count"] == 2, "Should report exactly 2 down-rated observations"


# Helper functions that should exist in the implementation (but don't yet)

def derive_confidence_with_feedback(supporting, contradicting, observations_with_feedback, current_time):
    """Target function signature that should handle feedback-aware confidence derivation."""
    # This function doesn't exist yet — should cause AttributeError/ImportError
    from mcp_memory_service.consolidation.belief import derive_confidence_with_feedback as target_func
    return target_func(
        supporting=supporting,
        contradicting=contradicting, 
        observations_with_feedback=observations_with_feedback,
        current_time=current_time
    )


def get_feedback_flag_value():
    """Target function to check if feedback feature is enabled."""
    # This function doesn't exist yet — should cause ImportError
    from mcp_memory_service.consolidation.belief import get_feedback_flag_value as target_func
    return target_func()