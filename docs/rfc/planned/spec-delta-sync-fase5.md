# SPEC — delta-sync Phase 5: bootstrap + event version negotiation

- **Status:** Planned
- **Scope:** #1345 Phase 5. Implements RFC §9.3 (bootstrap/migration) + §9.3 rule 6 (version negotiation). Closes the delta-sync arc.
- **Depends on:** Phase 1 (event-log), Phase 2 (HLC+resolver), Phase 4 (pull/push/apply/cursors).
- **Out of scope (deferred, see RFC §5):** strong per-spoke transport identity. The Phase 4c
  authorship allow-list (`MCP_SYNC_PUSH_ALLOWED_AGENTS`, §8.4/R4) covers the current trusted
  hub + known-spokes topology; cryptographic per-spoke identity is future work.

## Problem

A new spoke (or a freshly reinstalled machine) joining the mesh today has no way to catch up
on the existing corpus without reprocessing everything. The event-log only carries mutations
that happened *after* it was enabled — a node that was offline for the baseline has gaps. To
retire Insync, a new node must be able to **bootstrap** from a peer's current state as a unit
(snapshot + watermark), then consume events from that watermark forward, idempotently.

Separately, §9.3 rule 6: a peer must not silently accept an event whose envelope version it
does not understand — it must reject/quarantine and NOT advance its cursor past it.

## Requirements (EARS)

### Bootstrap (RFC §9.3)

**R1 — Baseline from current state (no fake history).**
WHEN a bootstrap baseline is generated from a storage, THE baseline SHALL be derived from the
*current* memories (and their tombstones), NOT from any pre-bootstrap event history. THE
baseline SHALL carry a durable `snapshot_id`/watermark identifying the event-log position at
which it was taken.

**R2 — Deterministic, idempotent baseline.**
WHEN the same storage state is bootstrapped twice, THE baseline SHALL produce the same logical
set of baseline events, with IDs derived deterministically from the memory's content_hash and
version (not random UUIDs). Re-running bootstrap SHALL NOT duplicate memories on the target.

**R3 — Atomic snapshot↔log cut.**
THE watermark SHALL be captured such that no mutation is lost between the snapshot and the
subsequent event stream: either the cut is atomic, or any overlap is covered by idempotent
replay (R2). A memory mutated concurrently with bootstrap SHALL appear in the baseline OR in
the post-watermark events, never neither.

**R4 — Authorship/privacy on baseline (RFC §9.3 rule 3).**
WHEN generating baseline events, THE bootstrap SHALL preserve `metadata.agent_id` where
present. WHERE a memory has no verifiable authorship, THE baseline SHALL mark it
`unattributed` and SHALL NOT invent an agent. (Implementation note: a single clean token
`unattributed` is used instead of the RFC's prose `legacy/unattributed`, so the value stays
a valid `agent_id` for downstream agent filters — no slash.)

> **DEFERRED to future (decision 09/out):** the privacy half of RFC §9.3 rule 3 — "unattributed/legacy
> items stay local-private and do NOT enter a shared baseline unless the prevailing `shareable`
> policy authorizes them" — is NOT implemented in this phase. The service has no `shareable`
> policy mechanism yet (it is RFC design, R6, not code anywhere), so gating the baseline on a
> non-existent policy would ship half a feature. The baseline currently includes all memories.
> Revisit together with the `shareable` policy when it is actually built. (Same spirit as the
> deferred per-spoke crypto identity, RFC §5.)

**R5 — Deletes become baseline tombstones (RFC §9.3 rule 4).**
WHEN a soft-deleted memory (`deleted_at` set) is bootstrapped, THE baseline SHALL emit a
tombstone preserving the available deletion time, NOT omit the row. THE physical tombstone
SHALL NOT be pruned by bootstrap.

**R6 — New-peer install is a unit and idempotent (RFC §9.3 rule 5).**
WHEN a new peer installs a baseline, THE peer SHALL install the snapshot and its watermark
together, THEN consume events strictly after that watermark. WHEN the same baseline is
installed again, THE result SHALL be identical (no duplicates, no cursor regression).
`content_hash` alone SHALL NOT be assumed sufficient to represent a delete or a policy change.

### Event version negotiation (RFC §9.3 rule 6)

**R7 — Unknown envelope version is rejected, not ignored.**
WHEN apply receives an event whose envelope `schema_version` is greater than the version this
peer understands, THE apply SHALL reject/quarantine the event, report the incompatibility, and
SHALL NOT advance the sync cursor past it. THE peer SHALL NOT silently skip or best-effort
apply an unknown-version event.

**R8 — Known versions still apply.**
WHERE an event's `schema_version` is one this peer understands (currently 1), THE apply SHALL
process it exactly as before (zero behaviour change for current events).

### Non-functional

**R9 — Opt-in, zero regression.**
Bootstrap SHALL be an explicit operation (CLI/endpoint/function call), never automatic on
startup. WHERE bootstrap is never invoked, THE service SHALL behave exactly as Phase 4.

**R10 — No secrets in logs.** Reuse `_sanitize_log_value` for any logged peer/identity values.

## Acceptance Criteria

- **CA1 (R1/R2):** bootstrap a storage with N memories twice → identical baseline event set
  (same IDs); applying it to an empty peer twice → peer has exactly N memories, no duplicates.
- **CA2 (R3):** a memory stored during bootstrap appears in the baseline or in post-watermark
  events (prove via a seam test: store between snapshot and watermark read).
- **CA3 (R4):** a memory with `metadata.agent_id` keeps it in the baseline; a memory with no
  authorship is marked `unattributed` (not an invented agent). Privacy gating (excluding
  unattributed from a shared baseline) is DEFERRED — see R4 note.
- **CA4 (R5):** a soft-deleted memory bootstraps as a tombstone (apply on peer → row is
  tombstoned, not resurrected).
- **CA5 (R6):** install baseline on fresh peer → corpus materialized + cursor at watermark;
  re-install → no change (idempotent); then one post-watermark event applies on top.
- **CA6 (R7):** apply an event with `schema_version=99` → rejected/quarantined, cursor does
  NOT advance past it, incompatibility logged.
- **CA7 (R8):** apply a `schema_version=1` event → applied exactly as Phase 4 (regression).
- **CA8 (E2E a quente):** on a real pair (local ↔ hub VPS), bootstrap a fresh local DB from the
  hub baseline → corpus present, then live pull/push continues from the watermark with no
  reprocessing of the baseline.

## Out of Scope

- Strong per-spoke transport identity / cryptographic authorship (RFC §5 — future).
- Compaction/pruning of tombstones (RFC §8.1 retention — separate concern).
- hybrid/Cloudflare/Milvus bootstrap (RFC §9.4 — sqlite_vec only this phase).
- Scale claims for 20k+ memories (RFC §9.3 — needs measurement first; CA uses small N).
