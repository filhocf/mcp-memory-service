# ADR-0027: Phase 4c — outbound push (spoke → hub) reusing apply, with session-validated authorship

- **Date:** 2026-10-08
- **Status:** Accepted
- **Deciders:** Claudio (owner/client), Zero (agent).
- **Scope:** delta-sync (#1345) Phase 4c. Satisfies RFC §7 (transport) + §8.4 (authorship), completes the radial (hub-and-spoke) model.

## Context

Phase 4a/4b delivered **pull only** (ADR-0018): a spoke pulls events from the hub via
`GET /api/sync/events` and applies them locally. This is sufficient for *receiving*, but a
memory **created on a spoke** (e.g. DNBSCDC289, behind the Dataprev firewall) never reaches
the hub — so it never reaches the other spokes either.

**Network constraint (decisive).** The 3 work machines (DNBSCDC289 behind corporate FW,
sirdata/socrates behind home NAT) are **not reachable from outside**. Only the hub VPS
(`cfnarede.dev`, public, nginx:443) is reachable. Therefore the hub **cannot push** to a
spoke; every data flow must be **initiated by the spoke** (outbound). The radial model is:
spokes converge through the hub; spokes never talk to each other directly.

Consequently "bidirectional sync" on this topology = the spoke, in one outbound pass,
**pulls** new events from the hub (Phase 4a) **and pushes** its own new events to the hub
(this ADR). The hub is a passive pivot.

## Decision

**1. Hub ingestion endpoint — `POST /api/sync/events` (mirror of the GET feed).**
Accepts a batch of events `{events: [SyncEventData...]}` and applies each via the existing
`apply_remote_event` (ADR-0021/0022: idempotent on `(agent_id, event_id)`, materializes
enriched `create`, preserves original authorship/HLC, honors durable tombstones §8.1c).
No new apply logic — the ingestion is a thin authenticated wrapper over `apply.py`.

**2. Spoke push client — `remote_http.push_events_since(events)`.**
Sends local events with `seq > last_pushed` to the hub's `POST /api/sync/events`. The spoke
reads its own `sync_events` and posts them; the hub returns per-event apply results
(`applied` / `skipped_duplicate` / `failed`).

**3. Outbound push cursor — dedicated table `push_cursor` (migration 019).**
Track "how far I pushed to each peer" in a dedicated table
`push_cursor(peer_id PK, last_seq_pushed, updated_at)` (migration 019, additive). This is
**deliberately separate** from `sync_cursor`: the two carry different meanings — `sync_cursor.last_seq_seen`
is "how far I read **the peer's** log" (pull), `push_cursor.last_seq_pushed` is "how far I published
**my own** log to that peer" (push). Overloading one column with two meanings (via a `:push`
peer_id suffix) was considered and **rejected**: a field with two meanings is a debugging trap
and future-refactor debt (same hazard class as the overloaded `quality_score` that ADR-0013
had to defuse). Advance `last_seq_pushed` only after the hub acks the batch, same transactional
discipline as ADR-0019. One meaning per column; the operator reads either table and knows exactly
what it says.

**4. Authorship (pragmatic now, hardened in Phase 5) — §8.4.**
The hub validates that incoming events' `agent_id` matches an **expected authorship bound to
the authenticated session**. Today all spokes share one nginx basic-user (`zero`), so the
hub cannot distinguish spokes at the transport layer. Interim rule: the hub accepts the
payload `agent_id` but **rejects a batch whose events claim an `agent_id` outside an
allow-list** configured on the hub (env `MCP_SYNC_PUSH_ALLOWED_AGENTS`), defaulting to
"accept any non-empty" when unset (back-compat). Full per-spoke identity (one credential per
machine, hub stamps `agent_id` from the authenticated principal, ignoring payload) is
deferred to **Phase 5** (shareable/scope, §9.3) and tracked there. This keeps push working
across the 3 machines now without a transport-layer identity overhaul.

**5. Bidirectional pass (orchestration).**
`sync_from_peer` (pull) + a new `push_to_peer` form one outbound cycle. The scheduler that
runs this cycle periodically (replacing Insync) is **Phase 4d** — out of scope here. Phase 4c
delivers the push mechanism, invoked manually/E2E, same as pull was in 4a.

## Alternatives Considered

- **Hub pulls from spokes.** Impossible on this topology (FW/NAT) — rejected by network reality.
- **Trust payload agent_id blindly.** Rejected: §8.4 forbids publishing as another agent; the
  allow-list is the minimum guard until per-spoke identity (Phase 5).
- **New push cursor table.** **Chosen** (decision 3): a dedicated `push_cursor` keeps one
  meaning per column. The additive migration 019 is cheap; the alternative — reusing
  `sync_cursor` with a direction-qualified `peer_id` suffix — was rejected because it overloads
  `last_seq_seen` with two meanings and forces every query to remember/parse the suffix
  (operator-debugging trap + future-refactor debt).
- **Push via existing `POST /api/memories`.** Rejected: that re-stores content and loses
  event identity/HLC/authorship; ingestion must go through `apply_remote_event` to preserve
  the event contract (same reason ADR-0021 chose direct-apply over `remote_http.store`).

## Consequences

- Completes the radial model: any spoke's writes reach all others through the hub.
- No new apply/resolve logic — push reuses the proven `apply.py` (77 tests green, Phase 1-4).
- Authorship is guarded at the allow-list level now; strong per-spoke identity is an explicit
  Phase 5 follow-up (documented, not forgotten).
- Docs to update in the same increment: `docs/_fork/ESTADO.md` + `LEDGER-feats.md` (ours);
  project `README`/`docs/mastery/*` if they describe the sync API surface; and the SPEC
  `spec-delta-sync-fase4c.md`.
