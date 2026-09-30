"""Tests for session value triage (harvest/triage.py).

Golden cases derived from the real Kiro archive validated in RFC
ingestão-multi-agente §8 (camada C3a). Uses synthetic JSONL fixtures that
reproduce the payload-wrapped Kiro format, so tests are hermetic.
"""

import json
from pathlib import Path

import pytest

from mcp_memory_service.harvest.triage import (
    DEFAULT_THRESHOLD,
    TriageResult,
    score_session,
    session_uuid,
    triage_sessions,
    triage_threshold_from_env,
)


def _write_session(tmp_path: Path, name: str, records: list) -> Path:
    """Write a payload-wrapped Kiro messages.jsonl under {name}/messages.jsonl."""
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    f = d / "messages.jsonl"
    with f.open("w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return f


def _user(text):
    return {"payload": {"type": "user", "content": text}}


def _assistant(text):
    return {"payload": {"type": "assistant", "content": text}}


def _meta():
    return {"payload": {"type": "session_metadata"}}


PROSE = "x" * 400  # a block above PROSE_MIN_CHARS


# --- label / verdict per validated case ---

def test_gold_dense_conversation_is_kept(tmp_path):
    recs = [_meta()]
    for i in range(6):
        recs += [_user(f"pergunta real {i} " + PROSE), _assistant("resposta " + PROSE)]
    r = score_session(_write_session(tmp_path, "sess_gold", recs))
    assert r.label == "gold"
    assert r.verdict == "keep"
    assert r.score >= DEFAULT_THRESHOLD


def test_short_real_conversation_with_reply_is_kept(tmp_path):
    # Two-axis rule: short but real (has an assistant reply) → keep, not "test".
    recs = [_user("kiro, consegue acompanhar o contexto do haCARthon? " + PROSE),
            _assistant("Sim, aqui está o contexto " + PROSE)]
    r = score_session(_write_session(tmp_path, "sess_conv", recs))
    assert r.label == "conversation"
    assert r.is_test is False
    assert r.verdict == "keep"


def test_test_signature_is_dropped(tmp_path):
    recs = [_user("respond with just 'hello v3'"), _assistant("hello v3")]
    r = score_session(_write_session(tmp_path, "sess_test", recs))
    assert r.label == "test"
    assert r.is_test is True
    assert r.verdict == "drop"


def test_truncated_session_is_dropped(tmp_path):
    # Real prompt, but the session died before any assistant reply.
    recs = [_user("qual é seu nome e que hooks você detecta ativos?"),
            {"payload": {"type": "tool_call"}},
            {"payload": {"type": "tool_result", "content": "{}"}}]
    r = score_session(_write_session(tmp_path, "sess_trunc", recs))
    assert r.label == "truncated"
    assert r.verdict == "drop"


def test_empty_session_is_dropped(tmp_path):
    recs = [_meta(), {"payload": {"type": "session_start"}}]
    r = score_session(_write_session(tmp_path, "sess_empty", recs))
    assert r.label == "empty"
    assert r.score == 0.0
    assert r.verdict == "drop"


def test_volumetric_dump_is_dropped(tmp_path):
    # A single 600k-char tool_result block is noise, not prose.
    recs = [_user("Just say AVAILABLE"),
            {"payload": {"type": "tool_result", "content": "x" * 600_000}}]
    r = score_session(_write_session(tmp_path, "sess_dump", recs))
    assert r.label == "dump"
    assert r.verdict == "drop"


# --- language-agnostic (RC3.10) ---

def test_language_is_not_a_value_signal(tmp_path):
    # An English real conversation must score the same as a Portuguese one.
    pt = [_user("me ajuda a debugar isso " + PROSE), _assistant("claro " + PROSE)]
    en = [_user("help me debug this " + PROSE), _assistant("sure " + PROSE)]
    r_pt = score_session(_write_session(tmp_path, "sess_pt", pt))
    r_en = score_session(_write_session(tmp_path, "sess_en", en))
    assert r_pt.score == r_en.score
    assert r_pt.verdict == r_en.verdict == "keep"


# --- threshold calibration ---

def test_threshold_is_tunable(tmp_path):
    recs = [_user("pergunta " + PROSE), _assistant("resposta " + PROSE)]  # 1 reply → mid score
    f = _write_session(tmp_path, "sess_mid", recs)
    low = score_session(f, threshold=0.05)
    high = score_session(f, threshold=0.95)
    assert low.score == high.score          # score is stable
    assert low.verdict == "keep"            # same session, different cut
    assert high.verdict == "drop"


def test_threshold_from_env(monkeypatch):
    monkeypatch.setenv("MCP_HARVEST_TRIAGE_THRESHOLD", "0.5")
    assert triage_threshold_from_env() == 0.5
    monkeypatch.setenv("MCP_HARVEST_TRIAGE_THRESHOLD", "not-a-number")
    assert triage_threshold_from_env() == DEFAULT_THRESHOLD


# --- dedup by session_uuid (sync mirrors across workspace hashes) ---

def test_session_uuid_extraction():
    assert session_uuid(Path("/x/6b82/sess_af1e7b9c-1234-4000-8000-abcdef012345/messages.jsonl")) \
        == "af1e7b9c-1234-4000-8000-abcdef012345"
    assert session_uuid(Path("/x/hash/0d74b7e7-4b7a-402c-8ae0-f5e423de6f39/messages.jsonl")) \
        == "0d74b7e7-4b7a-402c-8ae0-f5e423de6f39"


def test_triage_dedup_by_uuid_and_skips_sync_dupes(tmp_path):
    recs = [_user("pergunta " + PROSE), _assistant("resposta " + PROSE)]
    # same uuid mirrored under two hashes + a "(2)" sync dupe
    _write_session(tmp_path / "hashA", "sess_dup-1234-4000-8000-abcdef012345", recs)
    big = _write_session(tmp_path / "hashB", "sess_dup-1234-4000-8000-abcdef012345",
                         recs + [_assistant("extra " + PROSE)])
    (tmp_path / "hashC").mkdir()
    (tmp_path / "hashC" / "messages (2).jsonl").write_text("{}\n")
    results = triage_sessions(list(tmp_path.rglob("messages*.jsonl")))
    ids = [r.session_id for r in results]
    assert ids.count("dup-1234-4000-8000-abcdef012345") == 1   # deduped
    assert all("(2)" not in str(r.session_id) for r in results)
