# SPEC-C: Freshness — the newest version wins in injection

**Status:** planned · **Created:** 2026-10-10 · **Fork-only (maturing) · learning-loop frente C (RFC §14)**
**Author:** Claudio + Zero · **ARC:** e3dc542d · **Depends on:** G0 (seven, 10/out)

## Problem

When the same fact exists in two versions (v1 old, v2 updated), injection does NOT
prefer the newer one. `memory_context` sorts purely by `relevance * confidence`
(context_injection.py:274) and never looks at `updated_at`/`created_at`; the belief
dict doesn't even carry the timestamp into the scored list. The underlying `retrieve`
orders by embedding `distance` (retrieve.py:154) — so if v1 is denser to the query, the
STALE version wins. In the fisioterapia analogy (RFC §0): the agent is handed last
semester's note when the fact was updated this week. (Dimension 2 — Freshness — of the
agent-memory eval framework.)

## Objective

Make injection prefer the most recent version of a fact. Start with the cheap,
zero-DDL route (timestamp as a ranking signal); keep belief-level supersession as an
explicit evolution only if the metric doesn't reach target.

## Requirements (EARS)

- **R1 (carry timestamp):** THE injection scorer SHALL propagate each belief's
  `updated_at` (fallback `created_at`) into the scored item (context_injection.py:245-258).
- **R2 (recency as tiebreaker/boost):** WHEN two candidate beliefs are within a relevance
  band of each other, THE injection SHALL rank the one with the newer `updated_at` higher
  — implemented as a deterministic tiebreaker (newer wins) and a bounded recency boost
  that MUST NOT override a materially higher relevance×confidence (freshness refines
  ties, it does not invert relevance).
- **R3 (respect active-only):** THE injection SHALL continue to read only `status='active'`
  beliefs, so a belief already marked `superseded` never competes (no regression).
- **R4 (opt-out):** THE recency signal SHALL be opt-in via `MCP_INJECT_FRESHNESS`
  (default on once validated); WHEN off, ordering is byte-identical to today.
- **R5 (no DDL in the cheap route):** R1-R4 SHALL be achievable without schema change
  (timestamps already exist on `beliefs`). A `beliefs.superseded_by` column is OUT OF
  SCOPE here (separate evolution) and only pursued if the acceptance metric < 1.0.

## Acceptance criteria (measurable)

- [ ] GIVEN a fact as belief v1 (older `updated_at`) and v2 (newer), both active and
  relevant to the task, WHEN `memory_context` is called, THEN v2 ranks above v1 in the
  top-k. taxa_freshness (fraction of versioned pairs where the newer wins) = 1.0 on the
  adversarial pair set (frente E provides the set).
- [ ] WITH `MCP_INJECT_FRESHNESS` off, ordering is byte-identical to today (regression).
- [ ] A materially more relevant older belief is NOT demoted below an irrelevant newer
  one (freshness refines ties, never inverts relevance) — explicit test.
- [ ] No schema migration in the cheap route.

## Out of scope

- `beliefs.superseded_by` + automatic version linking (robust route — separate spec if needed).
- Freshness on the generic `retrieve` path (only the injection path here).

## Notes

G0 (seven): sort at context_injection.py:274 ignores timestamps; memories have a proven
`superseded_by` filter but beliefs only have a `status`; cheap route = timestamp
boost/tiebreaker, robust route = new column. Metric-target in R2/acceptance.
