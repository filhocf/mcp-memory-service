# ADR-0006: Passive quality recompute ships dormant, persistence blocked until agent_id reaches retrieve()

- **Date:** 2026-10-05
- **Status:** Accepted
- **Deciders:** Claudio (owner), Zero (agent)

## Context

The learning-loop L4 (passive feedback, RFC-MM-01) needs a job that recomputes
memory quality from real usage signals instead of manual ratings (which nobody
does — ratings sat at 0 for 2 days of live telemetry). The compute machinery
already existed in `storage/usage_telemetry.py` (`derive_signals`,
`recompute_quality_scores` with `signed_sigmoid(Σpos − 2.5×Σneg) × decay`); what
was missing was persistence + scheduler wiring.

The job was implemented and gated (G0–G5, reviewer loop caught a P0: rating
preservation read via a `get_memory_metadata` branch that no real backend
implements — fixed to `get_by_hash` as the single path). Commit `14005d3f`.

A **shadow dry-run against the live DB** (24,220 memories / 16,954 usage_events)
measured the real signal before any write:

- 5,847 memories scored (~24% of the DB), 4,998 up / 538 down / 311 neutral, range −0.50..1.50.
- **But** 5,847 had `reaccess(+)` and 5,613 had `retry_failed(−)` *simultaneously*
  — near-total overlap.

Root cause: `agent_id` is `None` on the `retrieve()` hot path. Without an agent
to attribute reads to, searches from *different* sessions look like re-query
bursts of one another, inflating both positive (reaccess) and negative
(retry_failed) signals on the same hashes. The 2.5× negative weight keeps most
scores from collapsing, but the signal is **not honest merit** — it is
cross-session contamination.

## Decision

**We ship the passive recompute job dormant and do NOT persist until `agent_id`
is propagated into `retrieve()`.**

- `persist_quality_scores` defaults to `dry_run=True` (never writes).
- Scheduler wiring is opt-in: `MCP_QUALITY_RECOMPUTE_SCHEDULE` unset ⇒ no job;
  `MCP_QUALITY_RECOMPUTE_DRY_RUN` defaults to `true` even when scheduled.
- The next learning-loop step is **agent_id on retrieve()** (agent-id Phase 2),
  which is the real unblocker for honest feedback.

The Rota A choice (dry-run shadow first) did its job: a cheap measurement
revealed the bottleneck is `agent_id`, not the computation.

## Alternatives Considered

### Persist now (enable dry_run=false)
- **Pros:** closes the loop end-to-end today; starts moving quality off the 0.5 flat.
- **Cons:** persists machine scores built on contaminated signal — would push
  ~4,998 memories up on cross-session noise, corrupting ranking and
  archive-candidate selection across 24k memories.
- **Reversibility:** low — mass metadata writes; even with `original_quality`
  kept, undoing a bad distribution is painful.

### Fix agent_id on retrieve() first, then persist — CHOSEN sequencing
- **Pros:** feedback becomes honest ("the same line of work reused X"); retry
  stops self-contaminating; the job is already built and waiting.
- **Cons:** one more step before the loop visibly closes.
- **Reversibility:** high — the dormant job changes nothing until explicitly enabled.

## Consequences

- **Positive:** no bad data written; the job is proven (gate + shadow) and
  ready to flip on once the signal is trustworthy. Blast radius controlled by
  dual defaults (dry-run + opt-in).
- **Negative / cost:** L4 does not yet move quality scores; the 1-week window
  (N1) measures telemetry/injection, not persisted feedback, until agent_id lands.
- **Neutral / follow-up:** `rfc-agent-id-multi-agent.md` sits in `implemented/`
  with 12 EARS, but the retrieve() path (Phase 2) appears not delivered — a G0
  must confirm scope before coding the next step. `tracker.py` remains dead code
  (schema-incompatible); not revived.

## References

- `docs/rfc/planned/rfc-mm-01-feedback-loop.md` (the passive-feedback design)
- `docs/rfc/planned/rfc-learning-loop.md` §11 (negative signal first), §5 R3/R4
- `docs/adr/0003-learning-input-is-real-usage.md` (usage is the source of truth)
- `docs/adr/0005-agent-assertiveness-metric.md`
- commit `14005d3f` (feat: passive quality recompute job, dormant)
- `src/mcp_memory_service/storage/usage_telemetry.py` (`persist_quality_scores`)
- `src/mcp_memory_service/consolidation/scheduler.py` (`_run_quality_recompute`)
