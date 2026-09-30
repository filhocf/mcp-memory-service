# Spec: §6 Anti-Hallucination (Belief Quarantine + LLM NLI)

**Date:** 2026-06-01
**Branch:** `feat/rfc1-s6-anti-hallucination` (create from `feat/rfc1-s2-belief-store`)
**Repo:** `~/git/mcp-memory-service`
**Depends on:** §2 Belief Store (branch `feat/rfc1-s2-belief-store`)
**Refs:** RFC #1 (Codeberg issue #1), reasoning/nli.py (existing), consolidation/contradictions.py (existing)

---

## Context

We already have:
- `NLIClassifier` with heuristic backend (negation pairs, version conflicts) — max confidence 0.6
- `detect_contradictions_nli` 4-stage pipeline (entity overlap → embedding band → NLI → conflict registration)
- `check_contradiction_on_store` in consolidation/contradictions.py (similarity band only)
- `MCP_NLI_ON_STORE=true` integration in server/handlers/memory.py
- Scheduler running contradiction check every 6h

What's missing:
1. **LLM backend for NLI** — use existing provider chain (deepseek→groq→ollama) for higher accuracy
2. **Belief quarantine** — when contradiction involves a belief, set `belief_status=quarantine`
3. **Quarantine resolution** — expose via `memory_conflicts` tool for manual resolution

---

## 1. LLM NLI Backend

In `src/mcp_memory_service/reasoning/nli.py`, add LLM backend to `NLIClassifier`:

```python
async def _llm_classify(self, premise: str, hypothesis: str) -> NLIResult:
    """Use LLM provider chain for NLI classification."""
    from ..harvest.rewriter import HarvestRewriter

    prompt = (
        "Classify the relationship between these two statements:\n\n"
        f"Statement A: {premise[:500]}\n"
        f"Statement B: {hypothesis[:500]}\n\n"
        "Answer with EXACTLY one word: entailment, contradiction, or neutral.\n"
        "- entailment: B follows from or agrees with A\n"
        "- contradiction: B conflicts with or negates A\n"
        "- neutral: B is unrelated to A\n\n"
        "Answer:"
    )

    rewriter = HarvestRewriter()
    response = await rewriter._call_llm(prompt)
    response = response.strip().lower()

    if "contradiction" in response:
        return NLIResult(label="contradiction", confidence=0.85)
    elif "entailment" in response:
        return NLIResult(label="entailment", confidence=0.80)
    else:
        return NLIResult(label="neutral", confidence=0.5)
```

Backend selection in `classify()`:
```python
async def classify(self, premise: str, hypothesis: str) -> NLIResult:
    if self.backend == "heuristic":
        return self._heuristic_classify(premise, hypothesis)
    elif self.backend == "llm":
        return await self._llm_classify(premise, hypothesis)
    elif self.backend == "cascade":
        # Heuristic first; if neutral, escalate to LLM
        heuristic = self._heuristic_classify(premise, hypothesis)
        if heuristic.label != "neutral" and heuristic.confidence >= 0.5:
            return heuristic
        return await self._llm_classify(premise, hypothesis)
    # ... existing fallback
```

Config: `MCP_NLI_BACKEND` accepts `heuristic` (default), `llm`, or `cascade`.

---

## 2. Belief Quarantine Integration

In `src/mcp_memory_service/reasoning/nli.py`, modify `detect_contradictions_nli` Stage 4:

After registering the conflict, check if either memory is a belief and quarantine it:

```python
# Stage 4 addition: quarantine beliefs involved in contradictions
if not dry_run and contradictions:
    for h, mem_b_data, nli_res in contradictions:
        # ... existing conflict registration ...

        # Quarantine beliefs involved in contradiction
        for check_hash in (memory_hash, h):
            try:
                mem = await storage.get_by_hash(check_hash)
                if mem and mem.memory_type == "belief":
                    meta = mem.metadata or {}
                    if meta.get("belief_status") != "quarantine":
                        await storage.update_memory_metadata(
                            check_hash,
                            {"belief_status": "quarantine", "quarantine_reason": f"contradiction with {h[:12] if check_hash == memory_hash else memory_hash[:12]}"}
                        )
                        result["beliefs_quarantined"] = result.get("beliefs_quarantined", 0) + 1
            except Exception as e:
                logger.debug(f"Failed to quarantine belief: {e}")
```

Also add to `check_contradiction_on_store` in `consolidation/contradictions.py`:

```python
# After marking superseded, also quarantine if belief
if candidate.get("type") == "belief" or candidate.get("memory_type") == "belief":
    await storage.update_memory_metadata(
        cand_hash,
        {"belief_status": "quarantine", "quarantine_reason": f"superseded by {content_hash[:12]}"}
    )
```

---

## 3. Quarantine Visibility in memory_conflicts

In `server_impl.py` `handle_memory_conflicts`, add quarantined beliefs section:

```python
# After existing conflict listing, add quarantined beliefs
quarantined = await self.memory_service.list_memories(
    page=1, page_size=20, memory_type="belief"
)
quarantined_beliefs = [
    m for m in quarantined.get("memories", [])
    if (m.get("metadata") or {}).get("belief_status") == "quarantine"
]
if quarantined_beliefs:
    lines.append(f"\n🔒 Quarantined beliefs ({len(quarantined_beliefs)}):")
    for b in quarantined_beliefs:
        meta = b.get("metadata") or {}
        lines.append(f"  - {b['content'][:80]} (reason: {meta.get('quarantine_reason', '?')})")
```

---

## 4. Quarantine Resolution via memory_resolve

Extend `handle_memory_resolve` to accept `action="unquarantine"`:

```python
# In handle_memory_resolve, add unquarantine action
action = arguments.get("action")
if action == "unquarantine":
    content_hash = arguments.get("content_hash")
    await self.storage.update_memory_metadata(
        content_hash,
        {"belief_status": "active", "quarantine_reason": None}
    )
    return [types.TextContent(type="text", text=f"Belief {content_hash[:12]} restored to active.")]
```

---

## Files Affected

- `src/mcp_memory_service/reasoning/nli.py` — add LLM backend + cascade mode + belief quarantine in Stage 4 (~60 lines)
- `src/mcp_memory_service/consolidation/contradictions.py` — quarantine beliefs in `check_contradiction_on_store` (~10 lines)
- `src/mcp_memory_service/server_impl.py` — quarantined beliefs in `handle_memory_conflicts` + unquarantine in `handle_memory_resolve` (~25 lines)
- `tests/test_anti_hallucination.py` — new test file (~120 lines)

**Total: ~215 lines of code + ~120 lines of tests**

---

## Validation

```bash
.venv/bin/python -m pytest tests/test_anti_hallucination.py tests/test_belief_store.py -x -q --timeout=120
```

Integration test scenarios:
1. Store two contradicting memories → NLI detects → conflict registered
2. Store memory contradicting a belief → belief quarantined
3. `memory_conflicts` shows quarantined beliefs
4. `memory_resolve(action="unquarantine")` restores belief
5. Quarantined belief does NOT appear in bootstrap profile
6. Cascade mode: heuristic catches obvious contradiction (no LLM call)
7. Cascade mode: heuristic neutral → LLM escalation detects contradiction

---

## Commit Strategy

1. `feat(nli): add LLM backend and cascade mode to NLIClassifier`
2. `feat(nli): quarantine beliefs on contradiction detection`
3. `feat(conflicts): show quarantined beliefs + unquarantine action`
4. `test(anti-hallucination): integration tests for quarantine pipeline`

---

## Config Summary

| Env var | Default | Description |
|---------|---------|-------------|
| `MCP_NLI_ENABLED` | `false` | Master kill-switch for NLI pipeline |
| `MCP_NLI_ON_STORE` | `false` | Run NLI check on every memory_store |
| `MCP_NLI_BACKEND` | `heuristic` | `heuristic`, `llm`, or `cascade` |
| `MCP_NLI_CONFIDENCE_THRESHOLD` | `0.4` | Min confidence to register conflict |

Recommended production config:
```env
MCP_NLI_ENABLED=true
MCP_NLI_ON_STORE=true
MCP_NLI_BACKEND=cascade
MCP_NLI_CONFIDENCE_THRESHOLD=0.5
```
