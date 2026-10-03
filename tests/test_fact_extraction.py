"""Tests for RFC-MM-02: Fact Extraction (batch, incremental)."""

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the source is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp_memory_service.extraction.facts import (
    BATCH_SIZE,
    MAX_CHUNKS_PER_RUN,
    extract_facts_batch,
    get_extraction_status,
    get_llm_config,
    get_pending_chunks,
    mark_processed,
    run_extraction,
    store_facts,
)


@pytest.fixture
def db():
    """Create an in-memory database with the required schema."""
    conn = sqlite3.connect(":memory:")
    # Create memories table
    conn.execute("""
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            content_hash TEXT UNIQUE NOT NULL,
            metadata TEXT,
            created_at REAL NOT NULL,
            facts_extracted_at TEXT DEFAULT NULL
        )
    """)
    # Create memory_graph table (as per migration 008 + 009)
    conn.execute("""
        CREATE TABLE memory_graph (
            source_hash TEXT NOT NULL,
            target_hash TEXT NOT NULL,
            similarity REAL NOT NULL,
            connection_types TEXT NOT NULL,
            relationship_type TEXT DEFAULT 'related',
            metadata TEXT,
            created_at REAL NOT NULL,
            PRIMARY KEY (source_hash, target_hash)
        )
    """)
    conn.commit()
    yield conn
    conn.close()


def _insert_memory(conn, content_hash, content, extracted=False):
    """Helper to insert a test memory."""
    now = datetime.now(timezone.utc).timestamp()
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if extracted else None
    conn.execute(
        "INSERT INTO memories (content, content_hash, metadata, created_at, facts_extracted_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (content, content_hash, json.dumps({"tags": "test"}), now, extracted_at),
    )
    conn.commit()


class TestGetPendingChunks:
    """Tests for get_pending_chunks."""

    def test_returns_unprocessed_only(self, db):
        """Only returns memories with facts_extracted_at IS NULL."""
        _insert_memory(db, "hash1", "Content one", extracted=False)
        _insert_memory(db, "hash2", "Content two", extracted=True)
        _insert_memory(db, "hash3", "Content three", extracted=False)

        pending = get_pending_chunks(db)
        hashes = [p["content_hash"] for p in pending]

        assert "hash1" in hashes
        assert "hash3" in hashes
        assert "hash2" not in hashes
        assert len(pending) == 2

    def test_returns_empty_when_all_processed(self, db):
        """Returns empty list when no pending chunks."""
        _insert_memory(db, "hash1", "Content one", extracted=True)
        _insert_memory(db, "hash2", "Content two", extracted=True)

        pending = get_pending_chunks(db)
        assert pending == []

    def test_respects_limit(self, db):
        """Respects the limit parameter."""
        for i in range(10):
            _insert_memory(db, f"hash{i}", f"Content {i}", extracted=False)

        pending = get_pending_chunks(db, limit=3)
        assert len(pending) == 3

    def test_returns_content_and_hash(self, db):
        """Returns both content_hash and content fields."""
        _insert_memory(db, "abc123", "Hello World", extracted=False)

        pending = get_pending_chunks(db)
        assert len(pending) == 1
        assert pending[0]["content_hash"] == "abc123"
        assert pending[0]["content"] == "Hello World"


class TestMarkProcessed:
    """Tests for mark_processed."""

    def test_sets_timestamp(self, db):
        """Sets facts_extracted_at to current time."""
        _insert_memory(db, "hash1", "Content", extracted=False)
        _insert_memory(db, "hash2", "Content 2", extracted=False)

        mark_processed(db, ["hash1"])

        # hash1 should now be processed
        row = db.execute(
            "SELECT facts_extracted_at FROM memories WHERE content_hash = 'hash1'"
        ).fetchone()
        assert row[0] is not None

        # hash2 should still be pending
        row = db.execute(
            "SELECT facts_extracted_at FROM memories WHERE content_hash = 'hash2'"
        ).fetchone()
        assert row[0] is None

    def test_not_returned_again(self, db):
        """Once marked, chunks are not returned by get_pending_chunks."""
        _insert_memory(db, "hash1", "Content", extracted=False)
        _insert_memory(db, "hash2", "Content 2", extracted=False)

        mark_processed(db, ["hash1"])

        pending = get_pending_chunks(db)
        hashes = [p["content_hash"] for p in pending]
        assert "hash1" not in hashes
        assert "hash2" in hashes

    def test_empty_list(self, db):
        """Calling with empty list doesn't crash."""
        mark_processed(db, [])
        # Should not raise

    def test_multiple_hashes(self, db):
        """Can mark multiple hashes at once."""
        _insert_memory(db, "h1", "C1", extracted=False)
        _insert_memory(db, "h2", "C2", extracted=False)
        _insert_memory(db, "h3", "C3", extracted=False)

        mark_processed(db, ["h1", "h2"])

        pending = get_pending_chunks(db)
        assert len(pending) == 1
        assert pending[0]["content_hash"] == "h3"


class TestStoreFacts:
    """Tests for store_facts dedup logic."""

    def test_inserts_new_fact(self, db):
        """Inserts a new fact as a graph edge."""
        facts = [
            {"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.9, "source_chunk": "hash1"}
        ]
        stored = store_facts(db, facts)
        assert stored == 1

        row = db.execute(
            "SELECT source_hash, target_hash, relationship_type, similarity, metadata "
            "FROM memory_graph WHERE source_hash = 'entity:RER'"
        ).fetchone()
        assert row is not None
        assert row[0] == "entity:RER"
        assert row[1] == "entity:PostgreSQL"
        assert row[2] == "uses"
        assert row[3] == 0.9
        meta = json.loads(row[4])
        assert meta["confidence"] == 0.9
        assert meta["source_chunk"] == "hash1"

    def test_dedup_updates_higher_confidence(self, db):
        """Same triple with higher confidence → updates."""
        facts1 = [
            {"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.7, "source_chunk": "h1"}
        ]
        facts2 = [
            {"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.95, "source_chunk": "h2"}
        ]

        store_facts(db, facts1)
        store_facts(db, facts2)

        rows = db.execute(
            "SELECT similarity, metadata FROM memory_graph "
            "WHERE source_hash = 'entity:RER' AND target_hash = 'entity:PostgreSQL'"
        ).fetchall()
        assert len(rows) == 1  # No duplicates
        assert rows[0][0] == 0.95
        meta = json.loads(rows[0][1])
        assert meta["confidence"] == 0.95

    def test_dedup_skips_lower_confidence(self, db):
        """Same triple with lower confidence → skip."""
        facts1 = [
            {"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.9, "source_chunk": "h1"}
        ]
        facts2 = [
            {"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.5, "source_chunk": "h2"}
        ]

        store_facts(db, facts1)
        stored = store_facts(db, facts2)

        assert stored == 0  # Nothing updated

        rows = db.execute(
            "SELECT similarity FROM memory_graph "
            "WHERE source_hash = 'entity:RER' AND target_hash = 'entity:PostgreSQL'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 0.9  # Kept original

    def test_normalizes_predicate(self, db):
        """Predicate is normalized to snake_case."""
        facts = [
            {"s": "MIR", "p": "depends on", "o": "Redis", "confidence": 0.8, "source_chunk": "h1"}
        ]
        store_facts(db, facts)

        row = db.execute(
            "SELECT relationship_type FROM memory_graph WHERE source_hash = 'entity:MIR'"
        ).fetchone()
        assert row[0] == "depends_on"

    def test_skips_empty_fields(self, db):
        """Facts with empty s/p/o are skipped."""
        facts = [
            {"s": "", "p": "uses", "o": "PostgreSQL", "confidence": 0.9, "source_chunk": "h1"},
            {"s": "RER", "p": "", "o": "PostgreSQL", "confidence": 0.9, "source_chunk": "h2"},
            {"s": "RER", "p": "uses", "o": "", "confidence": 0.9, "source_chunk": "h3"},
        ]
        stored = store_facts(db, facts)
        assert stored == 0

    def test_multiple_distinct_facts(self, db):
        """Multiple distinct facts are all stored."""
        facts = [
            {"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.9, "source_chunk": "h1"},
            {"s": "RER", "p": "uses", "o": "PostGIS", "confidence": 0.85, "source_chunk": "h1"},
            {"s": "MIR", "p": "uses", "o": "Redis", "confidence": 0.8, "source_chunk": "h2"},
        ]
        stored = store_facts(db, facts)
        assert stored == 3

        total = db.execute("SELECT COUNT(*) FROM memory_graph").fetchone()[0]
        assert total == 3


class TestExtractFactsBatch:
    """Tests for extract_facts_batch with mocked LLM."""

    @pytest.mark.asyncio
    async def test_mocked_successful_response(self):
        """LLM returns valid JSON with facts."""
        chunks = [
            {"content_hash": "hash1", "content": "RER uses PostgreSQL and PostGIS for spatial data."},
            {"content_hash": "hash2", "content": "MIR integrates with SICAR via REST API."},
        ]
        config = {"base_url": "http://localhost:11434/v1", "model": "test", "api_key": ""}

        mock_response = json.dumps([
            {
                "chunk": 1,
                "facts": [
                    {"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.9},
                    {"s": "RER", "p": "uses", "o": "PostGIS", "confidence": 0.85},
                ]
            },
            {
                "chunk": 2,
                "facts": [
                    {"s": "MIR", "p": "integrates_with", "o": "SICAR", "confidence": 0.9},
                ]
            },
        ])

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": mock_response}}]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            facts = await extract_facts_batch(chunks, config)

        assert len(facts) == 3
        assert facts[0]["s"] == "RER"
        assert facts[0]["p"] == "uses"
        assert facts[0]["o"] == "PostgreSQL"
        assert facts[0]["source_chunk"] == "hash1"
        assert facts[2]["s"] == "MIR"
        assert facts[2]["source_chunk"] == "hash2"

    @pytest.mark.asyncio
    async def test_empty_chunks(self):
        """Empty chunk list returns empty."""
        config = {"base_url": "http://localhost:11434/v1", "model": "test", "api_key": ""}
        facts = await extract_facts_batch([], config)
        assert facts == []

    @pytest.mark.asyncio
    async def test_llm_timeout_graceful(self):
        """LLM timeout doesn't crash — returns empty list."""
        import httpx

        chunks = [{"content_hash": "h1", "content": "Some content"}]
        config = {"base_url": "http://localhost:99999/v1", "model": "test", "api_key": ""}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            facts = await extract_facts_batch(chunks, config)

        assert facts == []

    @pytest.mark.asyncio
    async def test_llm_returns_invalid_json(self):
        """Invalid JSON from LLM → returns empty list, no crash."""
        chunks = [{"content_hash": "h1", "content": "Some content"}]
        config = {"base_url": "http://localhost:11434/v1", "model": "test", "api_key": ""}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "This is not JSON at all."}}]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            facts = await extract_facts_batch(chunks, config)

        assert facts == []

    @pytest.mark.asyncio
    async def test_markdown_wrapped_json(self):
        """LLM wraps JSON in markdown code block."""
        chunks = [{"content_hash": "h1", "content": "PostgreSQL is used by RER."}]
        config = {"base_url": "http://localhost:11434/v1", "model": "test", "api_key": ""}

        mock_content = '```json\n[{"chunk": 1, "facts": [{"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.9}]}]\n```'

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": mock_content}}]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            facts = await extract_facts_batch(chunks, config)

        assert len(facts) == 1
        assert facts[0]["s"] == "RER"


class TestRunExtraction:
    """Tests for the full run_extraction pipeline."""

    @pytest.mark.asyncio
    async def test_skips_if_no_llm_configured(self, db):
        """If MCP_NLI_LLM_* env vars are not set, returns skipped."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove all env vars that would configure LLM
            os.environ.pop("MCP_NLI_LLM_BASE_URL", None)
            os.environ.pop("MCP_NLI_LLM_MODEL", None)
            result = await run_extraction(db)

        assert result["status"] == "skipped"
        assert result["reason"] == "llm_not_configured"

    @pytest.mark.asyncio
    async def test_returns_ok_if_no_pending(self, db):
        """If all chunks processed, returns ok with 0 pending."""
        _insert_memory(db, "h1", "Content", extracted=True)

        with patch.dict(os.environ, {
            "MCP_NLI_LLM_BASE_URL": "http://localhost:11434/v1",
            "MCP_NLI_LLM_MODEL": "test-model",
        }):
            result = await run_extraction(db)

        assert result["status"] == "ok"
        assert result["pending"] == 0


class TestGetExtractionStatus:
    """Tests for get_extraction_status."""

    def test_basic_status(self, db):
        """Returns correct counts."""
        _insert_memory(db, "h1", "C1", extracted=False)
        _insert_memory(db, "h2", "C2", extracted=True)
        _insert_memory(db, "h3", "C3", extracted=False)

        # Add a fact edge
        db.execute(
            "INSERT INTO memory_graph (source_hash, target_hash, similarity, connection_types, relationship_type, metadata, created_at) "
            "VALUES ('entity:A', 'entity:B', 0.9, '[\"fact\"]', 'uses', '{}', 1000)",
        )
        db.commit()

        status = get_extraction_status(db)
        assert status["total_memories"] == 3
        assert status["pending"] == 2
        assert status["processed"] == 1
        assert status["facts_total"] == 1
        assert status["migration_pending"] is False

    def test_all_pending(self, db):
        """All memories are pending."""
        _insert_memory(db, "h1", "C1", extracted=False)
        _insert_memory(db, "h2", "C2", extracted=False)

        status = get_extraction_status(db)
        assert status["pending"] == 2
        assert status["processed"] == 0


class TestGetLLMConfig:
    """Tests for get_llm_config."""

    def test_returns_none_when_not_configured(self):
        """Returns None if env vars are missing."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MCP_NLI_LLM_BASE_URL", None)
            os.environ.pop("MCP_NLI_LLM_MODEL", None)
            assert get_llm_config() is None

    def test_returns_config_when_set(self):
        """Returns dict when both required vars are set."""
        with patch.dict(os.environ, {
            "MCP_NLI_LLM_BASE_URL": "http://localhost:11434/v1",
            "MCP_NLI_LLM_MODEL": "deepseek-r1",
            "MCP_NLI_LLM_API_KEY": "sk-test123",
        }):
            config = get_llm_config()
            assert config is not None
            assert config["base_url"] == "http://localhost:11434/v1"
            assert config["model"] == "deepseek-r1"
            assert config["api_key"] == "sk-test123"

    def test_returns_none_if_only_url(self):
        """Returns None if only URL is set but not model."""
        with patch.dict(os.environ, {
            "MCP_NLI_LLM_BASE_URL": "http://localhost:11434/v1",
        }, clear=True):
            os.environ.pop("MCP_NLI_LLM_MODEL", None)
            assert get_llm_config() is None
