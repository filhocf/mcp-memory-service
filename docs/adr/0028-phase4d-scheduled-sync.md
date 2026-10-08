# ADR-0028: Phase 4d — scheduled sync cycle (pull + push) on the consolidation scheduler

- **Date:** 2026-10-08
- **Status:** Accepted
- **Deciders:** Claudio (owner/client), Zero (agent).
- **Scope:** delta-sync (#1345) Phase 4d. Completes ADR-0026 (manual-then-scheduler) and the
  radial model (ADR-0018 pull / ADR-0027 push). This is what actually retires Insync.

## Context

Phases 4a-4c proved the transport: a spoke pulls (ADR-0018) and pushes (ADR-0027) manually.
ADR-0026 deliberately deferred the scheduler so the orchestration logic could be proven in a
deterministic gate first. That proof is done (82 delta-sync tests green + hot E2E both
directions). The remaining gap to retire Insync is **automatic periodic sync** — a spoke must
run pull + push on its own, without a human invoking `sync_from_peer`/`push_to_peer`.

**Codebase truth (confirmed, not assumed).** The service already runs an in-process
`ConsolidationScheduler` (APScheduler `AsyncIOScheduler`, `consolidation/scheduler.py`),
instantiated in `server_impl.py:860` and started at startup. It already hosts two opt-in
interval jobs that are the exact pattern to mirror:
`_schedule_harvest_job` (`MCP_HARVEST_SCHEDULE`) and `_schedule_quality_recompute_job`
(`MCP_QUALITY_RECOMPUTE_SCHEDULE`) — both: read an env interval ("6h"/"30m"/"90s"), parse with
`_parse_interval_seconds`, `add_job(IntervalTrigger(seconds=...), replace_existing=True)`,
and are **off by default** (unset/blank/"disabled" → no job, zero regression).

## Decision

**Add a sync job to `ConsolidationScheduler`, mirroring the existing jobs — do not build a
new scheduler.**

1. **`_schedule_sync_job()`** — opt-in via **`MCP_SYNC_SCHEDULE`** (interval string, e.g.
   "15m"). Unset/blank/"disabled" → no job (default off, zero regression). Reuses
   `_parse_interval_seconds`. `add_job(func=self._run_sync_cycle,
   trigger=IntervalTrigger(seconds=...), id="delta_sync", replace_existing=True)`.
   Called from the same place as the other two (in `start()`).

2. **`_run_sync_cycle()`** — for each configured peer: `sync_from_peer` (pull) **then**
   `push_to_peer` (push). **Pull before push** so the spoke is up to date before publishing;
   both are already idempotent + cursor-resumable, so order only affects latency of
   convergence, not correctness.

3. **Peer configuration.** Peers come from env **`MCP_SYNC_PEERS`** (comma-separated peer specs
   resolved to `RemoteHTTPStorage` with the existing auth: `x-api-key` + basic). For the current
   topology one peer (the hub) suffices, but the cycle iterates a list so N peers work later.
   The hub itself sets no peers → the hub schedules nothing (it is the passive pivot;
   ADR-0027). Only spokes schedule.

4. **Resilience.** A failing cycle (network down, hub 5xx) is **logged and retried next
   interval** — never crashes the scheduler. The per-peer cursors (`sync_cursor` pull /
   `push_cursor` push) already guarantee resumption from the last acked seq, so a missed or
   partial cycle self-heals on the next run.

5. **Credentials.** The scheduler reads peer auth from env/files already used manually
   (`MCP_API_KEY`, basic user/pass). No secrets in code or logs (reuses `_sanitize_log_value`).

## Alternatives Considered

- **External cron calling an MCP tool.** Rejected: ADR-0026 already reasoned that in-process
  piggybacking on the consolidation cadence is simpler and avoids a blocked-tool external call;
  the two existing jobs set the precedent.
- **New dedicated scheduler.** Rejected: `ConsolidationScheduler` exists, is started, and has
  the exact interval-job pattern. A second scheduler is needless surface.
- **Push before pull.** Rejected as default: pulling first keeps the local view fresh before it
  publishes; correctness is identical (idempotent + cursors), so we pick the lower-surprise order.

## Consequences

- Retires Insync for memory: each spoke, with `MCP_SYNC_SCHEDULE` set, converges with the hub
  automatically; the 3 machines converge through the hub.
- Zero regression when unset (default off), identical to harvest/quality jobs.
- Docs to update same increment: `docs/_fork/ESTADO.md` + `LEDGER-feats.md` (ours); project
  `docs/mastery/configuration-guide.md` (new env `MCP_SYNC_SCHEDULE`/`MCP_SYNC_PEERS`); SPEC
  `spec-delta-sync-fase4d.md`.
- Follow-up (not here): per-spoke identity (Phase 5), observability of sync job in health.
