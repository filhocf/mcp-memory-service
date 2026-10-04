# ADR-0004: Working-memory reuses memory_context (single injection path)

- **Date:** 2026-10-04
- **Status:** Accepted
- **Deciders:** Claudio (owner), Zero (agent)

## Context

Two paths exist for "bring relevant context to the agent without it asking":
- `memory_context(task)` tool (built 3/out): given a theme, injects relevant beliefs
  ranked by relevance × confidence, token-budgeted, logs an `injection` event.
  It is a **push-by-demand event** (called with a theme).
- `rfc-working-memory` (planned): a **runtime tier** with lifecycle — hot tier with TTL,
  continuous auto-inject, and working→episodic promotion by reinforcement.

They are not duplicates: `memory_context` is an *event* ("how to fetch the relevant"),
working-memory is a *layer* ("what to keep hot, when, and how it graduates"). Risk: if
working-memory builds its own injection mechanism from scratch, it duplicates
`memory_context`.

## Decision

Working-memory will **reuse `memory_context` as the injection primitive** and add only
what is missing: the TTL hot tier, continuous auto-inject, and promotion-by-reinforcement.
No second injection path. Furthermore, working-memory's **promotion signal** (a memory
re-accessed/reinforced rises) is the **same signal** as RFC-MM-01's passive-feedback usage
signal — they are one engine, not two.

## Alternatives Considered

### Working-memory builds its own injection
- **Pros:** self-contained.
- **Cons:** duplicates `memory_context`; two injection code paths to maintain and reconcile.
- **Reversibility:** low once two paths exist.

### Reuse memory_context + add tier/promotion only — CHOSEN
- **Pros:** one injection path; promotion signal shared with feedback-loop (one engine).
- **Cons:** working-memory depends on memory_context's contract (acceptable — it's ours).
- **Reversibility:** high.

## Consequences

- **Positive:** no duplicate injection; usage signal unified across L3 (injection),
  L4 (feedback), and working-memory promotion.
- **Negative / cost:** memory_context must stay stable as a primitive (contract discipline).
- **Neutral / follow-up:** when working-memory is specced, its spec references this ADR
  and the memory_context contract.

## References

- `src/mcp_memory_service/storage/context_injection.py` (memory_context, the primitive)
- `docs/rfc/planned/rfc-working-memory.md` (the tier to build on top)
- `docs/rfc/planned/rfc-mm-01-feedback-loop.md` (shared usage signal)
