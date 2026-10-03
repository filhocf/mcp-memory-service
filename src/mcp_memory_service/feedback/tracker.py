"""
RFC-MM-01: Passive feedback tracking for memory quality scoring.

Tracks correlations between search results and subsequent actions to infer
which memories are useful without requiring explicit user feedback.

All operations are non-blocking and fire-and-forget. Tracker errors never
crash handlers.
"""

import logging
import math
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Session time-to-live in seconds (5 minutes)
SESSION_TTL = 300


@dataclass
class SearchSession:
    """In-memory buffer for the last search by an agent."""

    agent_id: str
    timestamp: float  # time.time()
    returned_hashes: list[str]
    query: str
    # Cache content prefixes for reference matching (hash -> first 50 chars)
    _content_prefixes: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > SESSION_TTL


class SessionTracker:
    """
    Tracks search sessions per agent_id and detects usage patterns.

    Singleton — instantiated once at server startup.
    Thread-safe enough for async context (single-threaded event loop).
    """

    def __init__(self):
        self._sessions: dict[str, SearchSession] = {}

    def record_search(
        self,
        agent_id: str,
        returned_hashes: list[str],
        query: str,
        content_prefixes: Optional[dict[str, str]] = None,
    ) -> None:
        """
        Store the last search session for an agent.

        Args:
            agent_id: Identifier of the calling agent.
            returned_hashes: Content hashes of memories returned.
            query: The search query string.
            content_prefixes: Optional mapping of hash -> first 50 chars of content.
        """
        try:
            self._sessions[agent_id] = SearchSession(
                agent_id=agent_id,
                timestamp=time.time(),
                returned_hashes=list(returned_hashes),
                query=query,
                _content_prefixes=content_prefixes or {},
            )
        except Exception as e:
            logger.debug(f"Feedback tracker record_search failed: {e}")

    def check_reference(self, agent_id: str, content: str) -> list[str]:
        """
        Check if new content references memories from the last search.

        Compares content against first 50 chars of each returned memory.
        Returns list of hashes that were likely referenced.
        Clears matched hashes from the session.

        Args:
            agent_id: Agent identifier.
            content: New content being stored.

        Returns:
            List of content_hashes that appear to be referenced.
        """
        try:
            session = self._sessions.get(agent_id)
            if not session or session.is_expired:
                return []

            matched = []
            remaining_hashes = []

            for h in session.returned_hashes:
                prefix = session._content_prefixes.get(h, "")
                if prefix and len(prefix) >= 10 and prefix in content:
                    matched.append(h)
                else:
                    remaining_hashes.append(h)

            # Remove matched hashes from session
            if matched:
                session.returned_hashes = remaining_hashes

            return matched
        except Exception as e:
            logger.debug(f"Feedback tracker check_reference failed: {e}")
            return []

    def check_retry(self, agent_id: str, new_query: str) -> list[str]:
        """
        Detect if a new search is a retry (previous results failed).

        Heuristic: if token overlap between old and new query is <30%,
        it's a different topic (no signal). If >70%, it's a refinement/retry
        meaning previous results were not useful.

        Args:
            agent_id: Agent identifier.
            new_query: The new search query.

        Returns:
            List of hashes from previous session that should get negative signal.
            Empty if no retry detected or session expired.
        """
        try:
            session = self._sessions.get(agent_id)
            if not session or session.is_expired:
                return []

            if not session.query or not new_query:
                return []

            old_tokens = set(session.query.lower().split())
            new_tokens = set(new_query.lower().split())

            if not old_tokens or not new_tokens:
                return []

            # Intersection over union of both sets
            intersection = old_tokens & new_tokens
            union = old_tokens | new_tokens

            overlap = len(intersection) / len(union) if union else 0

            # >70% overlap = retry (previous results were not useful)
            if overlap > 0.7:
                failed_hashes = list(session.returned_hashes)
                # Clear session so we don't double-penalize
                session.returned_hashes = []
                return failed_hashes

            # <30% overlap = different topic, no signal
            return []
        except Exception as e:
            logger.debug(f"Feedback tracker check_retry failed: {e}")
            return []

    def cleanup(self) -> int:
        """Remove expired sessions. Returns count of removed sessions."""
        try:
            expired = [
                aid for aid, session in self._sessions.items()
                if session.is_expired
            ]
            for aid in expired:
                del self._sessions[aid]
            return len(expired)
        except Exception as e:
            logger.debug(f"Feedback tracker cleanup failed: {e}")
            return 0

    @property
    def active_sessions(self) -> int:
        """Number of active (non-expired) sessions."""
        return sum(1 for s in self._sessions.values() if not s.is_expired)


# --- Signal recording (database operations) ---


def record_signal(
    conn: sqlite3.Connection,
    content_hash: str,
    signal_type: str,
    weight: float,
    agent_id: Optional[str] = None,
) -> bool:
    """
    Record a feedback signal in the database.

    Args:
        conn: SQLite connection.
        content_hash: Hash of the memory receiving the signal.
        signal_type: One of 'referenced', 'drilldown', 'retry_failed', 'always_ignored'.
        weight: Signal weight (positive or negative).
        agent_id: Optional agent identifier.

    Returns:
        True if recorded successfully, False on error.
    """
    try:
        conn.execute(
            "INSERT INTO feedback_signals (content_hash, signal_type, weight, agent_id) "
            "VALUES (?, ?, ?, ?)",
            (content_hash, signal_type, weight, agent_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.debug(f"Feedback signal recording failed: {e}")
        return False


def record_signals_batch(
    conn: sqlite3.Connection,
    signals: list[tuple[str, str, float, Optional[str]]],
) -> int:
    """
    Record multiple feedback signals in a single transaction.

    Args:
        conn: SQLite connection.
        signals: List of (content_hash, signal_type, weight, agent_id) tuples.

    Returns:
        Number of signals recorded successfully.
    """
    if not signals:
        return 0
    try:
        conn.executemany(
            "INSERT INTO feedback_signals (content_hash, signal_type, weight, agent_id) "
            "VALUES (?, ?, ?, ?)",
            signals,
        )
        conn.commit()
        return len(signals)
    except Exception as e:
        logger.debug(f"Feedback batch signal recording failed: {e}")
        return 0


# --- Quality score recalculation ---


def recalculate_quality_scores(conn: sqlite3.Connection) -> dict:
    """
    Recalculate quality_score for memories with feedback signals.

    Formula: new_quality = base + sigmoid(sum_positive - 2*sum_negative) * decay(age)
    Where decay(age) = 0.5 ^ (days_since / 14) (half-life 14 days)

    Returns:
        Dict with 'updated' count and 'errors' list.
    """
    result = {"updated": 0, "errors": []}

    try:
        # Get all hashes with signals
        rows = conn.execute("""
            SELECT 
                fs.content_hash,
                fs.signal_type,
                fs.weight,
                fs.created_at
            FROM feedback_signals fs
            ORDER BY fs.content_hash
        """).fetchall()

        if not rows:
            return result

        # Group signals by hash
        signals_by_hash: dict[str, list[tuple[float, str]]] = {}
        for content_hash, signal_type, weight, created_at in rows:
            if content_hash not in signals_by_hash:
                signals_by_hash[content_hash] = []
            signals_by_hash[content_hash].append((weight, created_at))

        now = datetime.now(timezone.utc)
        updates = []

        for content_hash, signals in signals_by_hash.items():
            try:
                # Get current base quality_score
                row = conn.execute(
                    "SELECT quality_score FROM memories WHERE content_hash = ?",
                    (content_hash,),
                ).fetchone()

                if not row:
                    continue

                base_score = row[0] if row[0] is not None else 0.5

                # Calculate weighted sum with decay
                weighted_sum = 0.0
                for weight, created_at_str in signals:
                    try:
                        if created_at_str:
                            created_at_dt = datetime.fromisoformat(created_at_str)
                            # Make timezone-aware if naive (SQLite stores naive UTC)
                            if created_at_dt.tzinfo is None:
                                created_at_dt = created_at_dt.replace(tzinfo=timezone.utc)
                            days_since = (now - created_at_dt).total_seconds() / 86400
                        else:
                            days_since = 0
                    except (ValueError, TypeError):
                        days_since = 0

                    # decay = 0.5 ^ (days_since / 14)
                    decay = 0.5 ** (days_since / 14.0)

                    if weight > 0:
                        weighted_sum += weight * decay
                    else:
                        # Negative signals weighted 2x
                        weighted_sum += 2.0 * weight * decay

                # sigmoid to map to [0, 1] range adjustment
                sigmoid_val = 1.0 / (1.0 + math.exp(-weighted_sum))
                # Map sigmoid from [0,1] to [-0.3, +0.3] adjustment range
                adjustment = (sigmoid_val - 0.5) * 0.6

                new_quality = max(0.0, min(1.0, base_score + adjustment))
                updates.append((new_quality, content_hash))

            except Exception as e:
                result["errors"].append(f"{content_hash}: {e}")

        # Apply updates
        if updates:
            conn.executemany(
                "UPDATE memories SET quality_score = ? WHERE content_hash = ?",
                updates,
            )
            conn.commit()
            result["updated"] = len(updates)

    except Exception as e:
        result["errors"].append(f"recalculate_quality_scores: {e}")
        logger.error(f"Quality score recalculation failed: {e}")

    return result


# --- Singleton ---

_tracker_instance: Optional[SessionTracker] = None


def get_tracker() -> SessionTracker:
    """Get the global SessionTracker singleton."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = SessionTracker()
    return _tracker_instance


def reset_tracker() -> None:
    """Reset the singleton (for testing)."""
    global _tracker_instance
    _tracker_instance = None
