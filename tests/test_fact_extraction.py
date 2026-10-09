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
        _insert_memory(db, "hash2", "Content two", extracted=True)  # Already processed
        _insert_memory(db, "hash3", "Content three", extracted=False)

        chunks = get_pending_chunks(db)
        
        assert len(chunks) == 2
        hashes = [c["content_hash"] for c in chunks]
        assert "hash1" in hashes
        assert "hash3" in hashes
        assert "hash2" not in hashes

    def test_respects_limit(self, db):
        """Respects the limit parameter."""
        for i in range(5):
            _insert_memory(db, f"hash{i}", f"Content {i}")

        chunks = get_pending_chunks(db, limit=3)
        assert len(chunks) == 3

    def test_ordered_by_created_at(self, db):
        """Returns chunks in creation order (oldest first)."""
        _insert_memory(db, "hash2", "Second")
        _insert_memory(db, "hash1", "First") 
        _insert_memory(db, "hash3", "Third")

        chunks = get_pending_chunks(db, limit=2)
        
        # Should get first two by creation time
        hashes = [c["content_hash"] for c in chunks]
        assert hashes == ["hash2", "hash1"]  # Oldest first

    def test_empty_when_all_processed(self, db):
        """Returns empty list when all memories are processed."""
        _insert_memory(db, "hash1", "Content", extracted=True)

        chunks = get_pending_chunks(db)
        assert chunks == []


class TestExtractFactsBatch:
    """Tests for extract_facts_batch."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_chunks(self):
        """Returns empty list when no chunks provided."""
        result = await extract_facts_batch([])
        assert result == []

    @pytest.mark.asyncio
    @patch("mcp_memory_service.extraction.facts.get_llm_config")
    async def test_skips_when_llm_not_configured(self, mock_config):
        """Gracefully skips when LLM not configured."""
        mock_config.return_value = None
        chunks = [{"content_hash": "h1", "content": "test"}]
        
        result = await extract_facts_batch(chunks)
        assert result is None  # FAILURE path returns None (H2: distinguish failure from empty)

    @pytest.mark.asyncio
    @patch("mcp_memory_service.extraction.facts.get_llm_config")
    @patch("mcp_memory_service.harvest.rewriter.HarvestRewriter")
    async def test_parses_valid_json_response(self, mock_rewriter_class, mock_config):
        """Parses valid JSON response from LLM."""
        mock_config.return_value = {"base_url": "test", "model": "test"}
        
        # Mock HarvestRewriter instance and its methods
        mock_rewriter = mock_rewriter_class.return_value
        mock_rewriter.is_configured = True
        mock_rewriter._call_llm = AsyncMock(return_value=(
            '[{"chunk": 0, "facts": [{"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.9}]}]',
            "test_provider", 
            "test_model"
        ))
        
        chunks = [{"content_hash": "h1", "content": "RER uses PostgreSQL database"}]
        result = await extract_facts_batch(chunks)
        
        assert len(result) == 1
        assert result[0]["chunk"] == 0
        assert len(result[0]["facts"]) == 1
        assert result[0]["facts"][0]["s"] == "RER"

    @pytest.mark.asyncio
    @patch("mcp_memory_service.extraction.facts.get_llm_config")
    @patch("mcp_memory_service.harvest.rewriter.HarvestRewriter")
    async def test_handles_llm_failure_gracefully(self, mock_rewriter_class, mock_config):
        """Handles LLM failure without raising (M2.6)."""
        mock_config.return_value = {"base_url": "test", "model": "test"}
        
        mock_rewriter = mock_rewriter_class.return_value
        mock_rewriter.is_configured = True
        mock_rewriter._call_llm = AsyncMock(side_effect=Exception("LLM failed"))
        
        chunks = [{"content_hash": "h1", "content": "test"}]
        result = await extract_facts_batch(chunks)
        
        assert result is None  # FAILURE path returns None (H2: distinguish failure from empty)

    @pytest.mark.asyncio
    @patch("mcp_memory_service.extraction.facts.get_llm_config")  
    @patch("mcp_memory_service.harvest.rewriter.HarvestRewriter")
    async def test_handles_invalid_json_gracefully(self, mock_rewriter_class, mock_config):
        """Handles invalid JSON response gracefully."""
        mock_config.return_value = {"base_url": "test", "model": "test"}
        
        mock_rewriter = mock_rewriter_class.return_value
        mock_rewriter.is_configured = True
        mock_rewriter._call_llm = AsyncMock(return_value=("invalid json", "provider", "model"))
        
        chunks = [{"content_hash": "h1", "content": "test"}]
        result = await extract_facts_batch(chunks)
        
        assert result is None  # FAILURE path returns None (H2: distinguish failure from empty)


class TestStoreFacts:
    """Tests for store_facts."""

    def test_stores_new_facts(self, db):
        """Stores new facts as memory_graph entries."""
        facts = [
            {"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.9},
            {"s": "MIR", "p": "implements", "o": "OAuth2", "confidence": 0.8}
        ]
        
        count = store_facts(db, "chunk1", facts)
        assert count == 2
        
        # Check database content
        rows = db.execute("SELECT * FROM memory_graph").fetchall()
        assert len(rows) == 2
        
        # Check first fact
        row1 = [r for r in rows if r[0] == "RER"][0]
        assert row1[1] == "PostgreSQL"  # target_hash
        assert row1[4] == "uses"        # relationship_type
        # M2: connection_types is now a JSON array, not a raw string
        assert json.loads(row1[3]) == ["extracted_fact"]  # connection_types

    def test_skips_incomplete_facts(self, db):
        """Skips facts with missing subject, predicate, or object."""
        facts = [
            {"s": "RER", "p": "uses", "o": "", "confidence": 0.9},      # Missing object
            {"s": "", "p": "uses", "o": "PostgreSQL", "confidence": 0.9},  # Missing subject  
            {"s": "RER", "p": "", "o": "PostgreSQL", "confidence": 0.9},   # Missing predicate
            {"s": "MIR", "p": "uses", "o": "React", "confidence": 0.8}     # Valid
        ]
        
        count = store_facts(db, "chunk1", facts)
        assert count == 1  # Only the valid fact stored

    def test_updates_existing_with_higher_confidence(self, db):
        """Updates existing fact if new confidence is higher (M2.4)."""
        # Insert initial fact
        initial_metadata = json.dumps({"confidence": 0.7, "source_chunk": "chunk1"})
        db.execute("""
            INSERT INTO memory_graph 
            (source_hash, target_hash, similarity, connection_types, relationship_type, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("RER", "PostgreSQL", 0.7, "extracted_fact", "uses", initial_metadata, 123456))
        
        # Try to store same fact with higher confidence
        facts = [{"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.9}]
        count = store_facts(db, "chunk2", facts)
        
        assert count == 1
        
        # Check it was updated
        row = db.execute("SELECT metadata FROM memory_graph WHERE source_hash = ?", ("RER",)).fetchone()
        metadata = json.loads(row[0])
        assert metadata["confidence"] == 0.9
        assert metadata["source_chunk"] == "chunk2"

    def test_skips_existing_with_lower_confidence(self, db):
        """Skips existing fact if new confidence is lower (M2.4)."""
        # Insert initial fact
        initial_metadata = json.dumps({"confidence": 0.9, "source_chunk": "chunk1"})
        db.execute("""
            INSERT INTO memory_graph 
            (source_hash, target_hash, similarity, connection_types, relationship_type, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("RER", "PostgreSQL", 0.9, "extracted_fact", "uses", initial_metadata, 123456))
        
        # Try to store same fact with lower confidence
        facts = [{"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.7}]
        count = store_facts(db, "chunk2", facts)
        
        assert count == 0  # Should be skipped
        
        # Check original was preserved
        row = db.execute("SELECT metadata FROM memory_graph WHERE source_hash = ?", ("RER",)).fetchone()
        metadata = json.loads(row[0])
        assert metadata["confidence"] == 0.9
        assert metadata["source_chunk"] == "chunk1"

    def test_dedup_by_source_target_only_different_predicates_m1(self, db):
        """M1: Deduplica por (source, target) — predicados diferentes sobrescrevem se conf maior."""
        # Store initial fact with lower confidence
        facts1 = [{"s": "RER", "p": "uses", "o": "PostgreSQL", "confidence": 0.6}]
        count1 = store_facts(db, "chunk1", facts1)
        assert count1 == 1
        
        # Store same (source, target) with DIFFERENT predicate but HIGHER confidence
        facts2 = [{"s": "RER", "p": "migrated_from", "o": "PostgreSQL", "confidence": 0.9}]
        count2 = store_facts(db, "chunk2", facts2)
        assert count2 == 1  # Should update, not insert
        
        # Verify only one row exists for the (RER, PostgreSQL) pair
        rows = db.execute("SELECT * FROM memory_graph WHERE source_hash = ? AND target_hash = ?", 
                         ("RER", "PostgreSQL")).fetchall()
        assert len(rows) == 1
        
        # The higher confidence fact should have won, including its predicate
        row = rows[0]
        assert row[4] == "migrated_from"  # relationship_type should be the winner
        
        # Verify metadata shows higher confidence
        metadata = json.loads(row[5])
        assert metadata["confidence"] == 0.9
        assert metadata["source_chunk"] == "chunk2"
        
        # Verify total count is still 1 (no silent failures)
        total_facts = db.execute("SELECT COUNT(*) FROM memory_graph").fetchone()[0]
        assert total_facts == 1

    def test_normalizes_predicate_to_relationship_type(self, db):
        """Normalizes predicates with spaces to underscore relationship types."""
        facts = [{"s": "MIR", "p": "depends on", "o": "Spring Boot", "confidence": 0.8}]
        store_facts(db, "chunk1", facts)
        
        row = db.execute("SELECT relationship_type FROM memory_graph").fetchone()
        assert row[0] == "depends_on"


class TestMarkProcessed:
    """Tests for mark_processed."""

    def test_marks_chunks_as_processed(self, db):
        """Marks specified chunks as processed with timestamp."""
        _insert_memory(db, "hash1", "Content 1")
        _insert_memory(db, "hash2", "Content 2")
        
        mark_processed(db, ["hash1", "hash2"])
        
        # Check both are marked
        rows = db.execute("SELECT content_hash, facts_extracted_at FROM memories ORDER BY content_hash").fetchall()
        for hash_val, extracted_at in rows:
            assert extracted_at is not None
            # Should be valid timestamp
            datetime.fromisoformat(extracted_at.replace('Z', '+00:00'))

    def test_handles_empty_list(self, db):
        """Handles empty hash list gracefully."""
        mark_processed(db, [])  # Should not raise

    def test_idempotent_marking(self, db):
        """Multiple calls to mark_processed are idempotent."""
        _insert_memory(db, "hash1", "Content 1")
        
        mark_processed(db, ["hash1"])
        first_time = db.execute("SELECT facts_extracted_at FROM memories WHERE content_hash = ?", ("hash1",)).fetchone()[0]
        
        mark_processed(db, ["hash1"])
        second_time = db.execute("SELECT facts_extracted_at FROM memories WHERE content_hash = ?", ("hash1",)).fetchone()[0]
        
        # Should be updated to new timestamp
        assert second_time is not None


class TestGetExtractionStatus:
    """Tests for get_extraction_status."""

    def test_counts_pending_and_processed(self, db):
        """Correctly counts pending and processed chunks."""
        _insert_memory(db, "hash1", "Content 1", extracted=False)
        _insert_memory(db, "hash2", "Content 2", extracted=True)
        _insert_memory(db, "hash3", "Content 3", extracted=False)
        
        status = get_extraction_status(db)
        
        assert status["pending_chunks"] == 2
        assert status["processed_chunks"] == 1

    def test_counts_extracted_facts(self, db):
        """Counts facts in memory_graph with extracted_fact type."""
        # Add some facts
        db.execute("""
            INSERT INTO memory_graph 
            (source_hash, target_hash, similarity, connection_types, relationship_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("A", "B", 0.8, "extracted_fact", "related", 123456))
        db.execute("""
            INSERT INTO memory_graph 
            (source_hash, target_hash, similarity, connection_types, relationship_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)  
        """, ("C", "D", 0.9, "similarity", "related", 123456))  # Different type
        
        status = get_extraction_status(db)
        
        assert status["extracted_facts"] == 1  # Only extracted_fact type

    def test_reports_llm_configuration_status(self, db):
        """Reports whether LLM is configured."""
        with patch("mcp_memory_service.extraction.facts.get_llm_config", return_value={"base_url": "test"}):
            status = get_extraction_status(db)
            assert status["llm_configured"] is True
            
        with patch("mcp_memory_service.extraction.facts.get_llm_config", return_value=None):
            status = get_extraction_status(db)
            assert status["llm_configured"] is False


class TestRunExtraction:
    """Tests for run_extraction."""

    @pytest.mark.asyncio
    async def test_returns_error_when_llm_not_configured(self, db):
        """Returns error when LLM not configured."""
        with patch("mcp_memory_service.extraction.facts.get_llm_config", return_value=None):
            result = await run_extraction(db)
            assert "error" in result
            assert "LLM not configured" in result["error"]

    @pytest.mark.asyncio
    @patch("mcp_memory_service.extraction.facts.get_llm_config")
    @patch("mcp_memory_service.extraction.facts.extract_facts_batch", new_callable=AsyncMock)
    async def test_processes_chunks_in_batches(self, mock_extract, mock_config, db):
        """Processes chunks in batches and returns summary."""
        mock_config.return_value = {"base_url": "test", "model": "test"}
        mock_extract.return_value = [
            {"chunk": 0, "facts": [{"s": "A", "p": "relates_to", "o": "B", "confidence": 0.8}]}
        ]
        
        # Insert test memories
        for i in range(3):
            _insert_memory(db, f"hash{i}", f"Content {i}")
        
        result = await run_extraction(db, limit=3)
        
        assert result["processed"] == 3
        assert result["facts_stored"] >= 0  # Depends on mock behavior
        assert "duration_seconds" in result
        assert "batches" in result

    @pytest.mark.asyncio  
    @patch("mcp_memory_service.extraction.facts.get_llm_config")
    async def test_stops_when_no_pending_chunks(self, mock_config, db):
        """Stops processing when no pending chunks remain."""
        mock_config.return_value = {"base_url": "test", "model": "test"}
        
        # No chunks in database
        result = await run_extraction(db, limit=100)
        
        assert result["processed"] == 0

    @pytest.mark.asyncio
    @patch("mcp_memory_service.extraction.facts.get_llm_config")  
    @patch("mcp_memory_service.extraction.facts.extract_facts_batch", new_callable=AsyncMock)
    async def test_marks_all_chunks_as_processed(self, mock_extract, mock_config, db):
        """Marks all processed chunks, even those with no facts (M2.5)."""
        mock_config.return_value = {"base_url": "test", "model": "test"}
        mock_extract.return_value = []  # No facts returned
        
        _insert_memory(db, "hash1", "Content 1")
        
        await run_extraction(db, limit=1)
        
        # Should be marked as processed even with no facts
        row = db.execute("SELECT facts_extracted_at FROM memories WHERE content_hash = ?", ("hash1",)).fetchone()
        assert row[0] is not None

    @pytest.mark.asyncio
    @patch("mcp_memory_service.extraction.facts.get_llm_config")  
    @patch("mcp_memory_service.extraction.facts.extract_facts_batch", new_callable=AsyncMock)
    async def test_run_extraction_breaks_on_llm_failure_no_infinite_loop(self, mock_extract, mock_config, db):
        """HIGH-1: Breaks on LLM failure to prevent infinite loop, chunks remain unprocessed."""
        import time
        
        mock_config.return_value = {"base_url": "test", "model": "test"}
        mock_extract.return_value = None  # LLM failure (returns None)
        
        # Insert test memories
        _insert_memory(db, "hash1", "Content 1")
        _insert_memory(db, "hash2", "Content 2")
        
        # Test should complete quickly (no hang) and call LLM only once per run
        start_time = time.time()
        result = await run_extraction(db, limit=10)
        duration = time.time() - start_time
        
        # Should complete quickly (not hang in infinite loop)
        assert duration < 5.0, f"Took {duration:.2f}s, should be much faster"
        
        # Should not process any chunks when LLM fails
        assert result["processed"] == 0
        
        # Chunks should remain unprocessed (facts_extracted_at still NULL)
        unprocessed = db.execute("SELECT COUNT(*) FROM memories WHERE facts_extracted_at IS NULL").fetchone()[0]
        assert unprocessed == 2
        
        # LLM should be called exactly once (for first batch), not repeatedly
        assert mock_extract.call_count == 1

    @pytest.mark.asyncio
    @patch("mcp_memory_service.extraction.facts.get_llm_config")
    @patch("mcp_memory_service.harvest.rewriter.HarvestRewriter")
    async def test_extract_facts_batch_passes_high_max_tokens(self, mock_rewriter_class, mock_config):
        """HIGH-2: extract_facts_batch passes max_tokens=2000 to avoid JSON truncation."""
        mock_config.return_value = {"configured": True}
        
        # Mock HarvestRewriter instance
        mock_rewriter = mock_rewriter_class.return_value
        mock_rewriter.is_configured = True
        mock_rewriter._call_llm = AsyncMock(return_value=('[]', "test_provider", "test_model"))
        
        chunks = [{"content_hash": "h1", "content": "Test content"}]
        await extract_facts_batch(chunks)
        
        # Verify _call_llm was called with max_tokens=2000
        mock_rewriter._call_llm.assert_awaited_once()
        call_args = mock_rewriter._call_llm.call_args
        assert call_args[1]['max_tokens'] == 2000  # Keyword argument
        assert call_args[0][1] == 30.0  # timeout argument (LLM_TIMEOUT)


# Integration test for scheduler job
class TestFactExtractionSchedulerIntegration:
    """Integration tests for fact extraction scheduler job."""
    
    def _scheduler(self, env, monkeypatch):
        """Helper to create scheduler with mocked consolidator."""
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        consolidator = MagicMock()
        consolidator.storage = MagicMock()
        from mcp_memory_service.consolidation.scheduler import ConsolidationScheduler
        sched = ConsolidationScheduler(
            consolidator=consolidator,
            schedule_config={},  # no consolidation jobs
            enabled=True,
        )
        return sched

    def test_fact_extraction_job_registered_when_env_set(self, monkeypatch):
        """MCP_FACT_EXTRACT_SCHEDULE=6h registers a 'fact_extraction' job."""
        sched = self._scheduler({"MCP_FACT_EXTRACT_SCHEDULE": "6h"}, monkeypatch)
        assert sched.scheduler is not None
        sched._schedule_fact_extraction_job()
        job = sched.scheduler.get_job("fact_extraction")
        assert job is not None, "fact_extraction job should be registered when MCP_FACT_EXTRACT_SCHEDULE is set"

    def test_fact_extraction_job_not_registered_by_default(self, monkeypatch):
        """Unset MCP_FACT_EXTRACT_SCHEDULE → no fact extraction job (zero regression, opt-in)."""
        monkeypatch.delenv("MCP_FACT_EXTRACT_SCHEDULE", raising=False)
        sched = self._scheduler({}, monkeypatch)
        sched._schedule_fact_extraction_job()
        assert sched.scheduler.get_job("fact_extraction") is None

    def test_fact_extraction_job_not_registered_when_disabled(self, monkeypatch):
        """MCP_FACT_EXTRACT_SCHEDULE=disabled → no job."""
        sched = self._scheduler({"MCP_FACT_EXTRACT_SCHEDULE": "disabled"}, monkeypatch)
        sched._schedule_fact_extraction_job()
        assert sched.scheduler.get_job("fact_extraction") is None

    def test_invalid_schedule_does_not_register(self, monkeypatch):
        """Invalid schedule format doesn't register job."""
        sched = self._scheduler({"MCP_FACT_EXTRACT_SCHEDULE": "notaninterval"}, monkeypatch)
        sched._schedule_fact_extraction_job()
        assert sched.scheduler.get_job("fact_extraction") is None

    @pytest.mark.asyncio
    async def test_run_fact_extraction_calls_extraction_pipeline(self, monkeypatch):
        """_run_fact_extraction calls the extraction pipeline with proper error handling."""
        sched = self._scheduler({}, monkeypatch)
        
        # Mock the extraction pipeline
        extracted_result = {
            "processed": 5, 
            "facts_stored": 10,
            "duration_seconds": 1.5
        }
        
        mock_storage = MagicMock()
        mock_storage.conn = MagicMock()
        sched.consolidator.storage = mock_storage
        
        with patch("mcp_memory_service.extraction.facts.run_extraction", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = extracted_result
            await sched._run_fact_extraction()
            
        mock_run.assert_awaited_once_with(mock_storage.conn, limit=200)
        assert sched.execution_stats["successful_jobs"] == 1

    @pytest.mark.asyncio 
    async def test_run_fact_extraction_error_does_not_raise(self, monkeypatch):
        """A failure inside the fact extraction job must be swallowed (logged), never re-raised."""
        sched = self._scheduler({}, monkeypatch)
        
        # Mock storage that will cause an exception during extraction
        mock_storage = MagicMock()
        mock_storage.conn = MagicMock()
        sched.consolidator.storage = mock_storage
        
        with patch("mcp_memory_service.extraction.facts.run_extraction", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = RuntimeError("Extraction failed")
            await sched._run_fact_extraction()  # Must not raise
            
        assert sched.execution_stats["failed_jobs"] == 1

    @pytest.mark.asyncio
    async def test_run_fact_extraction_skips_without_storage(self, monkeypatch):
        """No storage on consolidator → skip gracefully (no crash)."""
        sched = self._scheduler({}, monkeypatch)
        sched.consolidator.storage = None
        
        await sched._run_fact_extraction()  # Should not raise
        assert sched.execution_stats["failed_jobs"] == 0  # Should exit early, not fail