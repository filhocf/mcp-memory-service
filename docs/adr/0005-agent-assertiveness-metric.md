# ADR-0005: Agent-assertiveness metric (the "am I getting better?" number)

- **Date:** 2026-10-04
- **Status:** Accepted
- **Deciders:** Claudio (owner), Zero (agent — as the MCP's own client)

## Context

The owner asked the agent, as the actual client of the memory service, to provide "the
metric on your side". Today's telemetry (`usage_events`) measures *service usage* (search
counts, latency, feedback coverage) but **not the agent's benefit**: did I answer right on
the first try more often? redo less work? lose less context between sessions? The stated
north star — "each week more useful than the last" — has no measurement. Without a
baseline the agent builds the learning-loop blind (nearly repeated this session).

## Decision

Define an **agent-assertiveness metric** derived from `usage_events` + a few new signals,
aggregating three sub-metrics into one weekly number:
1. **Re-query rate** — how often the same query is refined within a window (proxy for
   "didn't find it first time"). Lower = more assertive. *Measurable with today's events.*
2. **Injection coverage** — % of sessions where an injected belief was actually referenced
   afterwards. Higher = injection hits.
3. **Lost context** — how often the agent searches for something that was in a recent
   checkpoint it "should" have had in context. Measures the #1 pain (context loss).

The single number answers: "is the service making the agent more assertive week over week?"
It is the honest measuring stick that closes the learning-loop, instead of the agent
asserting "I'm improving" without proof.

## Alternatives Considered

### No agent-side metric (status quo)
- **Pros:** nothing to build.
- **Cons:** cannot prove the learning-loop helps; builds features blind.

### Only service-usage telemetry (what exists)
- **Pros:** already built.
- **Cons:** measures the service, not the agent's benefit — the wrong subject.

## Consequences

- **Positive:** a baseline to prove N2 (auto-inject) and RFC-MM-01 (feedback) actually help.
- **Negative / cost:** needs reaccess capture + aggregation; "lost context" is a proxy.
- **Neutral / follow-up:** owner recommended building the metric FIRST (baseline before
  changing anything), so the effect of N2/RFC-MM-01 is measurable. Sequence TBD.

## References

- `src/mcp_memory_service/storage/usage_telemetry.py` (base signals)
- `docs/rfc/planned/rfc-mm-01-feedback-loop.md` (acceptance criteria: quality 0.5→0.65)
- `docs/rfc/planned/rfc-learning-loop.md` (north star: weekly improvement)
