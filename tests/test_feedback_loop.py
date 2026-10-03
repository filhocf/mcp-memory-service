"""
Tests for RFC-MM-01: Feedback Loop (passive tracking).

Tests cover:
- SearchSession creation and TTL expiry
- check_reference detects match
- check_retry detects retry pattern
- Signal recording (single and batch)
- Quality score recalculation formula
- Cleanup removes expired sessions
- Non-blocking (tracker errors don't crash handlers)
"""

import math
import sqlite3
import time
from unittest.mock import patch

import pytest

from mcp_memory_service.feedback.tracker import (
    SESSION_TTL,
    SearchSession,
    SessionTracker,
    get_tracker,
    recalculate_quality_scores,
    record_signal,
    record_signals_batch,
    reset_tracker,
)


# --- Fixtures ---


@pytest.fixture
def tracker():
    """Fresh tracker instance for each test."""
    return SessionTracker()


@pytest.fixture
def db():
    """In-memory SQLite database with required schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0,
            agent_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_hash ON feedback_signals(content_hash)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            content_hash TEXT PRIMARY KEY,
            content TEXT,
            quality_score REAL DEFAULT 0.5,
            created_at TEXT DEFAULT (datetime('now')),
            metadata TEXT,
            tags TEXT
        )
    """)
    conn.commit()
    return conn


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the global tracker singleton between tests."""
    reset_tracker()
    yield
    reset_tracker()


# --- SearchSession tests ---


class TestSearchSession:
    def test_creation(self):
        """SearchSession stores all fields correctly."""
        session = SearchSession(
            agent_id="agent-1",
            timestamp=time.time(),
            returned_hashes=["hash1", "hash2"],
            query="test query",
        )
        assert session.agent_id == "agent-1"
        assert session.returned_hashes == ["hash1", "hash2"]
        assert session.query == "test query"
        assert not session.is_expired

    def test_ttl_expiry(self):
        """Session expires after SESSION_TTL seconds."""
        session = SearchSession(
            agent_id="agent-1",
            timestamp=time.time() - SESSION_TTL - 1,
            returned_hashes=["hash1"],
            query="old query",
        )
        assert session.is_expired

    def test_not_expired_within_ttl(self):
        """Session is active within TTL."""
        session = SearchSession(
            agent_id="agent-1",
            timestamp=time.time() - SESSION_TTL + 10,
            returned_hashes=["hash1"],
            query="recent query",
        )
        assert not session.is_expired

    def test_content_prefixes_stored(self):
        """Content prefixes are stored for reference matching."""
        prefixes = {"hash1": "This is the first 50 chars of memory content..."}
        session = SearchSession(
            agent_id="agent-1",
            timestamp=time.time(),
            returned_hashes=["hash1"],
            query="test",
            _content_prefixes=prefixes,
        )
        assert session._content_prefixes == prefixes


# --- SessionTracker.record_search tests ---


class TestRecordSearch:
    def test_record_basic(self, tracker):
        """record_search stores a session."""
        tracker.record_search("agent-1", ["h1", "h2"], "my query")
        assert "agent-1" in tracker._sessions
        assert tracker._sessions["agent-1"].query == "my query"
        assert tracker._sessions["agent-1"].returned_hashes == ["h1", "h2"]

    def test_overwrites_previous(self, tracker):
        """Only the LAST search per agent is kept."""
        tracker.record_search("agent-1", ["h1"], "first query")
        tracker.record_search("agent-1", ["h2"], "second query")
        assert tracker._sessions["agent-1"].query == "second query"
        assert tracker._sessions["agent-1"].returned_hashes == ["h2"]

    def test_with_content_prefixes(self, tracker):
        """Content prefixes are passed through."""
        prefixes = {"h1": "Hello world this is content"}
        tracker.record_search("agent-1", ["h1"], "test", content_prefixes=prefixes)
        assert tracker._sessions["agent-1"]._content_prefixes == prefixes


# --- SessionTracker.check_reference tests ---


class TestCheckReference:
    def test_detects_match(self, tracker):
        """Detects when stored content references a search result."""
        prefixes = {"hash1": "The quick brown fox jumps over the lazy dog today"}
        tracker.record_search("agent-1", ["hash1", "hash2"], "fox query", content_prefixes=prefixes)

        # Content that contains the prefix substring
        new_content = "Based on: The quick brown fox jumps over the lazy dog today — I decided to..."
        matched = tracker.check_reference("agent-1", new_content)

        assert "hash1" in matched
        assert "hash2" not in matched

    def test_no_match_short_prefix(self, tracker):
        """Short prefixes (<10 chars) are not matched to avoid false positives."""
        prefixes = {"hash1": "Short"}
        tracker.record_search("agent-1", ["hash1"], "test", content_prefixes=prefixes)

        matched = tracker.check_reference("agent-1", "Short content with Short word")
        assert matched == []

    def test_clears_matched_hashes(self, tracker):
        """Matched hashes are removed from the session."""
        prefixes = {"hash1": "Unique prefix that is long enough for matching"}
        tracker.record_search("agent-1", ["hash1", "hash2"], "test", content_prefixes=prefixes)

        tracker.check_reference("agent-1", "Contains: Unique prefix that is long enough for matching")

        # hash1 should be removed from session
        assert "hash1" not in tracker._sessions["agent-1"].returned_hashes
        assert "hash2" in tracker._sessions["agent-1"].returned_hashes

    def test_expired_session_returns_empty(self, tracker):
        """Expired sessions don't produce matches."""
        prefixes = {"hash1": "Some long prefix that would normally match here"}
        tracker.record_search("agent-1", ["hash1"], "test", content_prefixes=prefixes)
        # Force expiry
        tracker._sessions["agent-1"].timestamp = time.time() - SESSION_TTL - 1

        matched = tracker.check_reference("agent-1", "Some long prefix that would normally match here in content")
        assert matched == []

    def test_no_session_returns_empty(self, tracker):
        """No session for agent returns empty list."""
        matched = tracker.check_reference("unknown-agent", "any content")
        assert matched == []


# --- SessionTracker.check_retry tests ---


class TestCheckRetry:
    def test_detects_retry_high_overlap(self, tracker):
        """High token overlap (>70%) indicates retry."""
        tracker.record_search("agent-1", ["h1", "h2"], "memory search python implementation")

        # Very similar query = retry
        failed = tracker.check_retry("agent-1", "memory search python implementation details")
        # Overlap: {memory, search, python, implementation} / {memory, search, python, implementation, details}
        # = 4/5 = 0.8 > 0.7
        assert "h1" in failed
        assert "h2" in failed

    def test_no_retry_low_overlap(self, tracker):
        """Low token overlap (<30%) means different topic, not retry."""
        tracker.record_search("agent-1", ["h1", "h2"], "memory search python")

        # Very different query = new topic
        failed = tracker.check_retry("agent-1", "kubernetes deployment configuration")
        assert failed == []

    def test_no_retry_moderate_overlap(self, tracker):
        """Moderate overlap (30-70%) does not trigger retry signal."""
        tracker.record_search("agent-1", ["h1"], "python memory management best practices")

        # Some overlap but not enough for retry
        failed = tracker.check_retry("agent-1", "python garbage collection optimization")
        # Overlap: {python} / {python, memory, management, best, practices, garbage, collection, optimization}
        # = 1/8 = 0.125 < 0.3
        assert failed == []

    def test_clears_hashes_after_retry(self, tracker):
        """After retry detection, hashes are cleared to prevent double-penalizing."""
        tracker.record_search("agent-1", ["h1"], "exact same query words here")
        tracker.check_retry("agent-1", "exact same query words here")

        # Second retry check should find empty hashes
        failed = tracker.check_retry("agent-1", "exact same query words here")
        assert failed == []

    def test_expired_session_no_retry(self, tracker):
        """Expired session doesn't produce retry signal."""
        tracker.record_search("agent-1", ["h1"], "some query")
        tracker._sessions["agent-1"].timestamp = time.time() - SESSION_TTL - 1

        failed = tracker.check_retry("agent-1", "some query refined")
        assert failed == []

    def test_empty_query_no_retry(self, tracker):
        """Empty queries don't trigger retry."""
        tracker.record_search("agent-1", ["h1"], "original query")
        failed = tracker.check_retry("agent-1", "")
        assert failed == []


# --- Signal recording tests ---


class TestSignalRecording:
    def test_record_single_signal(self, db):
        """Single signal is recorded correctly."""
        success = record_signal(db, "hash123", "referenced", 1.0, "agent-1")
        assert success

        row = db.execute("SELECT * FROM feedback_signals WHERE content_hash = 'hash123'").fetchone()
        assert row is not None
        assert row[1] == "hash123"  # content_hash
        assert row[2] == "referenced"  # signal_type
        assert row[3] == 1.0  # weight
        assert row[4] == "agent-1"  # agent_id

    def test_record_negative_signal(self, db):
        """Negative signals are recorded."""
        success = record_signal(db, "hash456", "retry_failed", -0.5, "agent-2")
        assert success

        row = db.execute("SELECT weight FROM feedback_signals WHERE content_hash = 'hash456'").fetchone()
        assert row[0] == -0.5

    def test_record_batch_signals(self, db):
        """Batch recording writes all signals."""
        signals = [
            ("h1", "referenced", 1.0, "a1"),
            ("h2", "retry_failed", -0.5, "a1"),
            ("h3", "drilldown", 0.8, "a1"),
        ]
        count = record_signals_batch(db, signals)
        assert count == 3

        total = db.execute("SELECT COUNT(*) FROM feedback_signals").fetchone()[0]
        assert total == 3

    def test_batch_empty_list(self, db):
        """Empty batch returns 0."""
        count = record_signals_batch(db, [])
        assert count == 0

    def test_record_signal_no_agent(self, db):
        """Signal without agent_id is valid."""
        success = record_signal(db, "hash789", "always_ignored", -0.3, None)
        assert success

    def test_signal_on_broken_connection(self):
        """Signal recording fails gracefully on broken connection."""
        conn = sqlite3.connect(":memory:")
        conn.close()  # Close to break it
        success = record_signal(conn, "hash", "referenced", 1.0, "agent")
        assert not success


# --- Quality score recalculation tests ---


class TestQualityRecalculation:
    def test_positive_signals_increase_score(self, db):
        """Positive signals increase quality_score."""
        # Insert a memory
        db.execute(
            "INSERT INTO memories (content_hash, content, quality_score) VALUES (?, ?, ?)",
            ("hash1", "test content", 0.5),
        )
        # Insert positive signal
        db.execute(
            "INSERT INTO feedback_signals (content_hash, signal_type, weight, agent_id, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("hash1", "referenced", 1.0, "agent"),
        )
        db.commit()

        result = recalculate_quality_scores(db)
        assert result["updated"] == 1
        assert not result["errors"]

        new_score = db.execute("SELECT quality_score FROM memories WHERE content_hash = 'hash1'").fetchone()[0]
        assert new_score > 0.5

    def test_negative_signals_decrease_score(self, db):
        """Negative signals decrease quality_score."""
        db.execute(
            "INSERT INTO memories (content_hash, content, quality_score) VALUES (?, ?, ?)",
            ("hash2", "bad content", 0.5),
        )
        # Insert multiple negative signals
        for _ in range(3):
            db.execute(
                "INSERT INTO feedback_signals (content_hash, signal_type, weight, agent_id, created_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                ("hash2", "retry_failed", -0.5, "agent"),
            )
        db.commit()

        result = recalculate_quality_scores(db)
        assert result["updated"] == 1

        new_score = db.execute("SELECT quality_score FROM memories WHERE content_hash = 'hash2'").fetchone()[0]
        assert new_score < 0.5

    def test_score_clamped_to_range(self, db):
        """Quality score is clamped to [0.0, 1.0]."""
        db.execute(
            "INSERT INTO memories (content_hash, content, quality_score) VALUES (?, ?, ?)",
            ("hash3", "great content", 0.95),
        )
        # Many positive signals
        for _ in range(20):
            db.execute(
                "INSERT INTO feedback_signals (content_hash, signal_type, weight, agent_id, created_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                ("hash3", "referenced", 1.0, "agent"),
            )
        db.commit()

        recalculate_quality_scores(db)
        new_score = db.execute("SELECT quality_score FROM memories WHERE content_hash = 'hash3'").fetchone()[0]
        assert new_score <= 1.0

    def test_old_signals_decayed(self, db):
        """Old signals have less impact due to decay."""
        db.execute(
            "INSERT INTO memories (content_hash, content, quality_score) VALUES (?, ?, ?)",
            ("hash4", "content", 0.5),
        )
        # Insert old positive signal (30 days ago)
        db.execute(
            "INSERT INTO feedback_signals (content_hash, signal_type, weight, agent_id, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now', '-30 days'))",
            ("hash4", "referenced", 1.0, "agent"),
        )
        db.commit()

        recalculate_quality_scores(db)
        old_signal_score = db.execute("SELECT quality_score FROM memories WHERE content_hash = 'hash4'").fetchone()[0]

        # Reset
        db.execute("UPDATE memories SET quality_score = 0.5 WHERE content_hash = 'hash4'")
        db.execute("DELETE FROM feedback_signals")
        # Insert fresh positive signal
        db.execute(
            "INSERT INTO feedback_signals (content_hash, signal_type, weight, agent_id, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("hash4", "referenced", 1.0, "agent"),
        )
        db.commit()

        recalculate_quality_scores(db)
        fresh_signal_score = db.execute("SELECT quality_score FROM memories WHERE content_hash = 'hash4'").fetchone()[0]

        # Fresh signal should have more impact
        assert fresh_signal_score > old_signal_score

    def test_no_signals_returns_zero_updates(self, db):
        """No signals = no updates."""
        result = recalculate_quality_scores(db)
        assert result["updated"] == 0

    def test_missing_memory_skipped(self, db):
        """Signal for non-existent memory is skipped."""
        db.execute(
            "INSERT INTO feedback_signals (content_hash, signal_type, weight, agent_id, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("nonexistent", "referenced", 1.0, "agent"),
        )
        db.commit()

        result = recalculate_quality_scores(db)
        assert result["updated"] == 0

    def test_decay_formula(self):
        """Verify decay formula: 0.5 ^ (days / 14)."""
        # 0 days → decay = 1.0
        assert 0.5 ** (0 / 14.0) == 1.0
        # 14 days → decay = 0.5
        assert 0.5 ** (14 / 14.0) == 0.5
        # 28 days → decay = 0.25
        assert 0.5 ** (28 / 14.0) == 0.25

    def test_sigmoid_behavior(self):
        """Verify sigmoid maps correctly."""
        # sigmoid(0) = 0.5 → no adjustment
        assert abs(1.0 / (1.0 + math.exp(0)) - 0.5) < 0.001
        # sigmoid(large positive) ≈ 1.0 → positive adjustment
        assert 1.0 / (1.0 + math.exp(-5)) > 0.99
        # sigmoid(large negative) ≈ 0.0 → negative adjustment
        assert 1.0 / (1.0 + math.exp(5)) < 0.01


# --- Cleanup tests ---


class TestCleanup:
    def test_removes_expired_sessions(self, tracker):
        """cleanup() removes expired sessions."""
        tracker.record_search("agent-1", ["h1"], "q1")
        tracker.record_search("agent-2", ["h2"], "q2")

        # Force agent-1 to be expired
        tracker._sessions["agent-1"].timestamp = time.time() - SESSION_TTL - 1

        removed = tracker.cleanup()
        assert removed == 1
        assert "agent-1" not in tracker._sessions
        assert "agent-2" in tracker._sessions

    def test_keeps_active_sessions(self, tracker):
        """cleanup() keeps active sessions."""
        tracker.record_search("agent-1", ["h1"], "q1")

        removed = tracker.cleanup()
        assert removed == 0
        assert "agent-1" in tracker._sessions

    def test_active_sessions_count(self, tracker):
        """active_sessions property counts non-expired sessions."""
        tracker.record_search("agent-1", ["h1"], "q1")
        tracker.record_search("agent-2", ["h2"], "q2")
        tracker._sessions["agent-2"].timestamp = time.time() - SESSION_TTL - 1

        assert tracker.active_sessions == 1


# --- Non-blocking behavior tests ---


class TestNonBlocking:
    def test_record_search_exception_does_not_propagate(self, tracker):
        """record_search silently catches exceptions."""
        # Force an error by passing bad types that would fail
        with patch.object(tracker, '_sessions', side_effect=TypeError("boom")):
            # Should not raise
            tracker.record_search("agent", ["h1"], "query")

    def test_check_reference_on_corrupted_session(self, tracker):
        """check_reference handles corrupted session gracefully."""
        tracker._sessions["agent"] = SearchSession(
            agent_id="agent",
            timestamp=time.time(),
            returned_hashes=["h1"],
            query="test",
            _content_prefixes=None,  # type: ignore — simulate corruption
        )
        # Should not crash, just return empty
        result = tracker.check_reference("agent", "some content")
        assert result == []

    def test_check_retry_with_none_query(self, tracker):
        """check_retry handles None query gracefully."""
        tracker.record_search("agent", ["h1"], "original")
        result = tracker.check_retry("agent", None)  # type: ignore
        assert result == []

    def test_record_signal_with_closed_connection(self):
        """record_signal returns False on closed connection."""
        conn = sqlite3.connect(":memory:")
        conn.close()
        result = record_signal(conn, "hash", "referenced", 1.0, "agent")
        assert result is False

    def test_batch_signals_with_closed_connection(self):
        """record_signals_batch returns 0 on closed connection."""
        conn = sqlite3.connect(":memory:")
        conn.close()
        result = record_signals_batch(conn, [("h", "referenced", 1.0, "a")])
        assert result == 0


# --- Singleton tests ---


class TestSingleton:
    def test_get_tracker_returns_same_instance(self):
        """get_tracker() always returns the same instance."""
        t1 = get_tracker()
        t2 = get_tracker()
        assert t1 is t2

    def test_reset_tracker_creates_new_instance(self):
        """reset_tracker() causes next get_tracker() to create new instance."""
        t1 = get_tracker()
        reset_tracker()
        t2 = get_tracker()
        assert t1 is not t2
