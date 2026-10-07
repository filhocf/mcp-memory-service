# ADR-0013: Resolver — importance (quality_score) breaks ties only on exact logical equality

- **Date:** 2026-10-07
- **Status:** Accepted
- **Deciders:** Claudio (owner/client), Zero (agent). Arch input: seven (Gate 1).
- **Scope:** delta-sync (#1345) Phase 2 resolver. Satisfies RFC §8.2 + refines R3.

## Context

R3 originally framed reconciliation as "timeline + importance". §8.2 sharpens this:
importance must only break a tie **when the logical order ties**, otherwise ordering is
not deterministic across hosts (quality scores can diverge). The resolver must define
exactly where importance enters.

## Decision

The resolver decides in strict order:
1. **Logical order** — `(hlc_physical, hlc_logical)`, higher wins.
2. **delete-vs-update** on equal logical order — delete wins (ADR-0012).
3. **Importance** — `quality_score` (from `metadata`, default 0.5) breaks a tie **only when
   steps 1-2 are exactly equal**; higher wins.
4. **Stable final tie-breaker** — `agent_id` then `event_id` (UUID → total order, never ties).

Importance is step 3, never earlier: it cannot override HLC order.

## Alternatives Considered

### Importance as a primary weighting factor (literal "timeline + importance") — rejected
- Non-deterministic across hosts if quality diverges; breaks convergence (two hosts could
  pick different winners). Contradicts §8.2's "only to break a logical-order tie".

### No importance, only HLC + event_id — rejected
- Ignores R3; loses the (admittedly rare) tie-break signal the owner wants.

### Importance only on exact logical tie, before event_id — CHOSEN
- Matches §8.2 verbatim; deterministic (quality is a stored, synced value, and event_id
  guarantees a final total order regardless).

## Consequences

- **Positive:** deterministic, convergent resolution; honors R3's importance intent without
  sacrificing cross-host agreement.
- **Negative:** importance rarely fires (exact HLC tie is uncommon) — acceptable; it is a
  correctness tie-breaker, not a ranking knob.
- **Source:** `quality_score` read from `metadata` (default 0.5, models/memory.py).

## References
- `docs/rfc/planned/rfc-delta-sync.md` §8.2 (R3')
- ADR-0010 (HLC), ADR-0012 (delete-vs-update)
