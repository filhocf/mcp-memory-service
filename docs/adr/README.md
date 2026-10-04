# Architecture Decision Records — mcp-memory-service (fork)

> *Why* decisions were made, with discarded alternatives. Immutable once Accepted.
> New ADR when: alternatives really discarded, costly to reverse, or a future reader
> will ask "why not X?". Format: `NNNN-slug.md` (English, OSS fork). Template: `template.md`.
> Complements `docs/_fork/LEDGER-feats.md` (what/where) — ADR is the *why*.

| ADR | Title | Status | Arc |
|-----|-------|--------|-----|
| [0001](0001-adopt-adr.md) | Adopt Architecture Decision Records | Accepted | process |
| [0002](0002-sync-transport-delta-event-log.md) | Sync transport = delta event-log; retire OneDrive whole-DB sync | Accepted | multi-agent/sync |
| [0003](0003-learning-input-is-real-usage.md) | Learning input is real usage, not structured session fields | Accepted | learning-loop |
| [0004](0004-working-memory-reuses-memory-context.md) | Working-memory reuses memory_context (single injection path) | Accepted | learning-loop |
| [0005](0005-agent-assertiveness-metric.md) | Agent-assertiveness metric ("am I getting better?") | Accepted | learning-loop |

## Flow
RFC (what/why build) → **ADR (architecture decisions within)** → spec/EARS (how to test) → code.
