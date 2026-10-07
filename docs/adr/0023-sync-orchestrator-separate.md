# ADR-0023: Sync orchestrator is separate from BackgroundSyncService (no fused loop)

- **Date:** 2026-10-07
- **Status:** Accepted
- **Deciders:** Claudio (owner/client), Zero (agent). Arch input: seven (Gate 1, graph-baseline).
- **Scope:** delta-sync (#1345) Phase 4b — pull orchestration. RFC §7.

## Context

Phase 4a shipped the pull pieces (`get_events_since`, `apply_remote_event`, cursor) but
nothing wires them into an automatic flow (graph baseline: 0 production callers). The
hybrid backend already has a `BackgroundSyncService._sync_loop` that pushes *state*
(`secondary.store/delete` per operation) to the secondary. We must decide whether the
event-log sync integrates into that loop or lives separately.

## Decision

The event-log sync lives in a **separate `storage/sync/orchestrator.py`**, NOT inside
`BackgroundSyncService`/`_sync_loop` and NOT inside `hybrid.py`. It reuses the #1304
transport (`remote_http`) but is its own method/loop. `sync_from_peer(local, peer, peer_id)`
runs: resolve cursor → `peer.get_events_since(cursor)` paginated → `apply_remote_event`
per event → `advance_sync_cursor` per page (same transaction, §8.5).

## Alternatives Considered

### Integrate into the existing `_sync_loop` — rejected
- `BackgroundSyncService` moves STATE (store/delete, no authorship, no resolver, wall-clock
  cursor); the event-log moves EVENTS (seq/HLC/agent_id, resolver, per-peer cursor). Fusing
  them would make each local `store` push the SAME fact via TWO channels with different
  conflict semantics — the bifurcation RFC §7 explicitly forbids. Graph proof: `_sync_loop`
  callees are only `MemoryStorage` primitives — zero event-log symbols; fusing would
  introduce the conflict.
- It also couples the event-log to the hybrid `secondary` lifecycle (multi-writer doesn't
  require a hybrid backend).

### Separate orchestrator reusing #1304 transport — CHOSEN
- RFC §7: the event-log is the authorship+reconciliation layer OVER the #1304 transport,
  not a competing channel. Reusing transport ≠ fusing the loop. Agnostic to hybrid.

## Consequences

- **Positive:** no double-write of the same fact; event-log works without a hybrid backend;
  the orchestrator is testable in local mode (two storages, no network).
- **Negative:** a second place where "sync" happens — mitigated by the fact they move
  different things (state vs events) and, in multi-writer deployments, the event-log is the
  channel of record (the state-push to the same peer is not enabled).
- **Delta-graph check (Gate 4):** `apply_remote_event`/`get_events_since` must gain a
  production caller (the orchestrator); the orchestrator must have NO edge to/from
  `_sync_loop`/`_process_single_operation` (else the forbidden fusion happened).

## References
- `docs/rfc/planned/rfc-delta-sync.md` §7
- ADR-0018 (pull-only 4a), ADR-0026 (manual dispatch → scheduler); `storage/sync/orchestrator.py`
