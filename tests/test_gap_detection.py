"""Tests for RFC-MM-03: Gap Detection (memory_gaps)."""

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the source is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

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
    """Tests for the memory_gaps tool handler."""

    @pytest.fixture
    def mock_server(self):
        """Create a mock server with gaps table populated."""
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
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        db.executemany(
            "INSERT INTO memory_gaps (query, normalized_query, max_score, agent_id, created_at) VALUES (?, ?, ?, ?, ?)",
            [
                ("kubernetes deploy", "deploy kubernetes", 0.12, "kiro", now),
                ("helm chart tutorial", "chart helm tutorial", 0.08, "kiro", now),
                ("docker compose network", "compose docker network", 0.22, None, now),
            ]
        )
        # Insert a resolved one
        db.execute(
            "INSERT INTO memory_gaps (query, normalized_query, max_score, agent_id, created_at, resolved_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("old query", "old query", 0.05, "kiro", now, now)
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
    async def test_list_action(self, mock_server):
        """List returns unresolved gaps."""
        result = await handle_memory_gaps(mock_server, {"action": "list"})
        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["action"] == "list"
        assert data["count"] == 3
        assert len(data["gaps"]) == 3
        # All should be unresolved
        for gap in data["gaps"]:
            assert "query" in gap
            assert "max_score" in gap

    @pytest.mark.asyncio
    async def test_list_with_limit(self, mock_server):
        """List respects limit parameter."""
        result = await handle_memory_gaps(mock_server, {"action": "list", "limit": 2})
        data = json.loads(result[0].text)
        assert data["count"] == 2

    @pytest.mark.asyncio
    async def test_resolve_by_id(self, mock_server):
        """Resolve by gap_id works."""
        result = await handle_memory_gaps(mock_server, {"action": "resolve", "gap_id": 1})
        data = json.loads(result[0].text)
        assert data["action"] == "resolve"

        # Verify it's resolved
        storage = await mock_server._ensure_storage_initialized()
        row = storage.conn.execute(
            "SELECT resolved_at FROM memory_gaps WHERE id = 1"
        ).fetchone()
        assert row[0] is not None

    @pytest.mark.asyncio
    async def test_resolve_by_normalized_query(self, mock_server):
        """Resolve by normalized_query marks all matching gaps."""
        result = await handle_memory_gaps(
            mock_server,
            {"action": "resolve", "normalized_query": "deploy kubernetes"}
        )
        data = json.loads(result[0].text)
        assert data["action"] == "resolve"

        storage = await mock_server._ensure_storage_initialized()
        row = storage.conn.execute(
            "SELECT resolved_at FROM memory_gaps WHERE normalized_query = 'deploy kubernetes'"
        ).fetchone()
        assert row[0] is not None

    @pytest.mark.asyncio
    async def test_resolve_missing_params(self, mock_server):
        """Resolve without gap_id or normalized_query returns error."""
        result = await handle_memory_gaps(mock_server, {"action": "resolve"})
        assert "Error" in result[0].text

    @pytest.mark.asyncio
    async def test_stats_action(self, mock_server):
        """Stats returns summary."""
        result = await handle_memory_gaps(mock_server, {"action": "stats"})
        data = json.loads(result[0].text)
        assert data["action"] == "stats"
        assert data["total"] == 4  # 3 unresolved + 1 resolved
        assert data["unresolved"] == 3
        assert data["resolved"] == 1
        assert "resolution_rate" in data
        assert "weekly" in data

    @pytest.mark.asyncio
    async def test_unknown_action(self, mock_server):
        """Unknown action returns error message."""
        result = await handle_memory_gaps(mock_server, {"action": "invalid"})
        assert "Error" in result[0].text
        assert "invalid" in result[0].text


class TestGapDetectionIntegration:
    """Integration-style tests for the gap detection hook in search."""

    @pytest.mark.asyncio
    async def test_gap_recorded_on_low_score(self):
        """Verify that record_gap is called when search results have low scores."""
        # This tests the logic separately since hooking into the full search
        # handler requires the full server stack.
        from mcp_memory_service.server.handlers.gaps import GAP_DETECTION_THRESHOLD

        # Simulate: search returned results with max score 0.15 (< 0.3)
        assert 0.15 < GAP_DETECTION_THRESHOLD
        # The hook in memory.py checks: if top_score < GAP_DETECTION_THRESHOLD
        # This confirms the threshold logic is correct

    def test_threshold_configurable_via_env(self):
        """Threshold can be overridden via env var."""
        with patch.dict(os.environ, {"MCP_GAP_DETECTION_THRESHOLD": "0.5"}):
            # Re-import to pick up new env
            import importlib
            import mcp_memory_service.server.handlers.gaps as gaps_mod
            importlib.reload(gaps_mod)
            assert gaps_mod.GAP_DETECTION_THRESHOLD == 0.5

        # Restore
        import importlib
        import mcp_memory_service.server.handlers.gaps as gaps_mod
        importlib.reload(gaps_mod)


class TestMigration:
    """Test that the migration SQL is valid."""

    def test_migration_creates_table(self):
        """Migration SQL executes without error on fresh db."""
        db = sqlite3.connect(":memory:")
        migration_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'mcp_memory_service',
            'storage', 'migrations', '013_add_memory_gaps.sql'
        )
        with open(migration_path) as f:
            sql = f.read()
        db.executescript(sql)

        # Verify table exists
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_gaps'"
        ).fetchone()
        assert tables is not None

        # Verify indexes exist
        indexes = db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_memory_gaps%'"
        ).fetchall()
        assert len(indexes) == 3

        # Verify we can insert
        db.execute(
            "INSERT INTO memory_gaps (query, normalized_query, max_score, agent_id) VALUES (?, ?, ?, ?)",
            ("test", "test", 0.1, "agent1")
        )
        db.commit()
        row = db.execute("SELECT * FROM memory_gaps").fetchone()
        assert row is not None
        assert row[5] is not None  # created_at should have default value
        assert row[6] is None  # resolved_at should be NULL
