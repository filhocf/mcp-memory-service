# ADR-0021: APPLY materializes from the event enriched with content (not a get_by_hash fetch)

- **Date:** 2026-10-07
- **Status:** Accepted
- **Deciders:** Claudio (owner/client), Zero (agent). Arch input: seven (Gate 1).
- **Scope:** delta-sync (#1345) Phase 4a. RFC §7, §8.1-8.3.

## Context

The `create` event does NOT carry `content` (Phase 1 stored only
`{content_hash, memory_type, tags, timestamps, metadata}`, store.py). To materialize a
pulled `create`, the APPLY needs the content. Two ways: enrich the feed, or fetch it.

## Decision

The **`GET /api/sync/events` feed enriches `create` events with `content`** (server-side
JOIN `sync_events × memories`). The APPLY is then self-contained: it writes directly to the
local SQLite (not via `POST /api/memories`), which also avoids the known `remote_http.store`
timestamp-handling limitation. If the memory was already deleted on the hub, the event is
sent without content and the APPLY treats it via the tombstone (§8.1c).

## Alternatives Considered

### APPLY fetches content via `get_by_hash` — rejected
- Extra round-trip per create; couples the apply to the peer's availability at apply time;
  non-deterministic replay (content could change between feed and fetch).

### Feed enriches create with content — CHOSEN
- Self-contained, deterministic replay, fewer round-trips, bypasses the store-timestamp
  limitation. Cost: larger payload for `create` events (acceptable; deltas are small).

## Consequences

- **Positive:** deterministic, single round-trip, direct SQLite materialization.
- **Negative:** `create` payloads carry content (bigger). Deleted-on-hub creates arrive
  content-less and rely on the tombstone — correct, documented.
- **Materialization:** create/update → UPSERT memories (embedding_pending=1 if the vector's
  model differs or is absent, §8.3); delete → soft-delete (tombstone).

## References
- `docs/rfc/planned/rfc-delta-sync.md` §7, §8.1c, §8.3
- ADR-0009 (tombstone), ADR-0015/0016/0017 (embedding_pending)
