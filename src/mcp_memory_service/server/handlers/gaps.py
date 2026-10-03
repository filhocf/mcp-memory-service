"""
Gap detection handler functions for MCP server (RFC-MM-03).

Provides proactive gap detection:
- memory_gaps: list, resolve, stats for detected knowledge gaps
- record_gap: internal helper called from search handler when score < threshold
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import List

from mcp import types

logger = logging.getLogger(__name__)

# Configurable threshold via environment variable
GAP_DETECTION_THRESHOLD = float(os.environ.get("MCP_GAP_DETECTION_THRESHOLD", "0.3"))

# Common stopwords for query normalization (EN + PT-BR)
_STOPWORDS = frozenset({
    # English
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "because", "about", "up", "it", "its", "that", "this", "what",
    "which", "who", "whom", "these", "those", "i", "me", "my", "myself",
    "we", "our", "ours", "you", "your", "he", "him", "his", "she", "her",
    "they", "them", "their", "and", "but", "or", "if",
    # Portuguese
    "o", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "sob",
    "sobre", "entre", "que", "se", "como", "mais", "mas", "ou", "e",
    "eu", "tu", "ele", "ela", "nós", "eles", "elas", "me", "te", "lhe",
    "nos", "vos", "lhes", "meu", "minha", "teu", "tua", "seu", "sua",
    "nosso", "nossa", "este", "esta", "esse", "essa", "aquele", "aquela",
    "isto", "isso", "aquilo", "ser", "estar", "ter", "haver", "ir",
    "não", "já", "ainda", "também", "muito", "bem", "agora", "aqui",
})


def normalize_query(query: str) -> str:
    """Normalize a query for dedup: lowercase, strip stopwords, sort tokens."""
    if not query:
        return ""
    # Lowercase and split
    tokens = re.split(r'\s+', query.lower().strip())
    # Remove stopwords and short tokens
    tokens = [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
    # Sort for canonical form
    tokens.sort()
    return " ".join(tokens)


async def record_gap(server, query: str, max_score: float, agent_id: str = None):
    """Record a search gap (called internally from search handler).

    Dedup: if normalized_query already exists (unresolved) in last 24h,
    just update max_score if the new score is higher.
    """
    try:
        storage = await server._ensure_storage_initialized()
        normalized = normalize_query(query)
        if not normalized:
            return  # Skip empty/stopword-only queries

        def _record():
            conn = storage.conn
            # Check for existing unresolved gap with same normalized query in last 24h
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            existing = conn.execute(
                """SELECT id, max_score FROM memory_gaps
                   WHERE normalized_query = ? AND resolved_at IS NULL AND created_at >= ?
                   ORDER BY created_at DESC LIMIT 1""",
                (normalized, cutoff)
            ).fetchone()

            if existing:
                gap_id, existing_score = existing
                # Update max_score only if new score is higher (closer to threshold)
                if max_score > existing_score:
                    conn.execute(
                        "UPDATE memory_gaps SET max_score = ? WHERE id = ?",
                        (max_score, gap_id)
                    )
                    conn.commit()
            else:
                conn.execute(
                    """INSERT INTO memory_gaps (query, normalized_query, max_score, agent_id)
                       VALUES (?, ?, ?, ?)""",
                    (query, normalized, max_score, agent_id)
                )
                conn.commit()

        await storage._run_in_thread(_record)
    except Exception as e:
        # Non-fatal: don't break search if gap recording fails
        logger.debug(f"Failed to record gap (non-fatal): {e}")


async def handle_memory_gaps(server, arguments: dict) -> List[types.TextContent]:
    """Handle memory_gaps tool with actions: list, resolve, stats."""
    action = arguments.get("action", "list")

    storage = await server._ensure_storage_initialized()

    if action == "list":
        return await _handle_list(storage, arguments)
    elif action == "resolve":
        return await _handle_resolve(storage, arguments)
    elif action == "stats":
        return await _handle_stats(storage, arguments)
    else:
        return [types.TextContent(
            type="text",
            text=f"Error: unknown action '{action}'. Use: list, resolve, stats"
        )]


async def _handle_list(storage, arguments: dict) -> List[types.TextContent]:
    """List top unresolved gaps ordered by recency."""
    limit = arguments.get("limit", 20)

    def _query():
        rows = storage.conn.execute(
            """SELECT id, query, normalized_query, max_score, agent_id, created_at
               FROM memory_gaps
               WHERE resolved_at IS NULL
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        return [
            {
                "id": r[0],
                "query": r[1],
                "normalized_query": r[2],
                "max_score": r[3],
                "agent_id": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]

    gaps = await storage._run_in_thread(_query)
    result = {"action": "list", "count": len(gaps), "gaps": gaps}
    return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def _handle_resolve(storage, arguments: dict) -> List[types.TextContent]:
    """Mark a gap as resolved."""
    gap_id = arguments.get("gap_id")
    normalized_query = arguments.get("normalized_query")

    if not gap_id and not normalized_query:
        return [types.TextContent(
            type="text",
            text="Error: provide gap_id or normalized_query to resolve"
        )]

    def _resolve():
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if gap_id:
            storage.conn.execute(
                "UPDATE memory_gaps SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
                (now, gap_id)
            )
        elif normalized_query:
            storage.conn.execute(
                "UPDATE memory_gaps SET resolved_at = ? WHERE normalized_query = ? AND resolved_at IS NULL",
                (now, normalized_query)
            )
        storage.conn.commit()
        return storage.conn.total_changes

    affected = await storage._run_in_thread(_resolve)
    return [types.TextContent(
        type="text",
        text=json.dumps({"action": "resolve", "resolved": affected}, default=str)
    )]


async def _handle_stats(storage, arguments: dict) -> List[types.TextContent]:
    """Gap statistics: count by week, resolution rate."""
    def _stats():
        # Count by week (last 8 weeks)
        weekly = storage.conn.execute(
            """SELECT strftime('%Y-W%W', created_at) as week, COUNT(*) as count
               FROM memory_gaps
               WHERE created_at >= datetime('now', '-56 days')
               GROUP BY week
               ORDER BY week DESC"""
        ).fetchall()

        # Overall stats
        total = storage.conn.execute("SELECT COUNT(*) FROM memory_gaps").fetchone()[0]
        unresolved = storage.conn.execute(
            "SELECT COUNT(*) FROM memory_gaps WHERE resolved_at IS NULL"
        ).fetchone()[0]
        resolved = total - unresolved

        # Average max_score of unresolved gaps
        avg_score = storage.conn.execute(
            "SELECT AVG(max_score) FROM memory_gaps WHERE resolved_at IS NULL"
        ).fetchone()[0]

        return {
            "action": "stats",
            "total": total,
            "unresolved": unresolved,
            "resolved": resolved,
            "resolution_rate": f"{(resolved / total * 100):.1f}%" if total > 0 else "N/A",
            "avg_unresolved_score": round(avg_score, 3) if avg_score else None,
            "weekly": [{"week": w[0], "count": w[1]} for w in weekly],
        }

    stats = await storage._run_in_thread(_stats)
    return [types.TextContent(type="text", text=json.dumps(stats, indent=2, default=str))]
