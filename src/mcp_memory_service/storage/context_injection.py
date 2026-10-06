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
Proactive, theme-based context injection: memory_context(storage, task).

Today's bootstrap injects the top-N GLOBAL active beliefs (blind, no theme
filter). This module instead ranks beliefs by RELEVANCE-TO-THEME x CONFIDENCE,
stays within a token budget, and records an 'injection' usage event.

Design decisions (mirror usage_telemetry.py — module-level async functions that
take `storage`):
- Killswitch: MCP_CONTEXT_INJECTION_ENABLED (default ON; 'false'/'0'/'no' off).
- Budget: MCP_CONTEXT_MAX_TOKENS default 2048; budget_tokens overrides.
- Telemetry: respects MCP_USAGE_TELEMETRY via log_usage_event (best-effort).

Relevance measurement is honest and embedding-free at its core:
- Primary signal: term overlap between the task and each belief's content.
- Semantic boost (when available): storage.retrieve(task) returns related
  memories with relevance_score; beliefs whose content overlaps those memories
  get a small boost. When no embedding model is available retrieve() returns []
  and we fall back to top-N by confidence (relevance uniform -> pure confidence
  ordering).
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Values that disable injection (case-insensitive). Everything else -> enabled.
_DISABLED_VALUES = {"false", "0", "no"}

# Default token budget when neither budget_tokens nor env override is set.
_DEFAULT_MAX_TOKENS = 2048

# Rough chars-per-token heuristic for budget accounting.
_CHARS_PER_TOKEN = 4

# Candidate floor: pull low-confidence beliefs too so a theme-relevant but
# lower-confidence belief can still be surfaced by the ranker.
_CANDIDATE_MIN_CONFIDENCE = 0.0

# How many related memories to pull for the semantic relevance boost.
_RETRIEVE_N = 50

_WORD_RE = re.compile(r"[a-z0-9]+")

# Very common tokens that carry little thematic signal; dropped from overlap.
_STOPWORDS = {
    "the", "a", "an", "to", "of", "for", "in", "on", "and", "or", "how",
    "should", "i", "configure", "my", "is", "are", "with", "at", "by", "it",
    "this", "that", "be", "as", "do", "does",
}


def get_context_injection_flag() -> bool:
    """Return whether proactive context injection is enabled.

    Default ON. Only 'false', '0', or 'no' (case-insensitive, trimmed) disable it.
    """
    raw = os.environ.get("MCP_CONTEXT_INJECTION_ENABLED")
    if raw is None:
        return True
    return raw.strip().lower() not in _DISABLED_VALUES


def _effective_budget(budget_tokens: Optional[int]) -> int:
    """Resolve the effective token budget."""
    if budget_tokens is not None:
        return int(budget_tokens)
    raw = os.environ.get("MCP_CONTEXT_MAX_TOKENS")
    if raw:
        try:
            return int(raw)
        except (TypeError, ValueError):
            logger.warning("Invalid MCP_CONTEXT_MAX_TOKENS=%r; using default", raw)
    return _DEFAULT_MAX_TOKENS


def _tokenize(text: str) -> List[str]:
    """Lowercase word tokens with stopwords removed."""
    if not text:
        return []
    return [t for t in _WORD_RE.findall(text.lower()) if t not in _STOPWORDS]


def _overlap_relevance(task_terms: set, content: str) -> float:
    """Term-overlap relevance in [0, 1]: fraction of task terms present in content."""
    if not task_terms:
        return 0.0
    content_terms = set(_tokenize(content))
    if not content_terms:
        return 0.0
    hits = len(task_terms & content_terms)
    return hits / len(task_terms)


async def _semantic_terms(storage, task: str) -> set:
    """Collect terms from memories semantically related to the task.

    Returns an empty set when no embedding model is available (retrieve() -> [])
    or on any failure. Used only as a soft boost over term-overlap.
    """
    try:
        results = await storage.retrieve(task, n_results=_RETRIEVE_N)
    except Exception as e:  # noqa: BLE001 - best-effort boost
        logger.debug("context_injection: retrieve() failed (non-fatal): %s", e)
        return set()

    terms: set = set()
    for r in results or []:
        try:
            mem = getattr(r, "memory", None)
            content = getattr(mem, "content", None) if mem is not None else None
            if content is None and isinstance(r, dict):
                content = r.get("content")
            if content:
                terms.update(_tokenize(content))
        except Exception:
            continue
    return terms


async def memory_context(
    storage,
    task: str,
    budget_tokens: Optional[int] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Return theme-relevant beliefs for a task, ranked, budgeted, and logged.

    Result dict:
        items:   [ {content, confidence, relevance, belief_hash}, ... ]
        beliefs: alias of items (all injected items are beliefs here)
        truncated: bool  (True when the budget forced a cut)
        injected:  bool  (False when killswitch off)
        belief_hashes: [...]
        count: int
        budget_tokens: int
    """
    budget = _effective_budget(budget_tokens)

    # Killswitch off -> noop.
    if not get_context_injection_flag():
        return {
            "items": [],
            "beliefs": [],
            "truncated": False,
            "injected": False,
            "belief_hashes": [],
            "count": 0,
            "budget_tokens": budget,
        }

    # Fetch candidate beliefs (low confidence floor so the ranker, not a blind
    # confidence cutoff, decides what surfaces).
    beliefs: List[dict] = []
    try:
        from ..consolidation.belief_service import BeliefService

        service = BeliefService(storage)
        beliefs = await service.get_beliefs(
            status="active", min_confidence=_CANDIDATE_MIN_CONFIDENCE
        )
    except Exception as e:  # noqa: BLE001 - never break on belief fetch
        logger.warning("context_injection: get_beliefs failed (non-fatal): %s", e)
        beliefs = []

    task_terms = set(_tokenize(task))

    # Thematic ranking requires an embedding model to be available. When it is
    # absent (REQ-7), similarity is unavailable and we must fall back to pure
    # top-N-by-confidence ordering (relevance uniform).
    embedding_available = getattr(storage, "embedding_model", None) is not None
    semantic_terms = await _semantic_terms(storage, task) if embedding_available else set()

    scored: List[Dict[str, Any]] = []
    for b in beliefs:
        content = b.get("content", "") or ""
        confidence = b.get("confidence", 0.0) or 0.0

        if embedding_available:
            # Theme-aware relevance: term overlap between the task and the
            # belief, nudged by overlap with semantically related memories.
            overlap = _overlap_relevance(task_terms, content)
            boost = 0.0
            if semantic_terms:
                content_terms = set(_tokenize(content))
                if content_terms:
                    boost = len(content_terms & semantic_terms) / len(content_terms)
            relevance = min(1.0, overlap + 0.25 * boost)
        else:
            # No embedding model -> pure confidence fallback.
            relevance = 1.0

        scored.append(
            {
                "content": content,
                "confidence": confidence,
                "relevance": relevance,
                "belief_hash": b.get("belief_hash"),
            }
        )

    # Fallback: if the thematic signal matched nothing at all, don't zero out
    # the whole set — rank purely by confidence instead.
    if scored and all(s["relevance"] == 0.0 for s in scored):
        for s in scored:
            s["relevance"] = 1.0

    # Order by combined relevance x confidence (desc), then confidence as a
    # stable tiebreaker.
    scored.sort(key=lambda s: (s["relevance"] * s["confidence"], s["confidence"]), reverse=True)

    # Apply explicit item limit first.
    if limit is not None:
        scored = scored[: int(limit)]

    # Budget: keep items while concatenated content stays within budget chars.
    budget_chars = budget * _CHARS_PER_TOKEN
    selected: List[Dict[str, Any]] = []
    used = 0
    truncated = False
    for item in scored:
        piece = len(item["content"])
        addition = piece if not selected else piece + 1  # +1 for the join space
        if selected and used + addition > budget_chars:
            truncated = True
            break
        selected.append(item)
        used += addition

    # If even the first item overflows, keep it (one item minimum) but flag the
    # cut so the caller knows the budget was exceeded by the single top pick.
    if not selected and scored:
        selected = [scored[0]]
        if len(scored[0]["content"]) > budget_chars:
            truncated = True
        if len(scored) > 1:
            truncated = True
    elif truncated is False and len(selected) < len(scored):
        truncated = True

    belief_hashes = [s["belief_hash"] for s in selected if s.get("belief_hash")]
    count = len(selected)

    # Best-effort injection telemetry.
    try:
        from .usage_telemetry import log_usage_event, resolve_telemetry_agent_id

        await log_usage_event(
            storage,
            "injection",
            n_results=count,
            agent_id=resolve_telemetry_agent_id(),
            metadata=json.dumps(
                {"belief_hashes": belief_hashes, "count": count}
            ),
        )
    except Exception as e:  # noqa: BLE001 - telemetry is best-effort
        logger.warning("context_injection: injection event log failed (non-fatal): %s", e)

    return {
        "items": selected,
        "beliefs": selected,
        "truncated": truncated,
        "injected": True,
        "belief_hashes": belief_hashes,
        "count": count,
        "budget_tokens": budget,
    }
