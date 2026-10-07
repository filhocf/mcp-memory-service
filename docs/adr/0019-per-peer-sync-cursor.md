# ADR-0019: Per-peer sync cursor in a dedicated table (not metadata, not data_version)

- **Date:** 2026-10-07
- **Status:** Accepted
- **Deciders:** Claudio (owner/client), Zero (agent). Arch input: seven (Gate 1).
- **Scope:** delta-sync (#1345) Phase 4a. Satisfies RFC §8.5.

## Context

§8.5: the per-peer sync cursor is the source of truth for "how far I have observed each
peer's event-log" — `PRAGMA data_version` only detects local-connection staleness. Phase 4a
must persist, per peer, the last event consumed, so a pull is resumable and idempotent.

## Decision

A dedicated table **`sync_cursor(peer_id PK, last_seq_seen, last_hlc_physical,
last_hlc_logical, updated_at)`** (migration 018). Pagination is by the peer's `seq`
(monotonic PK of its `sync_events`); the cursor advances `last_seq_seen = next_seq`
**only after** the batch is applied, in the same transaction as the applies.

## Alternatives Considered

### Reuse `metadata` last_hlc (ADR-0011) — rejected
- That is the LOCAL clock, not "how far I read from peer P". Different semantics; a single
  key can't hold N peers.

### `PRAGMA data_version` — rejected (§8.5)
- Aggregate state version; no per-peer resumable position; can't track multiple peers.

### Dedicated per-peer table — CHOSEN
- Per-peer rows, resumable, source of truth for completeness; advances atomically with the
  applies so a crash mid-batch re-pulls from the last durable cursor.

## Consequences

- **Positive:** resumable, multi-peer, idempotent re-sync; §8.5 satisfied.
- **Negative:** a new table (migration 018) — additive, zero blast radius.
- **Note:** HLC columns on the cursor are observability only; pagination is by `seq`
  (ADR-0020).

## References
- `docs/rfc/planned/rfc-delta-sync.md` §8.5; migration `018_add_sync_cursor.sql`
- ADR-0011 (local last_hlc — distinct), ADR-0020 (seq pagination)
