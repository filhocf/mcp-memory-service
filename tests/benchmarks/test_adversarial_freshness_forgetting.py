"""
TDD RED tests for adversarial eval (frente E): freshness + forgetting measurement.

SPEC: docs/rfc/planned/spec-learning-loop-e-eval-mrr.md
OBJECTIVE: offline deterministic eval that emits 3 commit-comparable numbers:
  (1) MRR (reusing LoCoMo harness)
  (2) taxa_freshness (fraction of v1/v2 pairs where v2-newer ranks above v1-older)  
  (3) taxa_forgetting (fraction of injected-unused beliefs whose confidence dropped/left top-k)

CONTRACT: reg will implement run_adversarial_eval(storage) -> {mrr, taxa_freshness, taxa_forgetting}
in scripts/benchmarks/ that constructs synthetic sets and measures frente C + B.

ALL TESTS ARE RED: run_adversarial_eval() does not exist yet.
"""

import asyncio
import json
import os
import sys
import tempfile
import shutil
from datetime import datetime, timedelta
from typing import Dict, Any
import pytest

# Path setup for benchmark imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "benchmarks"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

try:
    import sqlite_vec  # noqa: F401
    SQLITE_VEC_AVAILABLE = True
except ImportError:
    SQLITE_VEC_AVAILABLE = False

pytestmark = pytest.mark.skipif(not SQLITE_VEC_AVAILABLE, reason="sqlite-vec not available")

if SQLITE_VEC_AVAILABLE:
    from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage
    from benchmark_locomo import create_isolated_storage


# CONTRACT: The reg will implement this function in scripts/benchmarks/adversarial_eval.py
# Here we try to import it to show RED behavior when it doesn't exist
try:
    from adversarial_eval import run_adversarial_eval
except ImportError:
    # RED: The module doesn't exist yet - this is expected RED behavior
    def run_adversarial_eval(storage) -> Dict[str, float]:
        """
        CONTRACT for reg to implement in scripts/benchmarks/adversarial_eval.py:
        
        Runs offline adversarial eval measuring frente C (freshness) and B (forgetting).
        
        Args:
            storage: Initialized memory storage with synthetic data
            
        Returns:
            Dict with keys:
                - mrr: MRR score (reusing LoCoMo subset if viable, else synthetic)
                - taxa_freshness: fraction [0,1] of v1/v2 pairs where v2 ranks above v1
                - taxa_forgetting: fraction [0,1] of injected-unused beliefs with confidence drop
        """
        raise ImportError("adversarial_eval module not implemented by reg yet")


@pytest.fixture
async def isolated_storage():
    """Isolated storage for eval tests."""
    storage, tmp_dir = create_isolated_storage()
    await storage.initialize()
    yield storage
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
async def storage_with_synthetic_versioned_pairs(isolated_storage):
    """Storage with synthetic v1/v2 pairs for freshness measurement."""
    storage = isolated_storage
    
    # Use fixed seed date for determinism
    FIXED_SEED_DATE = datetime(2026, 10, 1, 12, 0, 0)
    old_timestamp = (FIXED_SEED_DATE - timedelta(days=2)).isoformat()
    new_timestamp = (FIXED_SEED_DATE - timedelta(hours=1)).isoformat()
    
    # Import belief service for direct belief insertion
    from mcp_memory_service.consolidation.belief_service import BeliefService
    
    # Insert versioned pairs into beliefs table
    conn = storage.conn
    
    pairs = [
        {
            "v1_hash": "fact1_v1",
            "v2_hash": "fact1_v2", 
            "content": "Redis supports atomic operations for concurrent access",
            "confidence": 0.8
        },
        {
            "v1_hash": "fact2_v1",
            "v2_hash": "fact2_v2",
            "content": "Docker containers share the host kernel for efficiency", 
            "confidence": 0.85
        },
        {
            "v1_hash": "fact3_v1", 
            "v2_hash": "fact3_v2",
            "content": "PostgreSQL VACUUM reclaims storage from deleted tuples",
            "confidence": 0.9
        }
    ]
    
    for pair in pairs:
        # Insert v1 (older)
        conn.execute("""
            INSERT INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            pair["v1_hash"],
            pair["content"], 
            pair["confidence"],
            "active",
            old_timestamp,
            old_timestamp,
            json.dumps([f"{pair['v1_hash']}_mem"])
        ))
        
        # Insert v2 (newer - same content/confidence, only timestamp differs)
        conn.execute("""
            INSERT INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            pair["v2_hash"],
            pair["content"],
            pair["confidence"], 
            "active",
            new_timestamp,
            new_timestamp,
            json.dumps([f"{pair['v2_hash']}_mem"])
        ))
    
    conn.commit()
    return storage


@pytest.fixture
async def storage_with_synthetic_unused_beliefs(isolated_storage):
    """Storage with synthetic beliefs for forgetting measurement."""
    storage = isolated_storage
    
    # Use fixed seed date for determinism
    FIXED_SEED_DATE = datetime(2026, 10, 1, 12, 0, 0)
    timestamp = FIXED_SEED_DATE.isoformat()
    
    conn = storage.conn
    
    unused_beliefs = [
        {
            "hash": "unused_belief_1",
            "content": "Kafka partitions enable parallel message processing",
            "confidence": 0.75
        },
        {
            "hash": "unused_belief_2", 
            "content": "Elasticsearch sharding distributes data across nodes",
            "confidence": 0.8
        },
        {
            "hash": "unused_belief_3",
            "content": "RabbitMQ exchanges route messages to queues",
            "confidence": 0.7
        }
    ]
    
    for belief in unused_beliefs:
        conn.execute("""
            INSERT INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            belief["hash"],
            belief["content"],
            belief["confidence"],
            "active", 
            timestamp,
            timestamp,
            json.dumps([f"{belief['hash']}_mem"])
        ))
    
    conn.commit()
    return storage


class TestAdversarialEvalContract:
    """GREEN tests proving the eval contract that reg implemented."""
    
    @pytest.mark.asyncio
    async def test_eval_function_exists_and_returns_expected_structure(self, isolated_storage):
        """GREEN: adversarial_eval module exists and returns proper structure."""
        
        # GREEN: Function should exist and return dict with required keys
        result = await run_adversarial_eval(isolated_storage)
        
        assert isinstance(result, dict), "Should return dict"
        assert "mrr" in result, "Should include MRR metric"
        assert "taxa_freshness" in result, "Should include freshness rate"
        assert "taxa_forgetting" in result, "Should include forgetting rate"
            
    @pytest.mark.asyncio
    async def test_eval_function_can_be_called_directly(self, isolated_storage):
        """GREEN: Direct call works and returns valid metrics."""
        
        # GREEN: Should successfully call and return results
        result = await run_adversarial_eval(isolated_storage)
        
        # All metrics should be in valid range [0,1]
        assert 0.0 <= result["mrr"] <= 1.0, f"MRR {result['mrr']} should be in [0,1]"
        assert 0.0 <= result["taxa_freshness"] <= 1.0, f"freshness {result['taxa_freshness']} should be in [0,1]"
        assert 0.0 <= result["taxa_forgetting"] <= 1.0, f"forgetting {result['taxa_forgetting']} should be in [0,1]"
            
    @pytest.mark.asyncio 
    async def test_eval_returns_required_metrics(self, isolated_storage):
        """GREEN: When implemented, should return dict with mrr, taxa_freshness, taxa_forgetting."""
        
        # GREEN: Now implemented and should return the expected structure
        result = await run_adversarial_eval(isolated_storage)
        
        # Expected structure (when implemented)
        assert isinstance(result, dict), "Should return dict"
        assert "mrr" in result, "Should include MRR metric" 
        assert "taxa_freshness" in result, "Should include freshness rate"
        assert "taxa_forgetting" in result, "Should include forgetting rate"
        
        # Metrics should be numeric [0,1] range
        assert 0.0 <= result["mrr"] <= 1.0, "MRR should be in [0,1]"
        assert 0.0 <= result["taxa_freshness"] <= 1.0, "freshness should be in [0,1]"  
        assert 0.0 <= result["taxa_forgetting"] <= 1.0, "forgetting should be in [0,1]"


class TestFreshnessDetection:
    """GREEN tests for freshness measurement (frente C)."""
    
    @pytest.mark.asyncio
    async def test_freshness_perfect_with_flag_enabled(self, storage_with_synthetic_versioned_pairs):
        """GREEN: With MCP_INJECT_FRESHNESS=true, taxa_freshness should be 1.0."""
        
        # Enable freshness injection
        os.environ["MCP_INJECT_FRESHNESS"] = "true"
        
        try:
            result = await run_adversarial_eval(storage_with_synthetic_versioned_pairs)
            
            # With frente C enabled, newer versions should ALWAYS rank above older ones
            assert result["taxa_freshness"] == 1.0, \
                f"With freshness enabled, expected perfect freshness score 1.0, got {result['taxa_freshness']}"
                
        finally:
            os.environ.pop("MCP_INJECT_FRESHNESS", None)
            
    @pytest.mark.asyncio
    async def test_freshness_degraded_with_flag_disabled(self, storage_with_synthetic_versioned_pairs):
        """GREEN: With MCP_INJECT_FRESHNESS=false, taxa_freshness should be < 1.0."""
        
        # Disable freshness injection  
        os.environ["MCP_INJECT_FRESHNESS"] = "false"
        
        try:
            result = await run_adversarial_eval(storage_with_synthetic_versioned_pairs)
            
            # Without frente C, ranking should be timestamp-agnostic (confidence/relevance only)
            # So taxa_freshness should be around 0.5 (random) or < 1.0 (deterministic but not freshness-aware)
            assert result["taxa_freshness"] < 1.0, \
                f"With freshness disabled, expected imperfect freshness score < 1.0, got {result['taxa_freshness']}"
                
        finally:
            os.environ.pop("MCP_INJECT_FRESHNESS", None)


class TestForgettingDetection:
    """GREEN tests for forgetting measurement (frente B)."""
    
    @pytest.mark.asyncio
    async def test_forgetting_detected_with_flag_enabled(self, storage_with_synthetic_unused_beliefs):
        """GREEN: With MCP_BELIEF_USE_FEEDBACK=true, taxa_forgetting should be > 0."""
        
        # Enable belief usage feedback (negative signal) AND telemetry
        os.environ["MCP_BELIEF_USE_FEEDBACK"] = "true"
        os.environ["MCP_USAGE_TELEMETRY"] = "true"
        
        try:
            result = await run_adversarial_eval(storage_with_synthetic_unused_beliefs)
            
            # With frente B enabled, unused beliefs should have degraded confidence
            assert result["taxa_forgetting"] > 0.0, \
                f"With forgetting enabled, expected positive forgetting rate > 0.0, got {result['taxa_forgetting']}"
                
        finally:
            os.environ.pop("MCP_BELIEF_USE_FEEDBACK", None)
            os.environ.pop("MCP_USAGE_TELEMETRY", None)
            
    @pytest.mark.asyncio
    async def test_no_forgetting_with_flag_disabled(self, storage_with_synthetic_unused_beliefs):
        """GREEN: With MCP_BELIEF_USE_FEEDBACK=false, taxa_forgetting should be 0.0."""
        
        # Disable belief usage feedback
        os.environ["MCP_BELIEF_USE_FEEDBACK"] = "false"
        
        try:
            result = await run_adversarial_eval(storage_with_synthetic_unused_beliefs)
            
            # Without frente B, unused beliefs should retain their confidence  
            assert result["taxa_forgetting"] == 0.0, \
                f"With forgetting disabled, expected zero forgetting rate 0.0, got {result['taxa_forgetting']}"
                
        finally:
            os.environ.pop("MCP_BELIEF_USE_FEEDBACK", None)


class TestDeterministicOfflineOperation:
    """GREEN tests ensuring eval runs offline and deterministically."""
    
    @pytest.mark.asyncio
    async def test_eval_runs_without_network(self, isolated_storage):
        """GREEN: Eval should run without network access (offline requirement)."""
        
        # Mock network failures to ensure offline operation
        import socket
        
        original_getaddrinfo = socket.getaddrinfo
        
        def mock_getaddrinfo(*args, **kwargs):
            raise socket.gaierror("Network unreachable (mocked)")
            
        socket.getaddrinfo = mock_getaddrinfo
        
        try:
            # Should work even with network mocked out
            result = await run_adversarial_eval(isolated_storage) 
            
            # If it returns, it ran offline successfully
            assert isinstance(result, dict), "Should complete offline"
            
        finally:
            socket.getaddrinfo = original_getaddrinfo
            
    @pytest.mark.asyncio 
    async def test_eval_produces_identical_results_on_repeat_runs(self, isolated_storage):
        """GREEN: Eval should be deterministic - same input should give same output."""
        
        # Run twice on same storage
        result1 = await run_adversarial_eval(isolated_storage)
        result2 = await run_adversarial_eval(isolated_storage)
        
        # Should be identical (deterministic)
        assert result1["mrr"] == result2["mrr"], "MRR should be deterministic"
        assert result1["taxa_freshness"] == result2["taxa_freshness"], "freshness should be deterministic"
        assert result1["taxa_forgetting"] == result2["taxa_forgetting"], "forgetting should be deterministic"


class TestMRRIntegration:
    """GREEN tests for MRR measurement integration."""
    
    @pytest.mark.asyncio
    async def test_mrr_baseline_reasonable_range(self, isolated_storage):
        """GREEN: MRR should be in reasonable range, ideally near LoCoMo baseline 0.4140."""
        
        result = await run_adversarial_eval(isolated_storage)
        
        # MRR should be in valid range
        mrr = result["mrr"]
        assert 0.0 <= mrr <= 1.0, f"MRR {mrr} should be in [0,1]"
        
        # Ideally should be non-zero if using LoCoMo subset
        # (May be 0.0 if using purely synthetic data without proper Q&A pairs)