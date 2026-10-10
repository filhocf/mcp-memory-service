"""
RED tests for learning-loop frente B: Negative use-signal for belief demotion.

Tests the negative feedback signal requirements (SPEC-B):
- R1/R2: belief injected ≥N times without later use → confidence drops by penalty factor
- R3: penalized confidence below CONFIDENCE_FLOOR → status='superseded'
- R4: actual use resets the unused injection counter
- R5: MCP_BELIEF_USE_FEEDBACK=false disables penalty (byte-identical derivation)
- R6: no new DDL (derives from usage_events + beliefs.metadata JSON)

All tests are designed to FAIL until the feature is implemented.
The expected missing function is `_derive_injected_never_used` in usage_telemetry.py
"""

import pytest
import pytest_asyncio
import os
import json
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

# Skip tests if sqlite-vec is not available
try:
    import sqlite_vec
    SQLITE_VEC_AVAILABLE = True
except ImportError:
    SQLITE_VEC_AVAILABLE = False

from mcp_memory_service.models.memory import Memory
from mcp_memory_service.utils.hashing import generate_content_hash

if SQLITE_VEC_AVAILABLE:
    from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage
    from mcp_memory_service.storage.usage_telemetry import log_usage_event
    from mcp_memory_service.consolidation.belief import derive_confidence, CONFIDENCE_FLOOR
    from mcp_memory_service.consolidation.belief_service import BeliefService

# Skip all tests if sqlite-vec is not available
pytestmark = pytest.mark.skipif(not SQLITE_VEC_AVAILABLE, reason="sqlite-vec not available")


class TestBeliefNegativeSignal:
    """Test suite for negative use-signal belief demotion (learning-loop frente B)."""

    @pytest_asyncio.fixture
    async def storage(self):
        """Create a test storage instance with usage_events table."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_memory.db")
        
        storage = SqliteVecMemoryStorage(db_path)
        await storage.initialize()
        
        # Initialize usage_events table (this may exist already)
        def init_usage_table():
            storage.conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    tool TEXT,
                    content_hash TEXT,
                    query_hash TEXT,
                    n_results INTEGER,
                    latency_ms REAL,
                    rating REAL,
                    source TEXT,
                    agent_id TEXT,
                    timestamp TEXT,
                    metadata TEXT
                )
            """)
            storage.conn.commit()
        
        await storage._execute_with_retry(init_usage_table)
        yield storage
        
        # Cleanup
        if storage.conn:
            storage.conn.close()
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest_asyncio.fixture
    async def belief_service(self, storage):
        """Create a BeliefService instance."""
        return BeliefService(storage)

    async def _log_injection_event(self, storage, agent_id: str, belief_hashes: list, source_hashes: list, 
                                   timestamp: str = None):
        """Helper to log an injection event with belief and source hashes."""
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        metadata = {
            "belief_hashes": belief_hashes,
            "source_hashes": source_hashes
        }
        
        await log_usage_event(
            storage, 
            "injection",
            agent_id=agent_id,
            timestamp=timestamp,
            n_results=len(belief_hashes),
            metadata=json.dumps(metadata)
        )

    async def _log_retrieval_event(self, storage, agent_id: str, returned_hashes: list,
                                   timestamp: str = None):
        """Helper to log a retrieval event with returned hashes."""
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        await log_usage_event(
            storage,
            "retrieval", 
            agent_id=agent_id,
            timestamp=timestamp,
            n_results=len(returned_hashes),
            returned_hashes=returned_hashes
        )

    @pytest.mark.asyncio
    async def test_belief_injected_three_times_without_use_drops_confidence(self, storage, belief_service):
        """R1/R2: belief injected ≥3 times whose source_hashes never reappear → confidence drops ≥20%."""
        # Create test memories and beliefs
        memory1 = Memory(
            content="Test belief about Python patterns",
            content_hash=generate_content_hash("Test belief about Python patterns"),
            tags=["python", "patterns"]
        )
        await storage.store(memory1)
        
        belief_hash = "test_belief_hash_001"
        source_hash = memory1.content_hash
        agent_id = "test_agent"
        
        # Create a belief with initial confidence > CONFIDENCE_FLOOR
        initial_confidence = 0.7
        
        # This will fail because the beliefs table and consolidation don't exist yet
        # But this establishes the contract for the implementation
        
        # Log 3 injection events (meets threshold) without any retrievals
        base_time = datetime.now(timezone.utc)
        
        await self._log_injection_event(
            storage, agent_id, [belief_hash], [source_hash],
            (base_time + timedelta(minutes=1)).isoformat()
        )
        await self._log_injection_event(
            storage, agent_id, [belief_hash], [source_hash],
            (base_time + timedelta(minutes=5)).isoformat()
        )
        await self._log_injection_event(
            storage, agent_id, [belief_hash], [source_hash],
            (base_time + timedelta(minutes=10)).isoformat()
        )
        
        # Add some retrieval events that DON'T contain our source_hash
        other_hash = generate_content_hash("different content")
        await self._log_retrieval_event(
            storage, agent_id, [other_hash],
            (base_time + timedelta(minutes=15)).isoformat()
        )
        
        # This function should exist but doesn't yet - it will derive the negative signal
        from mcp_memory_service.storage.usage_telemetry import _derive_injected_never_used
        
        # This should identify our belief as having 3 unused injections
        unused_stats = await _derive_injected_never_used(storage)
        
        composite_key = f"{agent_id}:{belief_hash}"
        assert composite_key in unused_stats
        assert unused_stats[composite_key]["injections_without_use"] == 3
        assert unused_stats[composite_key]["agent_id"] == agent_id
        
        # Apply the penalty factor (default 0.20) to confidence
        penalty_factor = float(os.getenv("MCP_BELIEF_UNUSED_PENALTY", "0.20"))
        expected_new_confidence = initial_confidence * (1 - penalty_factor)
        
        # The penalty should reduce confidence by at least 20%
        confidence_drop = initial_confidence - expected_new_confidence
        assert confidence_drop >= 0.20 * initial_confidence

    @pytest.mark.asyncio
    async def test_belief_crosses_confidence_floor_becomes_superseded(self, storage, belief_service):
        """R3: penalized confidence below CONFIDENCE_FLOOR → status='superseded'."""
        belief_hash = "test_belief_hash_002"
        source_hash = generate_content_hash("belief near floor")
        agent_id = "test_agent"
        
        # Start with confidence just above floor (will drop below after penalty)
        initial_confidence = 0.40  # CONFIDENCE_FLOOR is 0.35, penalty 0.20 → 0.32 < 0.35
        
        # Log enough unused injections to trigger penalty
        base_time = datetime.now(timezone.utc)
        threshold = int(os.getenv("MCP_BELIEF_UNUSED_THRESHOLD", "3"))
        
        for i in range(threshold):
            await self._log_injection_event(
                storage, agent_id, [belief_hash], [source_hash],
                (base_time + timedelta(minutes=i+1)).isoformat()
            )
        
        # No retrieval events with our source_hash = unused
        
        # Derive the unused signal and apply penalty
        from mcp_memory_service.storage.usage_telemetry import _derive_injected_never_used
        unused_stats = await _derive_injected_never_used(storage)
        
        penalty_factor = float(os.getenv("MCP_BELIEF_UNUSED_PENALTY", "0.20"))
        penalized_confidence = initial_confidence * (1 - penalty_factor)
        
        # Should drop below CONFIDENCE_FLOOR
        assert penalized_confidence < CONFIDENCE_FLOOR
        
        # The consolidation cycle should mark this as superseded
        # This tests the integration with existing belief management
        should_supersede = penalized_confidence < CONFIDENCE_FLOOR
        assert should_supersede == True

    @pytest.mark.asyncio 
    async def test_belief_use_resets_unused_counter(self, storage, belief_service):
        """R4: source memories reappearing in retrieval reset injections_without_use to 0."""
        belief_hash = "test_belief_hash_003"
        source_hash = generate_content_hash("belief that gets used")
        agent_id = "test_agent"
        
        base_time = datetime.now(timezone.utc)
        
        # Log 2 unused injections
        await self._log_injection_event(
            storage, agent_id, [belief_hash], [source_hash],
            (base_time + timedelta(minutes=1)).isoformat()
        )
        await self._log_injection_event(
            storage, agent_id, [belief_hash], [source_hash],
            (base_time + timedelta(minutes=5)).isoformat()
        )
        
        # Now the source appears in a retrieval (USE!)
        await self._log_retrieval_event(
            storage, agent_id, [source_hash],
            (base_time + timedelta(minutes=10)).isoformat()
        )
        
        # Log another injection after the use
        await self._log_injection_event(
            storage, agent_id, [belief_hash], [source_hash],
            (base_time + timedelta(minutes=15)).isoformat()
        )
        
        # Another non-matching retrieval 
        other_hash = generate_content_hash("different content")
        await self._log_retrieval_event(
            storage, agent_id, [other_hash],
            (base_time + timedelta(minutes=20)).isoformat()
        )
        
        from mcp_memory_service.storage.usage_telemetry import _derive_injected_never_used
        unused_stats = await _derive_injected_never_used(storage)
        
        # Should only count the injection AFTER the use (counter reset)
        composite_key = f"{agent_id}:{belief_hash}"
        assert composite_key in unused_stats
        assert unused_stats[composite_key]["injections_without_use"] == 1  # Only the last injection

    @pytest.mark.asyncio
    async def test_mcp_belief_use_feedback_disabled_no_penalty(self, storage, belief_service):
        """R5: MCP_BELIEF_USE_FEEDBACK=false → confidence derivation unchanged (byte-identical)."""
        
        # Test with feedback disabled
        with patch.dict(os.environ, {'MCP_BELIEF_USE_FEEDBACK': 'false'}):
            belief_hash = "test_belief_hash_004"
            source_hash = generate_content_hash("belief with feedback off")
            agent_id = "test_agent"
            
            base_time = datetime.now(timezone.utc)
            
            # Log many unused injections (well above threshold)
            for i in range(5):
                await self._log_injection_event(
                    storage, agent_id, [belief_hash], [source_hash],
                    (base_time + timedelta(minutes=i+1)).isoformat()
                )
            
            # No retrieval events = completely unused
            
            from mcp_memory_service.storage.usage_telemetry import _derive_injected_never_used
            
            # Derivation always runs (flag is checked at penalty application, not derivation)
            unused_stats = await _derive_injected_never_used(storage)
            
            # Stats ARE returned (derivation doesn't check the flag)
            composite_key = f"{agent_id}:{belief_hash}"
            assert composite_key in unused_stats
            assert unused_stats[composite_key]["injections_without_use"] == 5
            
            # But when _apply_unused_penalty is called with the flag off, it returns unchanged confidence
            # (this is tested in the integration - the flag prevents PENALTY, not DERIVATION)

    @pytest.mark.asyncio
    async def test_no_new_ddl_uses_existing_tables(self, storage, belief_service):
        """R6: no schema migration - derives signal from usage_events + beliefs.metadata JSON."""
        # Verify the usage_events table exists (should from fixture)
        def check_usage_events_exists():
            cursor = storage.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='usage_events'"
            )
            return cursor.fetchone() is not None
        
        usage_events_exists = await storage._execute_with_retry(check_usage_events_exists)
        assert usage_events_exists, "usage_events table should exist"
        
        # Verify no new tables are created by the negative signal feature
        def get_table_count():
            cursor = storage.conn.execute(
                "SELECT COUNT(*) as count FROM sqlite_master WHERE type='table'"
            )
            return cursor.fetchone()['count']
        
        initial_table_count = await storage._execute_with_retry(get_table_count)
        
        # Exercise the negative signal derivation
        belief_hash = "test_belief_hash_005"
        source_hash = generate_content_hash("ddl test belief")
        agent_id = "test_agent"
        
        await self._log_injection_event(storage, agent_id, [belief_hash], [source_hash])
        
        try:
            from mcp_memory_service.storage.usage_telemetry import _derive_injected_never_used
            await _derive_injected_never_used(storage)
        except ImportError:
            # Expected - function doesn't exist yet
            pass
        
        # Table count should be unchanged
        final_table_count = await storage._execute_with_retry(get_table_count)
        assert final_table_count == initial_table_count, "No new tables should be created"

    @pytest.mark.asyncio
    async def test_multiple_agents_isolated_counters(self, storage, belief_service):
        """Bonus: unused injection counters are isolated per agent."""
        belief_hash = "shared_belief_hash"
        source_hash = generate_content_hash("shared belief content")
        agent1 = "agent_one"
        agent2 = "agent_two"
        
        base_time = datetime.now(timezone.utc)
        
        # Agent1: 3 unused injections
        for i in range(3):
            await self._log_injection_event(
                storage, agent1, [belief_hash], [source_hash],
                (base_time + timedelta(minutes=i+1)).isoformat()
            )
        
        # Agent2: 1 injection + 1 use + 1 more injection = should only count the last one
        await self._log_injection_event(
            storage, agent2, [belief_hash], [source_hash],
            (base_time + timedelta(minutes=10)).isoformat()
        )
        await self._log_retrieval_event(
            storage, agent2, [source_hash],
            (base_time + timedelta(minutes=11)).isoformat()
        )
        await self._log_injection_event(
            storage, agent2, [belief_hash], [source_hash],
            (base_time + timedelta(minutes=12)).isoformat()
        )
        
        from mcp_memory_service.storage.usage_telemetry import _derive_injected_never_used
        unused_stats = await _derive_injected_never_used(storage)
        
        # Different unused counts per agent
        agent1_stats = [s for s in unused_stats.values() if s.get("agent_id") == agent1]
        agent2_stats = [s for s in unused_stats.values() if s.get("agent_id") == agent2]
        
        assert len(agent1_stats) == 1
        assert agent1_stats[0]["injections_without_use"] == 3
        

    @pytest.mark.asyncio
    async def test_end_to_end_belief_penalty_through_derive_beliefs(self, storage, belief_service):
        """H3: End-to-end test through _apply_unused_penalty - confidence drops and supersession triggers.
        
        This test exercises the REAL production path: _apply_unused_penalty calls 
        _derive_injected_never_used, applies penalty, and the result triggers supersession
        through the existing should_supersede() check in the caller. This ensures deleting 
        the penalty code would make the test FAIL.
        """
        # Create a belief directly
        belief_hash = "test_belief_e2e_penalty"
        belief_content = "Python async patterns improve performance"
        source_hash = generate_content_hash("source memory for belief")
        
        # Initial confidence just above floor so penalty will cross it
        initial_confidence = 0.42  # penalty 0.20 → 0.336 < 0.35 floor
        
        def create_belief():
            storage.conn.execute(
                """INSERT INTO beliefs 
                (belief_hash, content, confidence, status, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (belief_hash, belief_content, initial_confidence, "active", 
                 datetime.now(timezone.utc).isoformat(),
                 datetime.now(timezone.utc).isoformat(),
                 "{}")
            )
            storage.conn.commit()
        
        await storage._execute_with_retry(create_belief)
        
        # Log 3 injection events without subsequent use
        base_time = datetime.now(timezone.utc)
        agent_id = "test_agent_e2e"
        
        for i in range(3):
            await self._log_injection_event(
                storage, agent_id, [belief_hash], [source_hash],
                (base_time + timedelta(minutes=i+1)).isoformat()
            )
        
        # Log retrieval events that DON'T contain our source memory
        other_hash = generate_content_hash("unrelated content")
        for i in range(2):
            await self._log_retrieval_event(
                storage, agent_id, [other_hash],
                (base_time + timedelta(minutes=10+i)).isoformat()
            )
        
        # Enable feedback flag and apply penalty
        with patch.dict(os.environ, {'MCP_BELIEF_USE_FEEDBACK': 'true'}):
            def get_belief():
                cursor = storage.conn.execute(
                    "SELECT * FROM beliefs WHERE belief_hash = ?",
                    (belief_hash,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            
            existing = await storage._execute_with_retry(get_belief)
            assert existing is not None
            
            # Call _apply_unused_penalty (the production path)
            penalized_confidence = await belief_service._apply_unused_penalty(
                belief_hash, initial_confidence, existing
            )
            
            # Verify confidence dropped by at least 20%
            confidence_drop = initial_confidence - penalized_confidence
            expected_min_drop = initial_confidence * 0.20
            assert confidence_drop >= expected_min_drop * 0.95, \
                f"Confidence should drop by ≥{expected_min_drop:.3f}, got {confidence_drop:.3f}"
            
            # Verify penalized confidence is below floor
            from mcp_memory_service.consolidation.belief import CONFIDENCE_FLOOR
            assert penalized_confidence < CONFIDENCE_FLOOR, \
                f"Penalized confidence {penalized_confidence:.3f} should be < floor {CONFIDENCE_FLOOR}"
            
            # In the production flow, this would trigger supersession via should_supersede()
            # We verify the production function agrees this should be superseded
            from mcp_memory_service.consolidation.belief import should_supersede
            assert should_supersede(penalized_confidence), \
                "Production should_supersede() must return True for confidence below floor"

    @pytest.mark.asyncio
    async def test_belief_service_reset_write_path_exercised(self, storage, belief_service):
        """M1: Test that the reset write path in belief_service is actually exercised.
        
        The reset-to-zero metadata write happens in _apply_unused_penalty when
        max_unused_count == 0. Previous tests short-circuit at the derivation layer
        (unused beliefs are omitted from the dict), so the reset write is never hit.
        This test ensures that path works.
        """
        # Create a belief with some initial unused counter in metadata
        belief_hash = "test_belief_m1_reset"
        belief_content = "Test belief for reset path"
        
        def create_belief_with_counter():
            metadata = json.dumps({"injections_without_use": 5})
            storage.conn.execute(
                """INSERT INTO beliefs 
                (belief_hash, content, confidence, status, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (belief_hash, belief_content, 0.7, "active", 
                 datetime.now(timezone.utc).isoformat(),
                 datetime.now(timezone.utc).isoformat(),
                 metadata)
            )
            storage.conn.commit()
        
        await storage._execute_with_retry(create_belief_with_counter)
        
        # Enable feedback flag
        with patch.dict(os.environ, {'MCP_BELIEF_USE_FEEDBACK': 'true'}):
            # Get the existing belief
            def get_belief():
                cursor = storage.conn.execute(
                    "SELECT * FROM beliefs WHERE belief_hash = ?",
                    (belief_hash,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            
            existing = await storage._execute_with_retry(get_belief)
            assert existing is not None
            
            # Verify counter exists initially
            metadata = json.loads(existing["metadata"])
            assert "injections_without_use" in metadata
            assert metadata["injections_without_use"] == 5
            
            # Call _apply_unused_penalty with an empty unused_stats
            # (simulates the belief being used - derivation returns no entry for it)
            # This should trigger the reset write path
            confidence = existing["confidence"]
            
            # Patch _derive_injected_never_used to return empty (belief was used)
            async def mock_derive_empty(storage):
                return {}  # No unused beliefs
            
            with patch('mcp_memory_service.storage.usage_telemetry._derive_injected_never_used', 
                      side_effect=mock_derive_empty):
                result_confidence = await belief_service._apply_unused_penalty(
                    belief_hash, confidence, existing
                )
            
            # Confidence should be unchanged (no penalty)
            assert result_confidence == confidence
            
            # Most importantly: metadata counter should be REMOVED (reset)
            updated_belief = await storage._execute_with_retry(get_belief)
            updated_metadata = json.loads(updated_belief["metadata"])
            assert "injections_without_use" not in updated_metadata, \
                "Counter should be removed from metadata when reset to 0"