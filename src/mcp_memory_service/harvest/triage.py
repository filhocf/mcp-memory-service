"""Session value triage — score a session's harvest-worth BEFORE parsing/LLM.

A cheap O(n), LLM-free gate that separates real conversations from parking
tickets (smoke tests, dead sessions, tool dumps). Validated empirically against
a real Kiro archive (RFC ingestão-multi-agente §8, camada C3a): 51 sessions →
~78% discarded at threshold 0.25, with a natural score valley at 0.2–0.55.

Design invariants (from RC3.5–RC3.10):
- Two independent axes: is-it-a-test? (prompt signature) ⊕ has-content?
  (a substantive assistant reply). Discard only test-signature OR no-content —
  never merely for being short.
- Continuous 0–1 score with a tunable threshold (mirrors HARVEST_MIN_CONFIDENCE).
- LANGUAGE-AGNOSTIC: language is not a value signal (it does not generalize
  across operators). Only prompt intent + reply density decide value.

This module is a per-agent profile hook for the Kiro grammar. Other agents plug
their own signatures; the scoring shape stays the same.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# --- Kiro grammar (payload.type) — the per-agent piece ---
CONVERSATION_TYPES = {"user", "assistant"}
SUBAGENT_TYPES = {"sub_agent_start", "sub_agent_complete"}

# Mechanical test/smoke-prompt signatures (LANGUAGE-AGNOSTIC intent, not idiom).
# A prompt matching these is a command-to-test, not a real question/request.
TEST_SIGNATURE = re.compile(
    r"^(hello|hi)\b|^hello v\d|^respond with|^echo |^turn \d+\s*:|"
    r"^run a shell command:\s*echo|^list all (tools|mcp)|^list your |"
    r"^store in memory:\s*.(v3|test|resume)|test marker|"
    r"^do you remember the .*(marker|test)|^use the tool_search|"
    r"^what.?s? (is )?your (current )?session id|^what steering files|"
    r"^what agent are you",
    re.IGNORECASE,
)

PROSE_MIN_CHARS = 200          # a user/assistant block above this counts as prose
DUMP_MAX_CHARS = 500_000       # a single block above this is a tool dump (noise)
DEFAULT_THRESHOLD = 0.25       # tunable cut; validated valley at 0.2–0.55


@dataclass
class TriageResult:
    """Value triage of a single session."""
    session_id: str
    score: float
    verdict: str                       # "keep" | "drop"
    label: str                         # gold | conversation | test | truncated | empty | dump
    assistant_prose: int = 0
    user_prose: int = 0
    has_subagent: bool = False
    is_test: bool = False
    max_block_chars: int = 0
    first_prompt: str = ""


def session_uuid(path: Path) -> str:
    """Stable session id from a Kiro path (dedup key — sync mirrors across hashes)."""
    for part in reversed(path.parts):
        if part.startswith("sess_"):
            return part[5:]
        if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{27,}", part):
            return part
    return str(path)


def _real_prompt(content: str) -> str:
    """The user's real utterance = last non-empty line (strips embedded steering)."""
    lines = [ln for ln in content.splitlines() if ln.strip()]
    return lines[-1].strip() if lines else content.strip()


def score_session(path: Path, threshold: float = DEFAULT_THRESHOLD) -> TriageResult:
    """Compute the 0–1 value score and verdict for one session file."""
    users: List[str] = []
    asst_prose = user_prose = 0
    has_sub = False
    max_block = 0

    for line in path.open(errors="ignore"):
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        pl = obj.get("payload") or {}
        ptype = pl.get("type")
        content = pl.get("content")
        if ptype in SUBAGENT_TYPES:
            has_sub = True
        if isinstance(content, str):
            max_block = max(max_block, len(content))
        if ptype == "user" and isinstance(content, str):
            users.append(_real_prompt(content))
            if PROSE_MIN_CHARS < len(content) < DUMP_MAX_CHARS:
                user_prose += 1
        elif ptype == "assistant" and isinstance(content, str):
            if PROSE_MIN_CHARS < len(content) < DUMP_MAX_CHARS:
                asst_prose += 1

    is_test = bool(users) and all(TEST_SIGNATURE.search(u) for u in users if u)

    # --- continuous score (all O(n), language-agnostic) ---
    score = 0.0
    score += min(asst_prose, 10) * 0.09     # substantive replies: up to +0.9
    score += min(user_prose, 5) * 0.03      # substantive prompts: up to +0.15
    if has_sub:
        score += 0.15                        # subagent work = real
    if max_block >= DUMP_MAX_CHARS:
        score -= 0.5                         # tool dump
    if not any(users) and asst_prose == 0:
        score -= 1.0                         # empty (session death, no conversation)
    if users and asst_prose == 0:
        score -= 0.4                         # truncated (real prompt, session died pre-reply)
    if is_test:
        score -= 0.6                         # mechanical test signature
    score = max(0.0, min(1.0, score))

    # Floor for genuine short conversations (RC3.5, operator's "don't lose
    # knowledge" priority): a non-test session with at least one substantive
    # assistant reply is real conversation — a single short turn must not fall
    # below the keep line just for being brief. Tests/truncated/dumps are
    # unaffected (they have is_test / no reply / oversized block).
    if not is_test and asst_prose >= 1 and max_block < DUMP_MAX_CHARS:
        score = max(score, DEFAULT_THRESHOLD)

    # --- label (preserves judgment; verdict follows the score) ---
    if not any(users) and asst_prose == 0:
        label = "empty"
    elif max_block >= DUMP_MAX_CHARS:
        label = "dump"
    elif is_test:
        label = "test"
    elif users and asst_prose == 0:
        label = "truncated"
    elif asst_prose >= 5 or has_sub:
        label = "gold"
    else:
        label = "conversation"

    return TriageResult(
        session_id=session_uuid(path),
        score=score,
        verdict="keep" if score >= threshold else "drop",
        label=label,
        assistant_prose=asst_prose,
        user_prose=user_prose,
        has_subagent=has_sub,
        is_test=is_test,
        max_block_chars=max_block,
        first_prompt=(users[0][:60] if users else ""),
    )


def triage_threshold_from_env(default: float = DEFAULT_THRESHOLD) -> float:
    """Read MCP_HARVEST_TRIAGE_THRESHOLD (tunable cut); invalid values ignored."""
    raw = os.environ.get("MCP_HARVEST_TRIAGE_THRESHOLD")
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            pass
    return default


def triage_sessions(paths: List[Path], threshold: Optional[float] = None) -> List[TriageResult]:
    """Score a list of session files, deduplicated by session_uuid (keep largest)."""
    if threshold is None:
        threshold = triage_threshold_from_env()
    by_uuid: Dict[str, Path] = {}
    for p in paths:
        if "(2)" in p.name:              # sync-conflict duplicate
            continue
        u = session_uuid(p)
        if u not in by_uuid or p.stat().st_size > by_uuid[u].stat().st_size:
            by_uuid[u] = p
    return [score_session(p, threshold) for p in by_uuid.values()]
