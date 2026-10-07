# ADR-0020: Event feed paginated by seq, not HLC

- **Date:** 2026-10-07
- **Status:** Accepted
- **Deciders:** Claudio (owner/client), Zero (agent). Arch input: seven (Gate 1).
- **Scope:** delta-sync (#1345) Phase 4a. Supports RFC §8.5.

## Context

`GET /api/sync/events` must page through a peer's event-log in a stable, resumable order.
The events carry both a local `seq` (AUTOINCREMENT PK) and an HLC `(hlc_physical,
hlc_logical)`. We must choose the pagination key.

## Decision

Paginate by **`seq`** (`?since_seq=<int>&limit=<n>`). `seq` is the peer's local monotonic
PK — strictly increasing and unique on that peer, so the cursor is unambiguous and
resumable. HLC is still returned on each event (the APPLY uses it for ordering/resolution),
but it is NOT the pagination key.

## Alternatives Considered

### Paginate by HLC — rejected
- HLC can tie across agents (same physical ms, different agent); a cursor on HLC would be
  ambiguous about "did I already see this one". `seq` is per-peer unique and total.

### Paginate by seq — CHOSEN
- Monotonic, unique, resumable; matches the per-peer cursor (ADR-0019). HLC remains the
  *ordering/resolution* key inside the APPLY (ADR-0010), cleanly separated from the
  *transport* cursor.

## Consequences

- **Positive:** unambiguous resumable cursor; clean split between transport order (seq) and
  logical order (HLC).
- **Negative:** `seq` is peer-local, so a cursor is only meaningful per peer_id — exactly
  what ADR-0019's per-peer table enforces.

## References
- `docs/rfc/planned/rfc-delta-sync.md` §8.5; ADR-0010 (HLC = logical order), ADR-0019 (cursor)
