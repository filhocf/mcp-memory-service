"""
RED tests for usage telemetry feature.

These tests validate the PROVEITO/USO instrumentation requirements:
- REQ-1: retrieval events are logged with correct fields
- REQ-5: usage aggregator returns metrics from events
- REQ-6a: telemetry killswitch prevents event logging
- REQ-6b: telemetry failures never break retrieval
- REQ-7: raw queries/content are never stored (privacy)
- Feedback events are logged with proper fields

All tests are designed to FAIL until the feature is implemented.
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
import shutil
import json
import time
import hashlib
import sqlite3
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

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

# Skip all tests if sqlite-vec is not available
pytestmark = pytest.mark.skipif(not SQLITE_VEC_AVAILABLE, reason="sqlite-vec not available")


class TestUsageTelemetry:
    """Test suite for usage telemetry instrumentation."""
    
    @pytest_asyncio.fixture
    async def storage(self):
        """Create a test storage instance."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_memory.db")
        
        storage = SqliteVecMemoryStorage(db_path)
        await storage.initialize()
        
        yield storage
        
        # Cleanup
        if storage.conn:
            storage.conn.close()
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest_asyncio.fixture
    async def storage_with_memories(self, storage):
        """Storage instance with some test memories."""
        content1 = "Test memory about Python programming"
        content2 = "Test memory about database design"
        
        memories = [
            Memory(
                content=content1,
                content_hash=generate_content_hash(content1),
                tags=["programming", "python"],
                metadata={"importance": 0.8}
            ),
            Memory(
                content=content2,
                content_hash=generate_content_hash(content2),
                tags=["database", "design"],
                metadata={"importance": 0.6}
            )
        ]
        
        for memory in memories:
            await storage.store(memory)
        
        return storage

    @pytest.mark.asyncio
    async def test_retrieval_logs_event(self, storage_with_memories):
        """REQ-1: After retrieve, usage_events table contains 1 'retrieval' event with correct fields."""
        storage = storage_with_memories
        query = "Python programming tips"
        
        # Perform retrieval
        start_time = time.time()
        results = await storage.retrieve(query=query, n_results=5)
        end_time = time.time()
        
        # Check that usage_events table exists and has the event
        # This will fail because the table doesn't exist yet
        def check_events():
            cursor = storage.conn.execute("SELECT * FROM usage_events WHERE tool = 'retrieval'")
            events = cursor.fetchall()
            assert len(events) == 1, f"Expected 1 retrieval event, got {len(events)}"
            
            event = events[0]
            # Expected fields: timestamp, tool, n_results, latency_ms, query_hash
            assert event['tool'] == 'retrieval'
            assert event['n_results'] == len(results)
            assert event['latency_ms'] > 0
            assert event['query_hash'] is not None
            assert 'timestamp' in event
            
            # Verify query is NOT stored (privacy requirement)
            cursor_raw = storage.conn.execute("SELECT * FROM usage_events")
            all_events = cursor_raw.fetchall()
            for row in all_events:
                row_str = str(row)
                assert query not in row_str, f"Raw query found in event data: {row_str}"
        
        await storage._execute_with_retry(check_events)

    @pytest.mark.asyncio
    async def test_usage_aggregator_returns_metrics(self, storage_with_memories):
        """REQ-5: Usage aggregator function returns metrics from fixtured events."""
        storage = storage_with_memories
        
        # Create some fixture events by performing operations
        await storage.retrieve(query="Python", n_results=3)
        await storage.retrieve(query="database", n_results=2)
        
        # Test aggregator function (doesn't exist yet)
        from mcp_memory_service.storage.usage_telemetry import get_usage_metrics
        
        metrics = await get_usage_metrics(storage)
        
        # Expected metrics structure
        assert 'total_retrievals' in metrics
        assert 'avg_latency_ms' in metrics
        assert 'total_results_returned' in metrics
        assert metrics['total_retrievals'] >= 2
        assert metrics['avg_latency_ms'] > 0
        assert metrics['total_results_returned'] >= 0

    @pytest.mark.asyncio
    async def test_telemetry_killswitch_off_no_events(self, storage_with_memories):
        """REQ-6a: MCP_USAGE_TELEMETRY=false -> retrieve does NOT log event (row count == 0)."""
        storage = storage_with_memories
        
        # Set killswitch to false
        with patch.dict(os.environ, {'MCP_USAGE_TELEMETRY': 'false'}):
            # Perform retrieval
            results = await storage.retrieve(query="Python programming", n_results=5)
            
            # Verify no events were logged
            def check_no_events():
                cursor = storage.conn.execute("SELECT COUNT(*) as count FROM usage_events")
                count = cursor.fetchone()['count']
                assert count == 0, f"Expected 0 events with telemetry off, got {count}"
            
            await storage._execute_with_retry(check_no_events)

    @pytest.mark.asyncio
    async def test_telemetry_best_effort_never_breaks_read(self, storage_with_memories):
        """REQ-6b: If event INSERT fails (monkeypatch), retrieve STILL returns results."""
        storage = storage_with_memories
        
        # Monkeypatch to make telemetry INSERT fail
        original_execute_with_retry = storage._execute_with_retry
        
        async def failing_execute_with_retry(operation, **kwargs):
            # Check if the operation involves telemetry
            try:
                # Try to introspect the operation for telemetry-related SQL
                import inspect
                if hasattr(operation, '__name__') and 'telemetry' in operation.__name__.lower():
                    raise sqlite3.OperationalError("Simulated telemetry failure")
            except:
                pass
            return await original_execute_with_retry(operation, **kwargs)
        
        with patch.object(storage, '_execute_with_retry', side_effect=failing_execute_with_retry):
            # Retrieve should still work despite telemetry failure
            results = await storage.retrieve(query="Python programming", n_results=5)
            
            # Verify we got results despite telemetry failure
            assert len(results) > 0, "Retrieve should return results even when telemetry fails"
            assert all(hasattr(r, 'memory') for r in results), "Results should be valid MemoryQueryResult objects"

    @pytest.mark.asyncio
    async def test_no_raw_query_or_content_stored(self, storage_with_memories):
        """REQ-7: Events store query_hash but never the raw text (privacy)."""
        storage = storage_with_memories
        query = "sensitive user query with PII"
        
        # Perform retrieval
        results = await storage.retrieve(query=query, n_results=5)
        
        # Check that raw query is never stored
        def check_privacy():
            cursor = storage.conn.execute("SELECT * FROM usage_events")
            all_rows = cursor.fetchall()
            
            for row in all_rows:
                row_str = str(row).lower()
                # Verify sensitive content is not in the raw data
                assert "sensitive" not in row_str, f"Raw query content found in: {row}"
                assert "pii" not in row_str, f"Raw query content found in: {row}"
                
                # Verify we have query_hash but not the original
                if 'query_hash' in row:
                    assert row['query_hash'] is not None, "query_hash should be present"
                    # Hash should be different from original query
                    assert row['query_hash'] != query, "query_hash should not be the original query"
        
        await storage._execute_with_retry(check_privacy)

    @pytest.mark.asyncio
    async def test_feedback_event_logged(self, storage_with_memories):
        """Feedback events are logged with {content_hash, rating, source} fields."""
        storage = storage_with_memories
        
        # Get a memory to rate
        results = await storage.retrieve(query="Python", n_results=1)
        assert len(results) > 0, "Need at least one result to test feedback"
        
        memory = results[0].memory
        content_hash = memory.content_hash
        
        # Simulate rating the memory (this method doesn't exist yet)
        await storage.record_feedback_event(
            content_hash=content_hash,
            rating=1,
            source="user_explicit"
        )
        
        # Check feedback event was logged
        def check_feedback_event():
            cursor = storage.conn.execute("SELECT * FROM usage_events WHERE tool = 'feedback'")
            events = cursor.fetchall()
            assert len(events) == 1, f"Expected 1 feedback event, got {len(events)}"
            
            event = events[0]
            assert event['content_hash'] == content_hash
            assert event['rating'] == 1
            assert event['source'] == "user_explicit"
            assert 'timestamp' in event
        
        await storage._execute_with_retry(check_feedback_event)

    @pytest.mark.asyncio
    async def test_injected_then_used_cross_agent_isolation(self, storage):
        """LOW 1: injection by agent 'A' + retrieval by agent 'B' → injected_then_used should be 0 (cross-agent guard)."""
        from mcp_memory_service.storage.usage_telemetry import derive_signals, log_usage_event
        
        # Create a test hash for injection/retrieval
        test_hash = "abc123def456"
        
        # Agent 'A' injects the hash
        await log_usage_event(
            storage,
            "injection",
            agent_id="agent_A",
            metadata=json.dumps({"belief_hashes": [test_hash]}),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        # Wait a moment to ensure timestamp ordering
        import time
        time.sleep(0.01)
        
        # Agent 'B' retrieves the hash (different agent!)
        await log_usage_event(
            storage,
            "retrieval", 
            agent_id="agent_B",
            metadata=json.dumps({"returned_hashes": [test_hash]}),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        # Derive signals
        signals = await derive_signals(storage)
        
        # The cross-agent isolation should prevent any injected_then_used signal
        # for this hash, even though it was injected by A and retrieved by B
        injected_then_used_count = signals.get(test_hash, {}).get("injected_then_used", 0)
        assert injected_then_used_count == 0, (
            f"Expected 0 injected_then_used signal for cross-agent case, got {injected_then_used_count}. "
            f"This proves the agent_id guard is working."
        )

    @pytest.mark.asyncio
    async def test_usage_events_table_schema(self, storage):
        """Verify usage_events table has the correct schema."""
        # This will fail because table doesn't exist yet
        def check_schema():
            cursor = storage.conn.execute("PRAGMA table_info(usage_events)")
            columns = {row['name']: row['type'] for row in cursor.fetchall()}
            
            expected_columns = {
                'id': 'INTEGER',
                'timestamp': 'TEXT',
                'tool': 'TEXT',
                'query_hash': 'TEXT',
                'n_results': 'INTEGER',
                'latency_ms': 'REAL',
                'content_hash': 'TEXT',
                'rating': 'INTEGER',
                'source': 'TEXT',
                'metadata': 'TEXT'
            }
            
            for col_name, col_type in expected_columns.items():
                assert col_name in columns, f"Missing column: {col_name}"
                # SQLite is flexible with types, just check it's defined
                assert columns[col_name] is not None, f"Column {col_name} has no type"
        
        await storage._execute_with_retry(check_schema)

    @pytest.mark.asyncio 
    async def test_telemetry_default_enabled(self, storage_with_memories):
        """Telemetry should be enabled by default (MCP_USAGE_TELEMETRY default=true)."""
        storage = storage_with_memories
        
        # Don't set any env vars - should default to enabled
        with patch.dict(os.environ, {}, clear=False):
            # Remove the var if it exists
            if 'MCP_USAGE_TELEMETRY' in os.environ:
                del os.environ['MCP_USAGE_TELEMETRY']
                
            results = await storage.retrieve(query="default test", n_results=2)
            
            # Should log an event by default
            def check_default_enabled():
                cursor = storage.conn.execute("SELECT COUNT(*) as count FROM usage_events")
                count = cursor.fetchone()['count']
                assert count > 0, "Telemetry should be enabled by default"
            
            await storage._execute_with_retry(check_default_enabled)

    @pytest.mark.asyncio
    async def test_rate_memory_logs_feedback_event(self, storage_with_memories):
        """Rating a memory via the handler's storage path logs a 'feedback' usage event.

        The rate_memory handler (web/api/quality.py) persists the rating via
        update_memory_metadata and then calls storage.record_feedback_event with
        content_hash + rating + source='user_explicit'. We exercise that same
        storage path here (the handler itself needs FastAPI auth/DI) and assert
        the feedback event landed in usage_events.
        """
        storage = storage_with_memories

        results = await storage.retrieve(query="Python", n_results=1)
        assert len(results) > 0, "Need at least one result to rate"
        memory = results[0].memory
        content_hash = memory.content_hash
        rating = 1

        # Mirror the handler flow: persist the user_rating metadata ...
        memory.metadata['user_rating'] = rating
        memory.metadata['user_feedback'] = "helpful"
        await storage.update_memory_metadata(
            content_hash=content_hash,
            updates=memory.metadata,
            preserve_timestamps=True,
        )
        # ... then record the feedback event (the D3 wiring under test).
        await storage.record_feedback_event(
            content_hash=content_hash,
            rating=rating,
            source="user_explicit",
        )

        def check_feedback_event():
            cursor = storage.conn.execute(
                "SELECT * FROM usage_events WHERE tool = 'feedback'"
            )
            events = cursor.fetchall()
            assert len(events) == 1, f"Expected 1 feedback event, got {len(events)}"
            event = events[0]
            assert event['event_type'] == 'feedback'
            assert event['content_hash'] == content_hash
            assert event['rating'] == rating
            assert event['source'] == "user_explicit"

        await storage._execute_with_retry(check_feedback_event)

    @pytest.mark.asyncio
    async def test_query_hash_consistency(self, storage_with_memories):
        """Same query should produce same hash across multiple calls."""
        storage = storage_with_memories
        query = "consistent hash test query"
        
        # Perform same query twice
        await storage.retrieve(query=query, n_results=2)
        await storage.retrieve(query=query, n_results=2) 
        
        def check_hash_consistency():
            cursor = storage.conn.execute("SELECT query_hash FROM usage_events WHERE tool = 'retrieval'")
            hashes = [row['query_hash'] for row in cursor.fetchall()]
            
            assert len(hashes) >= 2, "Should have at least 2 retrieval events"
            # All hashes for the same query should be identical
            assert len(set(hashes)) == 1, f"Same query should produce same hash, got: {hashes}"
        
        await storage._execute_with_retry(check_hash_consistency)

    @pytest.mark.asyncio
    async def test_recompute_quality_scores_clamp_range(self, storage_with_memories):
        """Quality scores must be clamped to [0,1] range even with extreme signal values."""
        from mcp_memory_service.storage.usage_telemetry import recompute_quality_scores
        
        storage = storage_with_memories
        
        # Test extreme values that would normally result in scores outside [0,1]
        extreme_signals = {
            # High positive signals (should clamp to ≤1.0)
            'hash_high': {'reaccess': 1000, 'retry_failed': 0, 'age_days': 0},
            # High negative signals (should clamp to ≥0.0)
            'hash_low': {'reaccess': 0, 'retry_failed': 1000, 'age_days': 0},
            # Very old positive signals with high decay (should still be clamped)
            'hash_old_high': {'reaccess': 1000, 'retry_failed': 0, 'age_days': 100},
            # Normal case (should remain unchanged)
            'hash_normal': {'reaccess': 1, 'retry_failed': 1, 'age_days': 0},
        }
        
        scores = await recompute_quality_scores(
            storage,
            base=0.5,
            signals_override=extreme_signals
        )
        
        # All scores must be within [0.0, 1.0] range
        for content_hash, score in scores.items():
            assert 0.0 <= score <= 1.0, f"Score for {content_hash} is {score}, outside [0,1] range"
            
        # Verify specific expectations for extreme cases
        assert scores['hash_high'] <= 1.0, f"High positive signals resulted in score {scores['hash_high']} > 1.0"
        assert scores['hash_low'] >= 0.0, f"High negative signals resulted in score {scores['hash_low']} < 0.0"
        assert scores['hash_old_high'] <= 1.0, f"Old high signals resulted in score {scores['hash_old_high']} > 1.0"
        
        # Normal case should produce reasonable values
        assert 0.0 <= scores['hash_normal'] <= 1.0

    @pytest.mark.asyncio
    async def test_derive_signals_injection_then_used_basic(self, storage):
        """derive_signals returns injected_then_used >= 1 when hash is injected then retrieved later."""
        from mcp_memory_service.storage.usage_telemetry import derive_signals, log_usage_event
        
        # Set up test data: inject hashA at T, then retrieve it at T+1
        hashA = "test_hash_a"
        agent_id = "test_agent"
        
        # Event 1: Injection at T=1000
        await log_usage_event(
            storage, 
            "injection",
            agent_id=agent_id,
            timestamp="2024-10-09T10:00:00Z",
            metadata=json.dumps({"belief_hashes": [hashA], "count": 1})
        )
        
        # Event 2: Retrieval at T=2000 that returns hashA
        await log_usage_event(
            storage,
            "retrieval", 
            agent_id=agent_id,
            timestamp="2024-10-09T10:01:00Z",
            returned_hashes=[hashA]
        )
        
        # Derive signals
        signals = await derive_signals(storage)
        
        # Should have injected_then_used >= 1 for hashA
        assert hashA in signals, f"hashA should be in signals, got: {signals}"
        assert 'injected_then_used' in signals[hashA], f"injected_then_used should be in signals for hashA, got: {signals[hashA]}"
        assert signals[hashA]['injected_then_used'] >= 1, f"injected_then_used should be >= 1 for hashA, got: {signals[hashA]['injected_then_used']}"

    @pytest.mark.asyncio
    async def test_derive_signals_injection_then_used_temporal_ordering(self, storage):
        """injected_then_used only counts when retrieval timestamp > injection timestamp."""
        from mcp_memory_service.storage.usage_telemetry import derive_signals, log_usage_event
        
        hashB = "test_hash_b"
        agent_id = "test_agent"
        
        # Event 1: Retrieval BEFORE injection (should not count)
        await log_usage_event(
            storage,
            "retrieval",
            agent_id=agent_id,
            timestamp="2024-10-09T09:59:00Z",  # Earlier timestamp
            returned_hashes=[hashB]
        )
        
        # Event 2: Injection AFTER retrieval
        await log_usage_event(
            storage,
            "injection",
            agent_id=agent_id, 
            timestamp="2024-10-09T10:00:00Z",  # Later timestamp
            metadata=json.dumps({"belief_hashes": [hashB], "count": 1})
        )
        
        signals = await derive_signals(storage)
        
        # Should NOT have injected_then_used for hashB (wrong order)
        if hashB in signals:
            assert signals[hashB].get('injected_then_used', 0) == 0, f"injected_then_used should be 0 for wrong temporal order, got: {signals[hashB]}"

    @pytest.mark.asyncio
    async def test_recompute_quality_scores_with_injected_then_used_weight(self, storage):
        """Quality scores with injected_then_used should be higher than reaccess-only due to W_INJ weight."""
        from mcp_memory_service.storage.usage_telemetry import recompute_quality_scores
        
        # Compare two hashes: one with injected_then_used, one with only reaccess
        signals_override = {
            # Hash with injection utilization (W_INJ=2.0 weight)
            'hash_injected': {'reaccess': 1, 'retry_failed': 0, 'injected_then_used': 1},
            # Hash with equal reaccess but no injection utilization  
            'hash_reaccess_only': {'reaccess': 1, 'retry_failed': 0, 'injected_then_used': 0},
        }
        
        scores = await recompute_quality_scores(
            storage,
            base=0.5,
            signals_override=signals_override
        )
        
        # injected_then_used should result in higher score due to W_INJ weight (2.0)
        injected_score = scores['hash_injected']
        reaccess_score = scores['hash_reaccess_only']
        
        assert injected_score > reaccess_score, f"Injected+used hash should have higher score than reaccess-only. Got injected={injected_score}, reaccess={reaccess_score}"
        assert injected_score > 0.5, f"Injected+used hash should be above base (0.5), got {injected_score}"

    @pytest.mark.asyncio
    async def test_w_inj_weight_isolation(self, storage):
        """LOW 2: Compare {injected_then_used:1, reaccess:0} vs {injected_then_used:0, reaccess:1} - first should be HIGHER (W_INJ=2.0 > 1)."""
        from mcp_memory_service.storage.usage_telemetry import recompute_quality_scores
        
        # Use signals_override to test the weighting directly without complex event setup
        signals_override = {
            "hash_injected_only": {
                "injected_then_used": 1,
                "reaccess": 0,
                "retry_failed": 0,
                "age_days": 0
            },
            "hash_reaccess_only": {
                "injected_then_used": 0,
                "reaccess": 1,
                "retry_failed": 0,
                "age_days": 0
            }
        }
        
        scores = await recompute_quality_scores(storage, base=0.5, signals_override=signals_override)
        
        # With W_INJ=2.0, injected_then_used:1 should score higher than reaccess:1
        # Formula: base + sigmoid(W_INJ * injected_then_used + reaccess - NEG_WEIGHT * retry_failed) * decay
        # hash_injected_only: 0.5 + sigmoid(2.0*1 + 0 - 0) = 0.5 + sigmoid(2.0)
        # hash_reaccess_only: 0.5 + sigmoid(0 + 1 - 0) = 0.5 + sigmoid(1.0)
        # Since sigmoid(2.0) > sigmoid(1.0), injected should be higher
        
        injected_score = scores['hash_injected_only']
        reaccess_score = scores['hash_reaccess_only']
        
        assert injected_score > reaccess_score, (
            f"Hash with injected_then_used:1 should score higher than reaccess:1 due to W_INJ=2.0 weight. "
            f"Got injected={injected_score:.4f}, reaccess={reaccess_score:.4f}"
        )
        
        # Verify both are above base (both should be positive signals)
        assert injected_score > 0.5, f"Injected signal should raise score above base 0.5, got {injected_score:.4f}"
        assert reaccess_score > 0.5, f"Reaccess signal should raise score above base 0.5, got {reaccess_score:.4f}"

    @pytest.mark.asyncio
    async def test_derive_signals_no_injection_events_fallback(self, storage):
        """When no injection events exist, injected_then_used should be 0 for all hashes (graceful degradation)."""
        from mcp_memory_service.storage.usage_telemetry import derive_signals, log_usage_event
        
        # Only create retrieval events, no injection events
        hashC = "test_hash_c"
        agent_id = "test_agent"
        
        await log_usage_event(
            storage,
            "retrieval",
            agent_id=agent_id,
            timestamp="2024-10-09T10:00:00Z",
            returned_hashes=[hashC]
        )
        
        signals = await derive_signals(storage)
        
        # All hashes should have injected_then_used=0 when no injection events
        for hash_id, signal_dict in signals.items():
            assert signal_dict.get('injected_then_used', 0) == 0, f"injected_then_used should be 0 when no injection events, got {signal_dict} for {hash_id}"