# ADR-0018: Phase 4a is pull-only (defer push/bidirectional to Phase 4b)

- **Date:** 2026-10-07
- **Status:** Accepted
- **Deciders:** Claudio (owner/client), Zero (agent). Arch input: seven (Gate 1).
- **Scope:** delta-sync (#1345) Phase 4a — event-log transport. RFC §7, §8.4, §8.5.

## Context

Phase 4 makes the event-log actually sync between machines, reusing the #1304 transport
(`remote_http`). Full bidirectional sync (pull + push + scheduling) is too large for one
cohesive PR, and the riskiest piece is the APPLY (resolver vs local state, late-event,
idempotency), not the direction.

## Decision

Phase **4a = PULL only**, end-to-end: a `GET /api/sync/events` feed (server), a
`remote_http.get_events_since()` consumer, the APPLY (`storage/sync/apply.py`), and a
per-peer cursor. A client pulls events from a hub and applies them. **Phase 4b** adds push
and the bidirectional polling loop + scheduler.

## Alternatives Considered

### push + pull together — rejected
- Couples two directions in one PR; larger review surface; the apply risk is the same.

### push only — rejected
- Low standalone value: the #1304 `store()` already pushes *state*; what's missing is the
  event-log sync, and pulling+applying is the half that unlocks hub-and-spoke for the 3
  machines pulling from the VPS hub.

### pull only — CHOSEN
- Isolates the APPLY (highest risk) and makes it testable in local mode without network;
  immediately useful (clients pull from the hub); a clean, reviewable slice.

## Consequences

- **Positive:** real value (hub→client sync), risk isolated, local-testable.
- **Negative:** anti-impersonation authorship validation (§8.4 full) is incomplete in
  pull-only (the client trusts the hub); documented as a 4a limitation, closed in 4b.

## References
- `docs/rfc/planned/rfc-delta-sync.md` §7, §8.4, §8.5
- ADR-0019 (cursor), 0020 (feed pagination), 0021 (apply materialization), 0022 (authorship)
