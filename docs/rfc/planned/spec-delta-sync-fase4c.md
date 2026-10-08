# SPEC — delta-sync Phase 4c: outbound push (spoke → hub)

- **Status:** Planned
- **Scope:** #1345 Phase 4c. Implements ADR-0027. Satisfies RFC §7 (transport) + §8.4 (authorship).
- **Depends on:** Phase 4a (apply, feed, pull), Phase 1-3 (event-log, HLC/resolver, embedding).

## Problem

A memory created on a spoke never reaches the hub (pull-only, ADR-0018). On this network
(spokes behind FW/NAT, only the hub is reachable), the spoke must **initiate** the push:
read its own new events and POST them to the hub, which applies them via `apply_remote_event`.

## Requirements (EARS)

**R1 — Hub ingestion endpoint.**
WHEN the hub receives `POST /api/sync/events` with a JSON body `{events: [...]}`, THE hub
SHALL apply each event via `apply_remote_event` and SHALL return a per-event result list
`{results: [{event_id, status}]}` where status ∈ {applied, skipped_duplicate, failed}.

**R2 — Ingestion is idempotent.**
WHEN the hub receives an event whose `(agent_id, event_id)` already exists locally, THE hub
SHALL skip it (status=skipped_duplicate) and SHALL NOT create a duplicate or mutate the
existing row. (Reuses apply idempotency, ADR-0021.)

**R3 — Ingestion requires write auth.**
WHEN `POST /api/sync/events` is called without valid write authorization, THE hub SHALL
reject it with 401/403 and SHALL NOT apply any event.

**R4 — Authorship allow-list (pragmatic §8.4).**
WHERE `MCP_SYNC_PUSH_ALLOWED_AGENTS` is set (comma-separated), WHEN the hub receives a batch
containing an event whose `agent_id` is not in the allow-list, THE hub SHALL reject the whole
batch with 403 and SHALL NOT apply any event in it. WHERE the env is unset, THE hub SHALL
accept any non-empty `agent_id` (back-compat).

**R5 — Spoke push client.**
WHEN `push_to_peer(local_storage, peer, peer_id, limit)` runs, THE client SHALL read local
`sync_events` with `seq > last_seq_pushed(peer_id)`, SHALL POST them in seq order (batched by
limit), and SHALL return a result `{events_pushed, events_failed, final_seq}`.

**R6 — Push cursor advances only on ack.**
WHEN the hub acks a batch (all applied or skipped_duplicate), THE client SHALL set
`push_cursor.last_seq_pushed = max(seq in batch)` for that peer_id in the same transaction.
WHEN any event in the batch returns failed, THE client SHALL stop and SHALL NOT advance the
cursor past the last successfully-acked seq (resumable).

**R7 — Push cursor is a dedicated table.**
THE schema SHALL define `push_cursor(peer_id PRIMARY KEY, last_seq_pushed INTEGER NOT NULL
DEFAULT 0, updated_at TEXT)` via migration 019 (additive, reversible). `push_cursor` SHALL be
distinct from `sync_cursor`; neither SHALL read the other's rows.

**R8 — Create events carry content on push.**
WHEN the client pushes a `create` event, THE client SHALL enrich it with `content` from the
local `memories` row (mirror of the GET feed enrichment, ADR-0021) so the hub can materialize.

## Acceptance Criteria

- **CA1 (R1/R2):** POST a create event to the hub → memory materialized on hub; POST again →
  skipped_duplicate, hub count unchanged.
- **CA2 (R3):** POST without auth → 401/403, zero events applied.
- **CA3 (R4):** allow-list set to `zero` → event with agent_id=`zero` applied; event with
  agent_id=`intruder` → whole batch 403, nothing applied. Env unset → non-empty agent_id applied.
- **CA4 (R5/R8):** push_to_peer sends 3 local creates → hub materializes all 3 with content.
- **CA5 (R6):** batch where event 2 of 3 fails → cursor advances to seq of event 1 only;
  re-run resumes from event 2.
- **CA6 (R7):** fresh DB → migration 019 creates `push_cursor`; `sync_cursor` and `push_cursor`
  independent (writing one does not touch the other).
- **CA7 (E2E a quente):** create memory on DNBSCDC289 local → push_to_peer to hub VPS →
  memory appears on hub (count +1); pull from another perspective sees it. Real HTTPS + auth.

## Out of Scope

- Scheduler / periodic bidirectional loop (Phase 4d).
- Per-spoke transport identity (hub stamps agent_id from authenticated principal) — Phase 5 (§9.3).
- Push of update_metadata/delete beyond what apply already handles (covered transitively; the
  client sends whatever ops are in its sync_events — no special-casing here).
