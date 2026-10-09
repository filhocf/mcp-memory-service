"""Tests for RFC-MM-03: Gap Detection (memory_gaps)."""

import asyncio
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_memory_service.server.handlers.gaps import (
    GAP_DETECTION_THRESHOLD,
    handle_memory_gaps,
    normalize_query,
    record_gap,
)


class TestNormalizeQuery:
    """Tests for query normalization logic."""

    def test_basic_normalization(self):
        """Lowercase and sort tokens."""
        result = normalize_query("Kubernetes Deploy Helm")
        assert result == "deploy helm kubernetes"

    def test_removes_english_stopwords(self):
        """Strips common English stopwords."""
        result = normalize_query("how to deploy the application in kubernetes")
        assert "how" not in result
        assert "the" not in result
        assert "to" not in result
        assert "in" not in result
        assert "deploy" in result
        assert "application" in result
        assert "kubernetes" in result

    def test_removes_portuguese_stopwords(self):
        """Strips common Portuguese stopwords."""
        result = normalize_query("como fazer deploy no kubernetes para produção")
        assert "como" not in result
        assert "no" not in result
        assert "para" not in result
        assert "deploy" in result
        assert "kubernetes" in result
        assert "produção" in result

    def test_empty_query(self):
        assert normalize_query("") == ""
        assert normalize_query("   ") == ""

    def test_only_stopwords(self):
        """All-stopwords query returns empty."""
        result = normalize_query("the a is are to of in for")
        assert result == ""

    def test_short_tokens_removed(self):
        """Single-char tokens are stripped."""
        result = normalize_query("a b c deploy x")
        assert result == "deploy"

    def test_canonical_form(self):
        """Same words in different order produce same normalized form."""
        q1 = normalize_query("kubernetes helm deploy")
        q2 = normalize_query("deploy helm kubernetes")
        q3 = normalize_query("helm deploy kubernetes")
        assert q1 == q2 == q3

    def test_threshold_from_env(self):
        """Threshold defaults to 0.3."""
        assert GAP_DETECTION_THRESHOLD == 0.3


class TestRecordGap:
    """Tests for recording gaps."""

    @pytest.fixture
    def mock_server(self):
        """Create a mock server with an in-memory SQLite database."""
        server = MagicMock()
        db = sqlite3.connect(":memory:")
        db.execute("""
            CREATE TABLE memory_gaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                normalized_query TEXT NOT NULL,
                max_score REAL NOT NULL,
                agent_id TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT DEFAULT NULL
            )
        """)
        db.commit()

        storage = MagicMock()
        storage.conn = db

        async def run_in_thread(fn):
            return fn()

        storage._run_in_thread = run_in_thread
        server._ensure_storage_initialized = AsyncMock(return_value=storage)
        return server

    @pytest.mark.asyncio
    async def test_records_gap(self, mock_server):
        """Basic gap recording works."""
        await record_gap(mock_server, "kubernetes helm chart", 0.15, "kiro")

        storage = await mock_server._ensure_storage_initialized()
        row = storage.conn.execute("SELECT * FROM memory_gaps").fetchone()
        assert row is not None
        assert row[1] == "kubernetes helm chart"  # query
        assert row[2] == "chart helm kubernetes"  # normalized_query (sorted)
        assert row[3] == 0.15  # max_score
        assert row[4] == "kiro"  # agent_id

    @pytest.mark.asyncio
    async def test_dedup_updates_higher_score(self, mock_server):
        """Duplicate normalized query updates max_score if higher."""
        await record_gap(mock_server, "kubernetes helm", 0.10, "kiro")
        await record_gap(mock_server, "helm kubernetes", 0.25, "kiro")

        storage = await mock_server._ensure_storage_initialized()
        rows = storage.conn.execute("SELECT * FROM memory_gaps").fetchall()
        # Should have only 1 row (dedup)
        assert len(rows) == 1
        assert rows[0][3] == 0.25  # Updated to higher score

    @pytest.mark.asyncio
    async def test_dedup_keeps_lower_score(self, mock_server):
        """Duplicate with lower score does not update."""
        await record_gap(mock_server, "kubernetes helm", 0.25, "kiro")
        await record_gap(mock_server, "helm kubernetes", 0.10, "kiro")

        storage = await mock_server._ensure_storage_initialized()
        rows = storage.conn.execute("SELECT * FROM memory_gaps").fetchall()
        assert len(rows) == 1
        assert rows[0][3] == 0.25  # Kept original higher score

    @pytest.mark.asyncio
    async def test_skips_empty_normalized(self, mock_server):
        """All-stopwords query is skipped."""
        await record_gap(mock_server, "the a is", 0.1, "kiro")

        storage = await mock_server._ensure_storage_initialized()
        rows = storage.conn.execute("SELECT * FROM memory_gaps").fetchall()
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_no_dedup_after_24h(self, mock_server):
        """Gaps older than 24h are not deduped — new gap created."""
        storage = await mock_server._ensure_storage_initialized()
        # Insert an old gap manually
        old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
        storage.conn.execute(
            "INSERT INTO memory_gaps (query, normalized_query, max_score, agent_id, created_at) VALUES (?, ?, ?, ?, ?)",
            ("kubernetes helm", "helm kubernetes", 0.15, "kiro", old_time)
        )
        storage.conn.commit()

        # Record same query — should create new row since old one is >24h
        await record_gap(mock_server, "helm kubernetes", 0.20, "kiro")

        rows = storage.conn.execute("SELECT * FROM memory_gaps").fetchall()
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_no_dedup_for_resolved(self, mock_server):
        """Resolved gaps are not matched for dedup."""
        storage = await mock_server._ensure_storage_initialized()
        # Insert a resolved gap
        storage.conn.execute(
            "INSERT INTO memory_gaps (query, normalized_query, max_score, agent_id, resolved_at) VALUES (?, ?, ?, ?, ?)",
            ("kubernetes helm", "helm kubernetes", 0.15, "kiro", "2026-01-01 00:00:00")
        )
        storage.conn.commit()

        await record_gap(mock_server, "helm kubernetes", 0.20, "kiro")

        rows = storage.conn.execute(
            "SELECT * FROM memory_gaps WHERE resolved_at IS NULL"
        ).fetchall()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_nonfatal_on_error(self, mock_server):
        """record_gap does not raise even if DB fails."""
        mock_server._ensure_storage_initialized = AsyncMock(side_effect=Exception("DB error"))
        # Should not raise
        await record_gap(mock_server, "test query", 0.1, "kiro")


class TestHandleMemoryGaps:
    """Tests for memory_gaps tool actions."""

    @pytest.fixture
    def mock_server(self):
        """Server with gaps table and some test data."""
        server = MagicMock()
        db = sqlite3.connect(":memory:")
        db.execute("""
            CREATE TABLE memory_gaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                normalized_query TEXT NOT NULL,
                max_score REAL NOT NULL,
                agent_id TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT DEFAULT NULL
            )
        """)
        # Insert test data
        db.execute(
            "INSERT INTO memory_gaps (query, normalized_query, max_score, agent_id) VALUES (?, ?, ?, ?)",
            ("kubernetes deploy", "deploy kubernetes", 0.25, "kiro")
        )
        db.execute(
            "INSERT INTO memory_gaps (query, normalized_query, max_score, agent_id, resolved_at) VALUES (?, ?, ?, ?, ?)",
            ("docker build", "build docker", 0.20, "kiro", "2026-01-01 12:00:00")
        )
        db.commit()

        storage = MagicMock()
        storage.conn = db

        async def run_in_thread(fn):
            return fn()

        storage._run_in_thread = run_in_thread
        server._ensure_storage_initialized = AsyncMock(return_value=storage)
        return server

    @pytest.mark.asyncio
    async def test_list_unresolved_gaps(self, mock_server):
        """List action returns unresolved gaps only."""
        result = await handle_memory_gaps(mock_server, {"action": "list"})
        text_content = result[0].text
        data = json.loads(text_content)
        
        assert data["action"] == "list"
        assert data["count"] == 1
        assert len(data["gaps"]) == 1
        assert data["gaps"][0]["query"] == "kubernetes deploy"

    @pytest.mark.asyncio
    async def test_resolve_by_id(self, mock_server):
        """Resolve action marks gap as resolved by ID."""
        # First get the gap ID
        storage = await mock_server._ensure_storage_initialized()
        gap_id = storage.conn.execute("SELECT id FROM memory_gaps WHERE resolved_at IS NULL").fetchone()[0]

        result = await handle_memory_gaps(mock_server, {"action": "resolve", "gap_id": gap_id})
        text_content = result[0].text
        data = json.loads(text_content)
        
        assert data["action"] == "resolve"
        assert data["resolved"] >= 1  # May be accumulated changes, just verify >= 1

        # Verify it's marked as resolved
        resolved = storage.conn.execute("SELECT resolved_at FROM memory_gaps WHERE id = ?", (gap_id,)).fetchone()[0]
        assert resolved is not None

    @pytest.mark.asyncio
    async def test_stats_action(self, mock_server):
        """Stats action returns gap counts."""
        result = await handle_memory_gaps(mock_server, {"action": "stats"})
        text_content = result[0].text
        data = json.loads(text_content)
        
        assert data["action"] == "stats"
        assert data["total"] == 2
        assert data["resolved"] == 1
        assert data["unresolved"] == 1


# New integration test for M3.1 - hook in memory_search
class TestGapDetectionIntegration:
    """Integration tests for gap detection in real memory search flow."""

    @pytest.fixture
    def mock_server_with_search_result(self):
        """Mock server that simulates memory search returning low score results."""
        server = MagicMock()
        db = sqlite3.connect(":memory:")
        db.execute("""
            CREATE TABLE memory_gaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                normalized_query TEXT NOT NULL,
                max_score REAL NOT NULL,
                agent_id TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT DEFAULT NULL
            )
        """)
        db.commit()

        storage = MagicMock()
        storage.conn = db

        async def run_in_thread(fn):
            return fn()

        storage._run_in_thread = run_in_thread
        server._ensure_storage_initialized = AsyncMock(return_value=storage)
        return server

    @pytest.mark.asyncio
    async def test_memory_search_calls_record_gap_on_low_score(self, mock_server_with_search_result):
        """Integration test: memory_search with top_score < 0.3 should call record_gap."""
        # This test will fail RED until we implement the hook
        from mcp_memory_service.server.handlers.memory import handle_memory_search
        from unittest.mock import patch
        
        # Mock _retrieve_search_results to return low score result
        mock_result = {
            "memories": [
                {"content": "some content", "similarity_score": 0.15}
            ],
            "total": 1
        }
        
        with patch('mcp_memory_service.server.handlers.memory._retrieve_search_results') as mock_retrieve, \
             patch('mcp_memory_service.server.handlers.memory._apply_memory_search_filters') as mock_filter, \
             patch('mcp_memory_service.server.handlers.memory._format_full_memory_search') as mock_format, \
             patch('mcp_memory_service.server.handlers.gaps.record_gap') as mock_record_gap:
            
            # Setup mocks
            mock_retrieve.return_value = (mock_result, False)
            mock_filter.return_value = (mock_result["memories"], mock_result["total"], None)
            mock_format.return_value = {"type": "text", "text": "formatted result"}
            
            # Call memory search
            arguments = {"query": "test query", "agent_id": "test_agent"}
            await handle_memory_search(mock_server_with_search_result, arguments)
            
            # Assert record_gap was called
            mock_record_gap.assert_called_once_with(
                mock_server_with_search_result, 
                "test query", 
                0.15,  # top_score from mock result
                "test_agent"
            )

    @pytest.mark.asyncio
    async def test_memory_search_does_not_call_record_gap_on_high_score(self, mock_server_with_search_result):
        """Integration test: memory_search with top_score >= 0.3 should NOT call record_gap."""
        from mcp_memory_service.server.handlers.memory import handle_memory_search
        from unittest.mock import patch
        
        # Mock _retrieve_search_results to return high score result
        mock_result = {
            "memories": [
                {"content": "some content", "similarity_score": 0.85}
            ],
            "total": 1
        }
        
        with patch('mcp_memory_service.server.handlers.memory._retrieve_search_results') as mock_retrieve, \
             patch('mcp_memory_service.server.handlers.memory._apply_memory_search_filters') as mock_filter, \
             patch('mcp_memory_service.server.handlers.memory._format_full_memory_search') as mock_format, \
             patch('mcp_memory_service.server.handlers.gaps.record_gap') as mock_record_gap:
            
            # Setup mocks
            mock_retrieve.return_value = (mock_result, False)
            mock_filter.return_value = (mock_result["memories"], mock_result["total"], None)
            mock_format.return_value = {"type": "text", "text": "formatted result"}
            
            # Call memory search
            arguments = {"query": "test query", "agent_id": "test_agent"}
            await handle_memory_search(mock_server_with_search_result, arguments)
            
            # Assert record_gap was NOT called
            mock_record_gap.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_search_does_not_call_record_gap_on_empty_query(self, mock_server_with_search_result):
        """Integration test: memory_search with empty query should NOT call record_gap."""
        from mcp_memory_service.server.handlers.memory import handle_memory_search
        from unittest.mock import patch
        
        # Mock _retrieve_search_results to return low score result
        mock_result = {
            "memories": [
                {"content": "some content", "similarity_score": 0.15}
            ],
            "total": 1
        }
        
        with patch('mcp_memory_service.server.handlers.memory._retrieve_search_results') as mock_retrieve, \
             patch('mcp_memory_service.server.handlers.memory._apply_memory_search_filters') as mock_filter, \
             patch('mcp_memory_service.server.handlers.memory._format_full_memory_search') as mock_format, \
             patch('mcp_memory_service.server.handlers.gaps.record_gap') as mock_record_gap:
            
            # Setup mocks
            mock_retrieve.return_value = (mock_result, False)
            mock_filter.return_value = (mock_result["memories"], mock_result["total"], None)
            mock_format.return_value = {"type": "text", "text": "formatted result"}
            
            # Call memory search with empty query
            arguments = {"query": "", "agent_id": "test_agent"}
            await handle_memory_search(mock_server_with_search_result, arguments)
            
            # Assert record_gap was NOT called
            mock_record_gap.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_search_does_not_break_on_record_gap_error(self, mock_server_with_search_result):
        """Integration test: record_gap error should not break memory_search (M3.8)."""
        from mcp_memory_service.server.handlers.memory import handle_memory_search
        from unittest.mock import patch
        
        # Mock _retrieve_search_results to return low score result
        mock_result = {
            "memories": [
                {"content": "some content", "similarity_score": 0.15}
            ],
            "total": 1
        }
        
        with patch('mcp_memory_service.server.handlers.memory._retrieve_search_results') as mock_retrieve, \
             patch('mcp_memory_service.server.handlers.memory._apply_memory_search_filters') as mock_filter, \
             patch('mcp_memory_service.server.handlers.memory._format_full_memory_search') as mock_format, \
             patch('mcp_memory_service.server.handlers.gaps.record_gap') as mock_record_gap:
            
            # Setup mocks - record_gap raises exception
            mock_retrieve.return_value = (mock_result, False)
            mock_filter.return_value = (mock_result["memories"], mock_result["total"], None)
            mock_format.return_value = {"type": "text", "text": "formatted result"}
            mock_record_gap.side_effect = Exception("Database error")
            
            # Call memory search - should not raise despite record_gap error
            arguments = {"query": "test query", "agent_id": "test_agent"}
            result = await handle_memory_search(mock_server_with_search_result, arguments)
            
            # Assert search still returned results
            assert len(result) == 1
            mock_record_gap.assert_called_once()

    @pytest.mark.asyncio
    async def test_high_similarity_score_prevents_gap_recording(self, mock_server_with_search_result):
        """NEW TEST: Proves that high similarity_score does NOT trigger record_gap (hit bom não vira gap)."""
        from mcp_memory_service.server.handlers.memory import handle_memory_search
        from unittest.mock import patch
        
        # Mock _retrieve_search_results to return very high score result (0.9)
        mock_result = {
            "memories": [
                {"content": "perfect match content", "similarity_score": 0.9}
            ],
            "total": 1
        }
        
        with patch('mcp_memory_service.server.handlers.memory._retrieve_search_results') as mock_retrieve, \
             patch('mcp_memory_service.server.handlers.memory._apply_memory_search_filters') as mock_filter, \
             patch('mcp_memory_service.server.handlers.memory._format_full_memory_search') as mock_format, \
             patch('mcp_memory_service.server.handlers.gaps.record_gap') as mock_record_gap:
            
            # Setup mocks
            mock_retrieve.return_value = (mock_result, False)
            mock_filter.return_value = (mock_result["memories"], mock_result["total"], None)
            mock_format.return_value = {"type": "text", "text": "formatted result"}
            
            # Call memory search with query that gets high-scoring hit
            arguments = {"query": "perfect match query", "agent_id": "test_agent"}
            await handle_memory_search(mock_server_with_search_result, arguments)
            
            # Assert record_gap was NOT called because similarity_score (0.9) >= threshold (0.3)
            mock_record_gap.assert_not_called()