# Copyright 2024 Heinrich Krupp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Usage telemetry (PROVEITO/USO instrumentation).

Design decisions (v1, sqlite-vec):
- Default ON. Env var MCP_USAGE_TELEMETRY; only 'false'/'0'/'no' (case-insensitive)
  disables it.
- Privacy: raw queries/content are NEVER stored. We store a truncated sha256
  query_hash plus the query length, never the query text.
- Additive and best-effort: a telemetry failure NEVER breaks the read path and
  must not add perceptible latency to the critical path. Every log call is
  wrapped in try/except and only emits a warning on failure.
"""

import os
import time
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Values that disable telemetry (case-insensitive). Everything else -> enabled.
_DISABLED_VALUES = {"false", "0", "no"}

# Tool labels used in the usage_events.tool column.
TOOL_RETRIEVAL = "retrieval"
TOOL_FEEDBACK = "feedback"


def get_telemetry_flag_value() -> bool:
    """Return whether usage telemetry is enabled.

    Default ON. Only 'false', '0', or 'no' (case-insensitive, trimmed) disable it.
    """
    raw = os.environ.get("MCP_USAGE_TELEMETRY")
    if raw is None:
        return True
    return raw.strip().lower() not in _DISABLED_VALUES


def query_hash(query: Optional[str]) -> Optional[str]:
    """Compute a privacy-preserving hash of a query.

    Returns the first 16 hex chars of the sha256 of the query. Never returns the
    raw query. Returns None for a None/empty query.
    """
    if not query:
        return None
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


def _store_connection(storage) -> Optional[Any]:
    """Best-effort access to the underlying sqlite3 connection."""
    return getattr(storage, "conn", None)


def _insert_event(conn, event_type: str, tool: str, fields: Dict[str, Any]) -> None:
    """Synchronous INSERT of a single usage event. Caller handles errors."""
    conn.execute(
        """
        INSERT INTO usage_events
            (event_type, tool, content_hash, query_hash, n_results, latency_ms,
             rating, source, agent_id, timestamp, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_type,
            tool,
            fields.get("content_hash"),
            fields.get("query_hash"),
            fields.get("n_results"),
            fields.get("latency_ms"),
            fields.get("rating"),
            fields.get("source"),
            fields.get("agent_id"),
            fields.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            fields.get("metadata"),
        ),
    )
    conn.commit()


async def log_usage_event(storage, event_type: str, **fields: Any) -> None:
    """Best-effort log of a usage event.

    Never raises: a telemetry failure must not break the read path. If the
    killswitch is off, this is a no-op. The 'tool' field defaults to event_type
    when not supplied.
    """
    try:
        if not get_telemetry_flag_value():
            return

        conn = _store_connection(storage)
        if conn is None:
            return

        tool = fields.pop("tool", None) or event_type

        def _telemetry_insert():
            _insert_event(conn, event_type, tool, fields)

        # Route through the storage retry wrapper when available so the insert
        # obeys the same connection locking as the rest of the backend. The
        # function name carries 'telemetry' so test harnesses can target it.
        execute_with_retry = getattr(storage, "_execute_with_retry", None)
        if execute_with_retry is not None:
            await execute_with_retry(_telemetry_insert)
        else:
            _telemetry_insert()
    except Exception as e:  # noqa: BLE001 - best-effort, never propagate
        logger.warning("Usage telemetry log failed (non-fatal): %s", e)


def _percentile(values, pct: float) -> float:
    """Nearest-rank percentile of a list of numbers. Empty -> 0.0."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    # Nearest-rank: rank = ceil(pct/100 * N), 1-based.
    import math
    rank = max(1, math.ceil((pct / 100.0) * len(ordered)))
    return float(ordered[min(rank, len(ordered)) - 1])


async def get_usage_metrics(storage) -> Dict[str, Any]:
    """Aggregate usage metrics from the usage_events table.

    Returns a dict of proveito/uso metrics. Best-effort: on any failure returns
    a zeroed structure instead of raising.
    """
    empty: Dict[str, Any] = {
        "total_retrievals": 0,
        "total_feedback": 0,
        "avg_latency_ms": 0.0,
        "total_results_returned": 0,
        "feedback_coverage": 0.0,
        "latency_p50_by_tool": {},
        "latency_p95_by_tool": {},
    }

    try:
        conn = _store_connection(storage)
        if conn is None:
            return empty

        def _read_events():
            cursor = conn.execute(
                "SELECT tool, n_results, latency_ms, content_hash FROM usage_events"
            )
            return cursor.fetchall()

        execute_with_retry = getattr(storage, "_execute_with_retry", None)
        if execute_with_retry is not None:
            rows = await execute_with_retry(_read_events)
        else:
            rows = _read_events()

        total_retrievals = 0
        total_feedback = 0
        total_results_returned = 0
        latencies = []
        latency_by_tool: Dict[str, list] = {}
        retrieved_hashes = set()
        feedback_hashes = set()

        for row in rows:
            tool = row["tool"]
            n_results = row["n_results"]
            latency_ms = row["latency_ms"]
            content_hash = row["content_hash"]

            if tool == TOOL_RETRIEVAL:
                total_retrievals += 1
                if n_results is not None:
                    total_results_returned += int(n_results)
                if latency_ms is not None:
                    latencies.append(float(latency_ms))
                    latency_by_tool.setdefault(tool, []).append(float(latency_ms))
            elif tool == TOOL_FEEDBACK:
                total_feedback += 1
                if content_hash:
                    feedback_hashes.add(content_hash)
                if latency_ms is not None:
                    latency_by_tool.setdefault(tool, []).append(float(latency_ms))

        avg_latency_ms = (sum(latencies) / len(latencies)) if latencies else 0.0

        # Feedback coverage: fraction of feedback events relative to retrievals.
        feedback_coverage = (
            (total_feedback / total_retrievals) if total_retrievals else 0.0
        )

        latency_p50_by_tool = {
            t: _percentile(vals, 50) for t, vals in latency_by_tool.items()
        }
        latency_p95_by_tool = {
            t: _percentile(vals, 95) for t, vals in latency_by_tool.items()
        }

        return {
            "total_retrievals": total_retrievals,
            "total_feedback": total_feedback,
            "avg_latency_ms": avg_latency_ms,
            "total_results_returned": total_results_returned,
            "feedback_coverage": feedback_coverage,
            "latency_p50_by_tool": latency_p50_by_tool,
            "latency_p95_by_tool": latency_p95_by_tool,
        }
    except Exception as e:  # noqa: BLE001 - best-effort aggregator
        logger.warning("Usage metrics aggregation failed (non-fatal): %s", e)
        return empty
