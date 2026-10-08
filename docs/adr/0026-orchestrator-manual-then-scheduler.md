# ADR-0026: Orchestrator is manually invokable first; scheduler is a separate later slice

- **Date:** 2026-10-07
- **Status:** Accepted
- **Deciders:** Claudio (owner/client), Zero (agent). Arch input: seven (Gate 1).
- **Scope:** delta-sync (#1345) Phase 4b. RFC §7.

## Context

The pull orchestrator (`sync_from_peer`) needs a trigger. Options: run it inside the
existing `_sync_loop`, add a scheduler now, or make it a plain callable first.

## Decision

`sync_from_peer` is a **plain awaitable method, invoked manually** in Phase 4b — fully
testable and deterministic in a gate (no timing, no background task). A scheduler is a
**separate later slice (4d)**: a thin wrapper calling `sync_with_peer` on its own interval
(`SYNC_PEER_INTERVAL`), decoupled from `HYBRID_SYNC_INTERVAL`, and NOT reusing
`_sync_loop` (ADR-0023).

## Alternatives Considered

### Add the scheduler now — rejected
- Mixes "does the pull work correctly" with "runs periodically in the background" — two
  concerns, harder to test deterministically. Scheduler value is low until pull is proven.

### Run inside `_sync_loop` — rejected (ADR-0023)
- Fuses the two sync mechanisms; forbidden by RFC §7.

### Manual callable first, scheduler later — CHOSEN
- The orchestration logic is proven in isolation; the scheduler becomes a trivial wrapper.

## Consequences

- **Positive:** deterministic gate testing; clean separation of logic vs scheduling.
- **Negative:** no automatic periodic sync until 4d — acceptable; a client can call
  `sync_from_peer` explicitly, and the hot E2E exercises it directly.

## References
- `docs/rfc/planned/rfc-delta-sync.md` §7; ADR-0023 (separate orchestrator)
