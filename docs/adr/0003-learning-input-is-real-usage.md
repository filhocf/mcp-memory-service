# ADR-0003: Learning input is real usage, not structured session fields

- **Date:** 2026-10-04
- **Status:** Accepted
- **Deciders:** Claudio (owner), Zero (agent)

## Context

The learning pipeline needs a source of truth for *what it learns from*. Two models
coexisted in the RFCs:
- `rfc-self-service-memory-intelligence` (earlier generation) assumes
  `commit_session_legacy` with **structured fields** — the upstream design.
- `rfc-autolearn-autodream §1.3` diagnoses the mismatch directly: *"The upstream system
  was designed for `commit_session_legacy` with structured fields. We use `memory_store`
  with free text + tags. The bootstrap looks for fields we never fill."*

This is not theory — it is a diagnosed bug: the upstream learning path expects structured
data we never produce. The telemetry built on 3/out (`usage_events`) already observes real
`memory_search`/`retrieve` activity, i.e. it is already on the correct side.

## Decision

The source of truth for learning input is **real usage**: `memory_store` free-text + tags,
JSONL session transcripts, and `usage_events` (retrieval/feedback telemetry). We **abandon
the `commit_session_legacy` structured-field premise** as the basis for learning. The
learning-loop (umbrella RFC) states this as canonical. This unblocks RFC-MM-01 (passive
feedback): it recalibrates quality from real usage signals, not from a phantom schema.

## Alternatives Considered

### Keep the structured `commit_session_legacy` model (upstream default)
- **Pros:** aligns with upstream; richer typed fields.
- **Cons:** we never populate those fields; bootstrap reads emptiness; proven mismatch.
- **Reversibility:** easy to keep, but it's dead weight.

### Learn from real usage (free text + JSONL + usage_events) — CHOSEN
- **Pros:** works with what we actually produce; telemetry already captures it.
- **Cons:** less structure → distillation must extract structure (that's fact-extraction's job).
- **Reversibility:** high — additive on top of existing signals.

## Consequences

- **Positive:** RFC-MM-01 unblocked; the 3/out telemetry is validated as the right path.
- **Negative / cost:** distillation (L2) carries the burden of imposing structure.
- **Neutral / follow-up:** `commit_session_legacy` is not removed (upstream compat), just
  not relied upon as the learning input.

## References

- `docs/rfc/planned/rfc-autolearn-autodream.md` §1.3 (the diagnosis)
- `docs/rfc/planned/rfc-mm-01-feedback-loop.md` (unblocked)
- `docs/rfc/planned/rfc-learning-loop.md` (umbrella — crava the truth source)
- `src/mcp_memory_service/storage/usage_telemetry.py` (already real-usage based)
