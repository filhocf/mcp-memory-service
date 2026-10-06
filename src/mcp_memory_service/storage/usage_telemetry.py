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
import json
import math
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

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

        # Capture of returned content hashes (REQ-1). When the caller passes
        # returned_hashes, fold them into the metadata JSON as
        # {"returned_hashes": [...]} without ever touching the raw query/content.
        # content_hash is a sha256 digest (not raw text), so this preserves the
        # privacy guarantee. We merge into any existing metadata dict the caller
        # may have supplied.
        returned_hashes = fields.pop("returned_hashes", None)
        if returned_hashes is not None:
            existing_meta = fields.get("metadata")
            meta_obj: Dict[str, Any] = {}
            if existing_meta:
                try:
                    parsed = json.loads(existing_meta) if isinstance(existing_meta, str) else existing_meta
                    if isinstance(parsed, dict):
                        meta_obj = parsed
                except (ValueError, TypeError):
                    meta_obj = {}
            meta_obj["returned_hashes"] = list(returned_hashes)
            fields["metadata"] = json.dumps(meta_obj)

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


# ---------------------------------------------------------------------------
# Assertiveness metric + reaccess/re-query signal derivation (ADR-0005 / RFC-MM-01)
#
# Everything below derives purely from the usage_events table (zero-discipline):
# retrieval events carry {"returned_hashes": [...]} in metadata (REQ-1), and the
# signals/metrics are computed offline from those rows. No manual rating API, no
# new write path on the hot retrieve() loop.
# ---------------------------------------------------------------------------

# Windows (ADR-0005 §2). Reaccess looks back 14 days; a re-query burst is tight
# (<= 5 minutes between two retrievals of the same agent).
REACCESS_WINDOW_DAYS = 14
RETRY_WINDOW_SECONDS = 5 * 60

TOOL_INJECTION = "injection"


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime. Tolerant of None."""
    if not ts:
        return None
    try:
        s = ts.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _event_returned_hashes(metadata_raw: Optional[str]) -> List[str]:
    """Extract returned_hashes from an event's metadata JSON. Empty on absence."""
    if not metadata_raw:
        return []
    try:
        meta = json.loads(metadata_raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(meta, dict):
        return []
    hashes = meta.get("returned_hashes")
    if isinstance(hashes, list):
        return [h for h in hashes if h]
    return []


def _event_belief_hashes(metadata_raw: Optional[str]) -> List[str]:
    """Extract belief_hashes from an injection event's metadata JSON."""
    if not metadata_raw:
        return []
    try:
        meta = json.loads(metadata_raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(meta, dict):
        return []
    hashes = meta.get("belief_hashes")
    if isinstance(hashes, list):
        return [h for h in hashes if h]
    return []


def _load_events(storage, event_type: str) -> list:
    """Load raw usage_events rows for a given event_type, oldest-first."""
    conn = _store_connection(storage)
    if conn is None:
        return []

    def _read():
        cursor = conn.execute(
            "SELECT id, event_type, tool, content_hash, query_hash, agent_id, "
            "timestamp, metadata FROM usage_events WHERE event_type = ? "
            "ORDER BY timestamp ASC, id ASC",
            (event_type,),
        )
        return cursor.fetchall()

    return _read()


async def _load_events_async(storage, event_type: str) -> list:
    conn = _store_connection(storage)
    if conn is None:
        return []
    execute_with_retry = getattr(storage, "_execute_with_retry", None)

    def _read():
        cursor = conn.execute(
            "SELECT id, event_type, tool, content_hash, query_hash, agent_id, "
            "timestamp, metadata FROM usage_events WHERE event_type = ? "
            "ORDER BY timestamp ASC, id ASC",
            (event_type,),
        )
        return cursor.fetchall()

    if execute_with_retry is not None:
        return await execute_with_retry(_read)
    return _read()


def _retrieval_tuples(rows) -> List[Dict[str, Any]]:
    """Normalise retrieval rows into dicts with parsed ts + returned_hashes."""
    out: List[Dict[str, Any]] = []
    for row in rows:
        ts = _parse_iso(row["timestamp"])
        out.append(
            {
                "id": row["id"],
                "agent_id": row["agent_id"],
                "query_hash": row["query_hash"],
                "ts": ts,
                "returned_hashes": _event_returned_hashes(row["metadata"]),
            }
        )
    # Stable order by time then id (None timestamps sink to the front).
    out.sort(key=lambda e: (e["ts"] or datetime.min.replace(tzinfo=timezone.utc), e["id"]))
    return out


async def derive_signals(storage) -> Dict[str, Dict[str, int]]:
    """Derive per-content_hash reaccess / retry_failed signals (REQ-2/3).

    Zero-discipline: reads only retrieval events from usage_events. When the
    kill-switch is off nothing was captured, so this returns {} naturally.

    reaccess: for a given agent, a content_hash returned in >=2 distinct
      retrievals within the 14-day window contributes (N-1) positive signals.
    retry_failed: two retrievals of the same agent <5 min apart with distinct
      query_hash and overlapping returned_hashes mark a negative signal on the
      hashes returned by the FIRST (earlier) event.
    """
    try:
        if not get_telemetry_flag_value():
            return {}

        rows = await _load_events_async(storage, "retrieval")
        events = _retrieval_tuples(rows)
        if not events:
            return {}

        signals: Dict[str, Dict[str, int]] = {}

        def _bump(h: str, key: str, amount: int = 1) -> None:
            slot = signals.setdefault(h, {"reaccess": 0, "retry_failed": 0})
            slot[key] = slot.get(key, 0) + amount

        # Group by agent for both signals. agent_id may be None (the real
        # retrieve() hook has no agent yet); treat None as its own bucket so
        # derivation degrades gracefully instead of crashing.
        by_agent: Dict[Any, List[Dict[str, Any]]] = {}
        for ev in events:
            by_agent.setdefault(ev["agent_id"], []).append(ev)

        reaccess_cutoff = timedelta(days=REACCESS_WINDOW_DAYS)

        for agent, agent_events in by_agent.items():
            # --- reaccess: count re-appearances of each hash within 14 days. ---
            # Per hash, the events (ordered) in which it appears; each extra
            # appearance within the window of the first is +1 reaccess.
            hash_appearances: Dict[str, List[datetime]] = {}
            for ev in agent_events:
                for h in ev["returned_hashes"]:
                    hash_appearances.setdefault(h, []).append(
                        ev["ts"] or datetime.now(timezone.utc)
                    )
            for h, times in hash_appearances.items():
                times.sort()
                anchor = times[0]
                reappearances = sum(
                    1 for t in times[1:] if (t - anchor) <= reaccess_cutoff
                )
                if reappearances > 0:
                    _bump(h, "reaccess", reappearances)

            # --- retry_failed: tight re-query bursts per hash (first-event). ---
            # Work on each hash's own appearance timeline (ordered). A tight
            # distinct-query burst (consecutive appearances <=5 min apart with a
            # different query_hash) is a failed refinement: the agent re-queried
            # because the first attempt was unsatisfactory. We charge ONE
            # retry_failed per such burst (on the hash), so a long reaccess chain
            # is not swamped by one negative per step.
            hash_events: Dict[str, List[Dict[str, Any]]] = {}
            for ev in agent_events:
                for h in ev["returned_hashes"]:
                    hash_events.setdefault(h, []).append(ev)
            for h, hevents in hash_events.items():
                hevents.sort(
                    key=lambda e: (
                        e["ts"] or datetime.min.replace(tzinfo=timezone.utc),
                        e["id"],
                    )
                )
                in_burst = False
                for i in range(len(hevents) - 1):
                    e1 = hevents[i]
                    e2 = hevents[i + 1]
                    t1, t2 = e1["ts"], e2["ts"]
                    if t1 is None or t2 is None:
                        in_burst = False
                        continue
                    gap = abs((t2 - t1).total_seconds())
                    tight = gap <= RETRY_WINDOW_SECONDS
                    distinct = e1["query_hash"] != e2["query_hash"]
                    if tight and distinct:
                        if not in_burst:
                            # Start of a new tight re-query burst for this hash.
                            _bump(h, "retry_failed", 1)
                            in_burst = True
                    else:
                        in_burst = False

        return signals
    except Exception as e:  # noqa: BLE001 - best-effort derivation
        logger.warning("derive_signals failed (non-fatal): %s", e)
        return {}


def _classify_requeries(events: List[Dict[str, Any]]) -> int:
    """Count retrievals classified as re-queries (ADR-0005 #1).

    A retrieval is a re-query when it closely follows (<=5 min) a prior
    retrieval of the same agent with a distinct query_hash and overlapping
    returned_hashes (the second event is the re-query).
    """
    by_agent: Dict[Any, List[Dict[str, Any]]] = {}
    for ev in events:
        by_agent.setdefault(ev["agent_id"], []).append(ev)

    re_queries = 0
    for agent_events in by_agent.values():
        for i in range(1, len(agent_events)):
            prev = agent_events[i - 1]
            cur = agent_events[i]
            t1, t2 = prev["ts"], cur["ts"]
            if t1 is None or t2 is None:
                continue
            if abs((t2 - t1).total_seconds()) > RETRY_WINDOW_SECONDS:
                continue
            if prev["query_hash"] == cur["query_hash"]:
                continue
            if not (set(prev["returned_hashes"]) & set(cur["returned_hashes"])):
                continue
            re_queries += 1
    return re_queries


async def get_assertiveness_metrics(storage) -> Dict[str, Any]:
    """Compute ADR-0005 assertiveness sub-metrics from usage_events.

    Returns:
      re_query_rate: re-query retrievals / total retrievals (0.0 when empty).
      injection_coverage: fraction of injected belief_hashes that later reappear
        in a retrieval's returned_hashes or a feedback event's content_hash.
      lost_context_count / lost_context_rate: retrievals that returned a recent
        checkpoint memory (proxy for context that should already have been present).
    """
    empty = {
        "re_query_rate": 0.0,
        "injection_coverage": 0.0,
        "lost_context_count": 0,
        "lost_context_rate": 0.0,
    }
    try:
        retrieval_rows = await _load_events_async(storage, "retrieval")
        events = _retrieval_tuples(retrieval_rows)
        total_retrievals = len(events)

        if total_retrievals == 0:
            return dict(empty)

        # --- re_query_rate (REQ-4) ---
        re_queries = _classify_requeries(events)
        re_query_rate = re_queries / total_retrievals if total_retrievals else 0.0

        # --- injection_coverage (REQ-5) ---
        injection_rows = await _load_events_async(storage, "injection")
        injected: set = set()
        injection_times: Dict[str, datetime] = {}
        for row in injection_rows:
            ts = _parse_iso(row["timestamp"]) or datetime.min.replace(tzinfo=timezone.utc)
            for h in _event_belief_hashes(row["metadata"]):
                injected.add(h)
                # earliest injection time per hash
                if h not in injection_times or ts < injection_times[h]:
                    injection_times[h] = ts

        reused_after_injection: set = set()
        if injected:
            # A belief hash is "covered" if it reappears later in a retrieval's
            # returned_hashes or in a feedback event.
            feedback_rows = await _load_events_async(storage, "feedback")
            later_hashes_with_ts: List[Tuple[str, datetime]] = []
            for ev in events:
                for h in ev["returned_hashes"]:
                    later_hashes_with_ts.append(
                        (h, ev["ts"] or datetime.now(timezone.utc))
                    )
            for row in feedback_rows:
                if row["content_hash"]:
                    later_hashes_with_ts.append(
                        (
                            row["content_hash"],
                            _parse_iso(row["timestamp"]) or datetime.now(timezone.utc),
                        )
                    )
            for h, ts in later_hashes_with_ts:
                if h in injected and ts >= injection_times.get(h, ts):
                    reused_after_injection.add(h)
            injection_coverage = len(reused_after_injection) / len(injected)
        else:
            injection_coverage = 0.0

        # --- lost_context (REQ-6, proxy) ---
        # A retrieval that returns a recent checkpoint memory counts as a
        # lost-context event: that memory arguably should already have been in
        # context. We proxy "checkpoint" by tag or memory_type.
        checkpoint_hashes = await _recent_checkpoint_hashes(storage)
        lost_context_count = 0
        if checkpoint_hashes:
            for ev in events:
                if set(ev["returned_hashes"]) & checkpoint_hashes:
                    lost_context_count += 1
        lost_context_rate = (
            lost_context_count / total_retrievals if total_retrievals else 0.0
        )

        return {
            "re_query_rate": re_query_rate,
            "injection_coverage": injection_coverage,
            "lost_context_count": lost_context_count,
            "lost_context_rate": lost_context_rate,
        }
    except Exception as e:  # noqa: BLE001 - best-effort aggregator
        logger.warning("get_assertiveness_metrics failed (non-fatal): %s", e)
        return dict(empty)


async def _recent_checkpoint_hashes(storage, days: int = 14) -> set:
    """Return content_hashes of recent checkpoint-like memories (proxy).

    Checkpoint proxy: a memory tagged 'checkpoint' OR whose memory_type is a
    milestone/checkpoint, created within the recent window.
    """
    conn = _store_connection(storage)
    if conn is None:
        return set()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()

        def _read():
            cursor = conn.execute(
                """
                SELECT content_hash FROM memories
                WHERE deleted_at IS NULL
                  AND created_at >= ?
                  AND (
                        (',' || tags || ',') LIKE '%,checkpoint,%'
                     OR memory_type IN ('checkpoint', 'milestone')
                  )
                """,
                (cutoff,),
            )
            return cursor.fetchall()

        execute_with_retry = getattr(storage, "_execute_with_retry", None)
        rows = await execute_with_retry(_read) if execute_with_retry else _read()
        return {row[0] for row in rows if row[0]}
    except Exception as e:  # noqa: BLE001
        logger.warning("_recent_checkpoint_hashes failed (non-fatal): %s", e)
        return set()


def _sigmoid(x: float) -> float:
    """Signed logistic in (-1, 1): 2*sigmoid(x) - 1 (== tanh(x/2)).

    Needed so negative net signal pushes quality BELOW base and positive net
    pushes it above base; the magnitude saturates smoothly.
    """
    try:
        s = 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        s = 0.0 if x < 0 else 1.0
    return 2.0 * s - 1.0


def _decay(age_days: float, half_life_days: float = REACCESS_WINDOW_DAYS) -> float:
    """Exponential decay with the given half-life. age 0 -> 1.0."""
    if age_days <= 0:
        return 1.0
    return 0.5 ** (age_days / half_life_days)


async def recompute_quality_scores(
    storage,
    base: float = 0.5,
    signals_override: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, float]:
    """Recompute per-content_hash quality scores from derived signals (REQ-7).

        quality = base + sigmoid(sum(pos) - NEG_WEIGHT*sum(neg)) * decay(age, half_life=14d)

    where pos = reaccess (and other positive signals) and neg = retry_failed.
    'sigmoid' here is the SIGNED logistic in (-1, 1) so a negative net pushes
    quality below base and a positive net above it (a plain (0,1) sigmoid could
    never drop below base). NEG_WEIGHT (2.5) is the "retry costs more than a
    reaccess rewards" asymmetry from RFC-MM-01: a hash reaccessed N times but
    caught in one tight re-query burst should still net positive, while a hash
    whose only history is short re-query bursts nets negative.

    signals_override lets a caller inject synthetic signals for testing/what-if:
      {hash: {"reaccess": N, "retry_failed": M, "age_days": D}}
    When provided, derivation is skipped and these signals are used verbatim.
    """
    NEG_WEIGHT = 2.5
    try:
        if signals_override is not None:
            scores: Dict[str, float] = {}
            for h, sig in signals_override.items():
                pos = float(sig.get("reaccess", 0)) + float(sig.get("referenced", 0)) + float(sig.get("drilldown", 0))
                neg = float(sig.get("retry_failed", 0)) + float(sig.get("always_ignored", 0))
                age = float(sig.get("age_days", 0))
                scores[h] = base + _sigmoid(pos - NEG_WEIGHT * neg) * _decay(age)
            return scores

        signals = await derive_signals(storage)
        scores = {}
        for h, sig in signals.items():
            pos = float(sig.get("reaccess", 0))
            neg = float(sig.get("retry_failed", 0))
            # Derived signals are treated as fresh (age 0) unless a caller
            # supplies ages; batch recompute over the live window keeps decay=1.
            scores[h] = base + _sigmoid(pos - NEG_WEIGHT * neg) * _decay(0)
        return scores
    except Exception as e:  # noqa: BLE001 - best-effort recompute
        logger.warning("recompute_quality_scores failed (non-fatal): %s", e)
        return {}


async def persist_quality_scores(
    storage,
    base: float = 0.5,
    dry_run: bool = True,
    signals_override: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Persist computed quality scores to memory metadata.

    Args:
        storage: Storage backend instance
        base: Base quality score for neutral memories
        dry_run: If True (DEFAULT), don't persist; just return statistics
        signals_override: Override signals for testing/what-if analysis

    Returns:
        Dict with statistics and results:
        - dry_run=True: {'dry_run': True, 'total': N, 'would_update': N, ...stats}
        - dry_run=False: {'dry_run': False, 'updated': N, ...stats, 'errors': N}
    """
    from ..quality.config import effective_quality
    
    try:
        # Get computed scores
        scores = await recompute_quality_scores(storage, base, signals_override)
        
        # Calculate statistics
        total = len(scores)
        if total == 0:
            return {
                'dry_run': dry_run,
                'total': 0,
                'would_update' if dry_run else 'updated': 0,
                'raised_count': 0,
                'lowered_count': 0,
                'neutral_count': 0,
                'min': None,
                'max': None,
                **({"errors": 0} if not dry_run else {})
            }
        
        score_values = list(scores.values())
        raised_count = sum(1 for s in score_values if s > base)
        lowered_count = sum(1 for s in score_values if s < base)
        neutral_count = sum(1 for s in score_values if s == base)
        min_score = min(score_values)
        max_score = max(score_values)
        
        if dry_run:
            return {
                'dry_run': True,
                'total': total,
                'would_update': total,
                'raised_count': raised_count,
                'lowered_count': lowered_count,
                'neutral_count': neutral_count,
                'min': min_score,
                'max': max_score,
            }
        
        # Persist scores to storage
        updated = 0
        errors = 0
        
        for content_hash, computed_score in scores.items():
            try:
                # Get existing user_rating from metadata using real storage interface
                user_rating = None
                memory = await storage.get_by_hash(content_hash)
                user_rating = (memory.metadata or {}).get('user_rating') if memory else None
                
                # Calculate effective quality score
                quality_score = effective_quality(computed=computed_score, user_rating=user_rating)
                
                # Update metadata
                success, _ = await storage.update_memory_metadata(
                    content_hash,
                    {
                        'computed_quality': computed_score,
                        'quality_score': quality_score
                    },
                    preserve_timestamps=True
                )
                
                if success:
                    updated += 1
                else:
                    errors += 1
                    
            except Exception as e:  # noqa: BLE001 - best-effort per-memory persist
                logger.warning("Failed to persist quality score for %s: %s", content_hash, e)
                errors += 1
        
        return {
            'dry_run': False,
            'updated': updated,
            'raised_count': raised_count,
            'lowered_count': lowered_count,
            'neutral_count': neutral_count,
            'min': min_score,
            'max': max_score,
            'errors': errors,
        }
        
    except Exception as e:  # noqa: BLE001 - best-effort operation
        logger.error("persist_quality_scores failed: %s", e)
        return {
            'dry_run': dry_run,
            'total': 0,
            'would_update' if dry_run else 'updated': 0,
            'raised_count': 0,
            'lowered_count': 0,
            'neutral_count': 0,
            'min': None,
            'max': None,
            **({"errors": 1} if not dry_run else {})
        }
