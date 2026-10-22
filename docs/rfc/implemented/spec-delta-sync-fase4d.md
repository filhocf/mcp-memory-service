# SPEC — delta-sync Phase 4d: scheduled sync cycle (pull + push)

- **Status:** Planned
- **Scope:** #1345 Phase 4d. Implements ADR-0028. Completes ADR-0026 (manual→scheduler).
- **Depends on:** Phase 4a (sync_from_peer), Phase 4c (push_to_peer), ConsolidationScheduler.

## Problem

Pull and push work manually. To retire Insync, a spoke must run the pull+push cycle
periodically on its own, in-process, opt-in, with zero regression when disabled — mirroring
the existing `_schedule_harvest_job` / `_schedule_quality_recompute_job`.

## Requirements (EARS)

**R1 — Opt-in scheduling.**
WHERE `MCP_SYNC_SCHEDULE` is set to a valid interval ("15m"/"30m"/"6h"/"90s"/plain hours),
THE scheduler SHALL register one interval job that runs the sync cycle. WHERE the env is
unset/blank/"disabled", THE scheduler SHALL register no job (default off, zero regression).

**R2 — Invalid interval is safe.**
WHEN `MCP_SYNC_SCHEDULE` is set but unparseable, THE scheduler SHALL log an error and
SHALL NOT register the job (no crash).

**R3 — Cycle = pull then push, per peer.**
WHEN the sync job fires, THE cycle SHALL, for each configured peer, call `sync_from_peer`
(pull) and then `push_to_peer` (push), in that order.

**R4 — Peer list from env.**
THE cycle SHALL resolve peers from `MCP_SYNC_PEERS`. WHERE `MCP_SYNC_PEERS` is unset, THE
cycle SHALL run no peers (a host with no peers — e.g. the hub — schedules effectively nothing).

**R5 — Resilience.**
WHEN a peer's pull or push raises, THE cycle SHALL log the error and continue to the next peer,
and SHALL NOT propagate the exception to the scheduler (next interval retries). Cursors
(`sync_cursor`, `push_cursor`) guarantee resumption from the last acked seq.

**R6 — No secrets in logs.**
THE cycle SHALL NOT log API keys or basic-auth credentials (reuse `_sanitize_log_value`).

**R7 — Idempotent registration.**
THE job SHALL be registered with `replace_existing=True` and a stable id (`delta_sync`), so a
restart does not create duplicates.

## Acceptance Criteria

- **CA1 (R1):** env set "15m" → job registered with IntervalTrigger(900s); env unset → zero jobs.
- **CA2 (R2):** env "banana" → error logged, no job, no exception.
- **CA3 (R3):** a fake peer records call order → pull called before push, once per peer.
- **CA4 (R4):** `MCP_SYNC_PEERS` with 2 peers → cycle touches both; unset → zero peers touched.
- **CA5 (R5):** peer A raises on pull → error logged, peer B still processed; scheduler job
  does not die (a second fire still runs).
- **CA6 (E2E a quente):** on DNBSCDC289 with `MCP_SYNC_SCHEDULE=1m` + `MCP_SYNC_PEERS=hub-vps`,
  create a memory locally → within one interval it appears on the hub (push leg); create one on
  the hub → within one interval it appears locally (pull leg). Real HTTPS + auth.

## Out of Scope

- Per-spoke transport identity / strong authorship (Phase 5).
- Health/observability surfacing of the sync job (follow-up).
- Backoff/jitter tuning beyond fixed interval (future, if needed).
