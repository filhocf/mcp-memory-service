# ADR-0001: Adopt Architecture Decision Records (fork)

- **Date:** 2026-10-04
- **Status:** Accepted
- **Deciders:** Claudio (owner), Zero (agent)

## Context

The fork keeps 24+ RFCs (`docs/rfc/`) describing *what* to build. But *why* a given
architecture was chosen — and what was deliberately rejected — lived scattered across
memory checkpoints, ESTADO.md lines, and commit messages. This caused real rework:
in a single session (3-4 Oct) we found three unresolved contradictions between RFCs
(sync transport, learning input model, injection path) that existed only because the
underlying decisions were never recorded *as decisions*. Reconstructing each cost
~30 minutes of archaeology that a one-page record would have answered in 30 seconds.

RFCs answer "what/why build it" and change with the product. They are the wrong place
for "we chose X over Y because Z" — a decision record must be **immutable** and capture
the moment's context and the discarded alternatives.

## Decision

We will keep **Architecture Decision Records** in `docs/adr/`, one file per decision,
`NNNN-slug.md`, English (OSS fork). An ADR is written when a decision (a) has real
alternatives discarded, (b) is costly to reverse, or (c) a future reader will ask
"why didn't they just do X?". ADRs are immutable once Accepted; circumstances changing
means a new ADR that supersedes the old. The flow is: **RFC (what) → ADR (architecture
decisions within it) → spec/EARS (how to test) → code.**

## Alternatives Considered

### Keep decisions in RFCs / commit messages / memory (status quo)
- **Pros:** no new artifact; zero setup.
- **Cons:** proven to fail — the 3 contradictions above. Decisions get edited away
  (RFCs mutate), buried (commits), or lost (memory not consulted at decision points).
- **Reversibility:** n/a (it's the current pain).

### Full RFC-per-decision
- **Pros:** rich.
- **Cons:** heavyweight; RFCs are product specs, not decision logs; would bloat.

## Consequences

- **Positive:** durable "why + rejected alternatives"; faster re-entry into a topic;
  onboarding; the fork-curation methodology gains a decision layer.
- **Negative / cost:** discipline to write one at decision time (mitigated by a strict
  cut rule above — not every choice needs an ADR).
- **Neutral / follow-up:** the three contradictions resolved on 4/out become ADR-0002/3/4;
  the agent-assertiveness metric becomes ADR-0005.

## References

- `.kiro/skills/adr/SKILL.md` (format)
- `docs/_fork/metodologia-fork.md` (fork curation — ADR complements the LEDGER)
