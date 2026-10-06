"""
RED tests for quality recompute scheduling feature.

Tests the scheduled quality recomputation functionality:
- A) persist_quality_scores function in usage_telemetry.py
- B) ConsolidationScheduler integration for quality recomputation jobs

These tests are designed to FAIL until the code is implemented.
"""

import pytest
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch, Mock

from mcp_memory_service.consolidation.scheduler import ConsolidationScheduler


def _mock_scheduler(env, monkeypatch):
    """Create a scheduler with mocked storage for testing."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    consolidator = MagicMock()
    consolidator.storage = MagicMock()
    scheduler = ConsolidationScheduler(
        consolidator=consolidator,
        schedule_config={},
        enabled=True,
    )
    return scheduler


class TestPersistQualityScores:
    """Tests for the persist_quality_scores function."""

    def test_persist_quality_scores_dry_run_default(self):
        """A1. dry_run=True (DEFAULT): does not call storage.update_memory_metadata."""
        async def _test():
            # Import will fail because persist_quality_scores doesn't exist yet
            from mcp_memory_service.storage.usage_telemetry import persist_quality_scores
            
            # Create a mock storage
            mock_storage = AsyncMock()
            
            # Call persist_quality_scores - should default to dry_run=True
            result = await persist_quality_scores(mock_storage)
            
            # Should NOT have called update_memory_metadata
            mock_storage.update_memory_metadata.assert_not_called()
            
            # Should return dry_run report
            assert result['dry_run'] is True
            assert 'total' in result
            assert 'would_update' in result
            assert 'raised_count' in result
            assert 'lowered_count' in result
            assert 'neutral_count' in result
            assert 'min' in result
            assert 'max' in result
        
        # Run the async test
        asyncio.run(_test())

    def test_persist_quality_scores_dry_run_false_updates_storage(self):
        """A2. dry_run=False: calls update_memory_metadata once per hash with computed_quality."""
        async def _test():
            from mcp_memory_service.storage.usage_telemetry import persist_quality_scores
            
            mock_storage = AsyncMock()
            # Mock get_by_hash to return Memory objects without metadata (no user_rating)
            mock_storage.get_by_hash.return_value = None
            
            # Use deterministic signals_override
            signals_override = {
                "hashA": {"reaccess": 3, "retry_failed": 0, "age_days": 0},  # Should result in score > 0.5
                "hashB": {"reaccess": 0, "retry_failed": 2, "age_days": 0},  # Should result in score < 0.5
            }
            
            result = await persist_quality_scores(
                mock_storage, 
                dry_run=False, 
                signals_override=signals_override
            )
            
            # Should have called update_memory_metadata twice
            assert mock_storage.update_memory_metadata.call_count == 2
            
            # Check calls for hashA (should be > 0.5)
            calls = mock_storage.update_memory_metadata.call_args_list
            hashA_call = next(call for call in calls if call[0][0] == "hashA")
            hashA_quality = hashA_call[0][1]["computed_quality"]
            assert hashA_quality > 0.5
            
            # Check calls for hashB (should be < 0.5)  
            hashB_call = next(call for call in calls if call[0][0] == "hashB")
            hashB_quality = hashB_call[0][1]["computed_quality"]
            assert hashB_quality < 0.5
            
            # Should return non-dry-run report
            assert result['dry_run'] is False
            assert 'updated' in result
        
        asyncio.run(_test())

    def test_persist_quality_scores_preserves_user_rating(self):
        """A3. dry_run=False preserves rating: effective_quality(computed, user_rating) when user_rating exists."""
        async def _test():
            from mcp_memory_service.storage.usage_telemetry import persist_quality_scores
            
            mock_storage = AsyncMock()
            
            # Create a Memory mock with metadata containing user_rating
            memory_mock = MagicMock()
            memory_mock.metadata = {"user_rating": 1}  # thumbs up
            
            # Mock get_by_hash to return memory with metadata for our test hash
            async def mock_get_by_hash(content_hash):
                if content_hash == "hashWithRating":
                    return memory_mock
                return None
            
            mock_storage.get_by_hash = mock_get_by_hash
            
            # Mock recompute_quality_scores to return a computed value
            with patch('mcp_memory_service.storage.usage_telemetry.recompute_quality_scores') as mock_recompute:
                mock_recompute.return_value = {"hashWithRating": 0.7}  # computed quality
                
                result = await persist_quality_scores(mock_storage, dry_run=False)
            
            # Should have called update_memory_metadata with effective_quality result
            mock_storage.update_memory_metadata.assert_called_once()
            call_args = mock_storage.update_memory_metadata.call_args
            
            # With user_rating=1, effective_quality should return 0.9 (not the computed 0.7)
            assert call_args[0][1]["quality_score"] == 0.9
        
        asyncio.run(_test())

    def test_persist_quality_scores_best_effort_error_handling(self):
        """A4. best-effort: if update_memory_metadata raises for one hash, continues with others."""
        async def _test():
            from mcp_memory_service.storage.usage_telemetry import persist_quality_scores
            
            mock_storage = AsyncMock()
            
            # Mock get_by_hash to return None (no metadata/user_rating)
            mock_storage.get_by_hash.return_value = None
            
            # Make update_memory_metadata fail for one hash but succeed for another
            def update_side_effect(content_hash, updates, preserve_timestamps=True):
                if content_hash == "failing_hash":
                    raise RuntimeError("Storage error for this hash")
                return True, "success"
            
            mock_storage.update_memory_metadata.side_effect = update_side_effect
            
            # Mock recompute to return multiple hashes
            with patch('mcp_memory_service.storage.usage_telemetry.recompute_quality_scores') as mock_recompute:
                mock_recompute.return_value = {
                    "failing_hash": 0.6,
                    "working_hash": 0.7
                }
                
                # Should not raise, should handle errors gracefully
                result = await persist_quality_scores(mock_storage, dry_run=False)
            
            # Should have attempted both updates
            assert mock_storage.update_memory_metadata.call_count == 2
            
            # Should report the error in results
            assert 'errors' in result or 'failed_count' in result
        
        asyncio.run(_test())

    def test_persist_quality_scores_empty_metadata_no_overwrite(self):
        """A5. get_by_hash->None or metadata={} does NOT overwrite: quality_score = effective_quality(computed, None)."""
        async def _test():
            from mcp_memory_service.storage.usage_telemetry import persist_quality_scores
            
            mock_storage = AsyncMock()
            
            # Test case 1: get_by_hash returns None
            mock_storage.get_by_hash.return_value = None
            
            with patch('mcp_memory_service.storage.usage_telemetry.recompute_quality_scores') as mock_recompute:
                mock_recompute.return_value = {"hash_no_memory": 0.6}
                
                result = await persist_quality_scores(mock_storage, dry_run=False)
            
            # Should have called update_memory_metadata with quality_score = effective_quality(0.6, None) = 0.6
            call_args = mock_storage.update_memory_metadata.call_args
            assert call_args[0][1]["quality_score"] == 0.6
            
            # Test case 2: get_by_hash returns memory with empty metadata
            memory_mock = MagicMock()
            memory_mock.metadata = {}  # empty metadata, no user_rating
            mock_storage.get_by_hash.return_value = memory_mock
            mock_storage.update_memory_metadata.reset_mock()
            
            with patch('mcp_memory_service.storage.usage_telemetry.recompute_quality_scores') as mock_recompute:
                mock_recompute.return_value = {"hash_empty_metadata": 0.7}
                
                result = await persist_quality_scores(mock_storage, dry_run=False)
            
            # Should have called update_memory_metadata with quality_score = effective_quality(0.7, None) = 0.7
            call_args = mock_storage.update_memory_metadata.call_args
            assert call_args[0][1]["quality_score"] == 0.7
        
        asyncio.run(_test())

    def test_persist_quality_scores_empty_dict_no_exception(self):
        """A6. Empty dict (0 hashes): persist_quality_scores with signals_override={} returns proper report."""
        async def _test():
            from mcp_memory_service.storage.usage_telemetry import persist_quality_scores
            
            mock_storage = AsyncMock()
            
            # Test dry_run=True with empty signals_override
            result = await persist_quality_scores(mock_storage, dry_run=True, signals_override={})
            
            expected_dry_run = {
                'dry_run': True,
                'total': 0,
                'would_update': 0,
                'raised_count': 0,
                'lowered_count': 0,
                'neutral_count': 0,
                'min': None,
                'max': None,
            }
            
            for key, expected_value in expected_dry_run.items():
                assert result[key] == expected_value, f"dry_run=True: {key} = {result[key]}, expected {expected_value}"
            
            # Test dry_run=False with empty signals_override
            result = await persist_quality_scores(mock_storage, dry_run=False, signals_override={})
            
            expected_wet_run = {
                'dry_run': False,
                'total': 0,
                'updated': 0,
                'raised_count': 0,
                'lowered_count': 0,
                'neutral_count': 0,
                'min': None,
                'max': None,
                'errors': 0
            }
            
            for key, expected_value in expected_wet_run.items():
                assert result[key] == expected_value, f"dry_run=False: {key} = {result[key]}, expected {expected_value}"
            
            # Should not have called any storage methods
            mock_storage.update_memory_metadata.assert_not_called()
        
        asyncio.run(_test())


class TestQualityRecomputeScheduling:
    """Tests for quality recomputation scheduling in ConsolidationScheduler."""

    def test_schedule_quality_recompute_job_exists(self):
        """B1. _schedule_quality_recompute_job() exists."""
        try:
            pytest.importorskip('apscheduler')
        except pytest.skip.Exception:
            pytest.skip("APScheduler not available")
        
        scheduler = ConsolidationScheduler(MagicMock(), {}, enabled=True)
        
        if scheduler.scheduler is None:
            pytest.skip("Scheduler is None (APScheduler not available)")
        
        # Should have the method
        assert hasattr(scheduler, '_schedule_quality_recompute_job')
        
        # Should be callable
        scheduler._schedule_quality_recompute_job()

    def test_quality_recompute_job_not_scheduled_by_default(self, monkeypatch):
        """B1. With MCP_QUALITY_RECOMPUTE_SCHEDULE unset/''/disabled, no job is scheduled."""
        try:
            pytest.importorskip('apscheduler')
        except pytest.skip.Exception:
            pytest.skip("APScheduler not available")
        
        # Test unset
        monkeypatch.delenv("MCP_QUALITY_RECOMPUTE_SCHEDULE", raising=False)
        scheduler = _mock_scheduler({}, monkeypatch)
        
        if scheduler.scheduler is None:
            pytest.skip("Scheduler is None (APScheduler not available)")
        
        scheduler._schedule_quality_recompute_job()
        
        # Should not have scheduled the job
        job = scheduler.scheduler.get_job("quality_recompute")
        assert job is None
        
        # Test empty string
        scheduler = _mock_scheduler({"MCP_QUALITY_RECOMPUTE_SCHEDULE": ""}, monkeypatch)
        scheduler._schedule_quality_recompute_job()
        job = scheduler.scheduler.get_job("quality_recompute")
        assert job is None
        
        # Test disabled
        scheduler = _mock_scheduler({"MCP_QUALITY_RECOMPUTE_SCHEDULE": "disabled"}, monkeypatch)
        scheduler._schedule_quality_recompute_job()
        job = scheduler.scheduler.get_job("quality_recompute")
        assert job is None

    def test_quality_recompute_job_scheduled_with_interval(self, monkeypatch):
        """B2. With MCP_QUALITY_RECOMPUTE_SCHEDULE='6h', schedules job with IntervalTrigger ~21600s."""
        try:
            pytest.importorskip('apscheduler')
        except pytest.skip.Exception:
            pytest.skip("APScheduler not available")
        
        scheduler = _mock_scheduler({"MCP_QUALITY_RECOMPUTE_SCHEDULE": "6h"}, monkeypatch)
        
        if scheduler.scheduler is None:
            pytest.skip("Scheduler is None (APScheduler not available)")
        
        scheduler._schedule_quality_recompute_job()
        
        # Should have scheduled the job
        job = scheduler.scheduler.get_job("quality_recompute")
        assert job is not None
        assert job.id == "quality_recompute"
        
        # Should use IntervalTrigger with correct interval
        from apscheduler.triggers.interval import IntervalTrigger
        assert isinstance(job.trigger, IntervalTrigger)
        assert job.trigger.interval.total_seconds() == 21600  # 6 hours

    def test_run_quality_recompute_exists_and_defaults_to_dry_run(self, monkeypatch):
        """B3. _run_quality_recompute() exists and by default runs in dry_run mode."""
        async def _test():
            scheduler = _mock_scheduler({}, monkeypatch)
            
            # Should have the method
            assert hasattr(scheduler, '_run_quality_recompute')
            
            # Mock persist_quality_scores to capture how it's called
            with patch('mcp_memory_service.storage.usage_telemetry.persist_quality_scores') as mock_persist:
                mock_persist.return_value = {"dry_run": True, "total": 0}
                
                await scheduler._run_quality_recompute()
            
            # Should have called persist_quality_scores with dry_run=True (default)
            mock_persist.assert_called_once()
            call_kwargs = mock_persist.call_args[1]
            assert call_kwargs.get('dry_run', True) is True
        
        asyncio.run(_test())

    def test_run_quality_recompute_respects_dry_run_env(self, monkeypatch):
        """B3. _run_quality_recompute reads MCP_QUALITY_RECOMPUTE_DRY_RUN env var."""
        async def _test():
            # Test dry_run=false from env
            scheduler = _mock_scheduler({"MCP_QUALITY_RECOMPUTE_DRY_RUN": "false"}, monkeypatch)
            
            with patch('mcp_memory_service.storage.usage_telemetry.persist_quality_scores') as mock_persist:
                mock_persist.return_value = {"dry_run": False, "updated": 0}
                
                await scheduler._run_quality_recompute()
            
            # Should have called persist_quality_scores with dry_run=False
            call_kwargs = mock_persist.call_args[1]
            assert call_kwargs.get('dry_run') is False
        
        asyncio.run(_test())

    def test_run_quality_recompute_never_reraises(self, monkeypatch):
        """B4. _run_quality_recompute never re-raises exceptions."""
        async def _test():
            scheduler = _mock_scheduler({}, monkeypatch)
            
            # Test storage being None
            scheduler.consolidator.storage = None
            await scheduler._run_quality_recompute()  # Should not raise
            
            # Test persist_quality_scores raising
            scheduler.consolidator.storage = MagicMock()
            with patch('mcp_memory_service.storage.usage_telemetry.persist_quality_scores', 
                      side_effect=RuntimeError("Storage failure")):
                await scheduler._run_quality_recompute()  # Should not raise
        
        asyncio.run(_test())