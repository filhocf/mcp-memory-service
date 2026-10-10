# SPEC-B: Negative use-signal — demote injected-but-unused beliefs

**Status:** planned · **Created:** 2026-10-10 · **Fork-only (maturing) · learning-loop frente B (RFC §14)**
**Author:** Claudio + Zero · **ARC:** e3dc542d · **Depends on:** injection provenance (source_hashes, commit 63ddfaaa)

## Problem

A belief's confidence is derived purely from observation support vs contradiction
(`derive_confidence`, belief.py:49-80) with temporal decay, and `should_supersede`
(belief.py:103) only compares against `CONFIDENCE_FLOOR` (0.35). **Nothing considers
whether an injected belief was ever actually useful.** A belief can be injected into
context dozens of times, never influence anything (its source memories never reappear
in a later retrieval), and keep its confidence — polluting the top-k injection with
dead weight. The loop has a positive use-signal (`injected_then_used`, telemetry W_INJ=2.0)
but no negative one. In the fisioterapia analogy (RFC §0): the agent keeps being handed
the note that never helped on any exam.

## Objective

Give beliefs a **negative use-signal**: a belief injected N times whose source memories
never reappear in subsequent retrievals loses confidence each consolidation cycle and,
on crossing the floor, is superseded and drops out of the injection top-k. Reuses the
existing `injected_then_used` derivation (inverted) and the existing consolidation cycle;
**no new DDL** (the signal is derived from `usage_events`; any cache lives in the existing
`beliefs.metadata` JSON).

## Requirements (EARS)

- **R1 (derive negative signal):** WHEN the consolidation cycle runs, THE service SHALL
  compute, for each active belief, `injections_without_use` = count of injection events
  carrying that belief_hash whose `source_hashes` never appeared in any later retrieval's
  `returned_hashes` for the same agent.
- **R2 (demotion threshold):** WHEN a belief's `injections_without_use >= N` (default N=3,
  env `MCP_BELIEF_UNUSED_THRESHOLD`), THE service SHALL reduce that belief's confidence by
  factor `MCP_BELIEF_UNUSED_PENALTY` (default 0.20) for that cycle.
- **R3 (supersede on floor):** WHEN the penalized confidence falls below `CONFIDENCE_FLOOR`
  (0.35), THE service SHALL mark the belief `status='superseded'` (same path as existing
  floor supersession), so it leaves the active set the injection reads from.
- **R4 (use resets):** WHEN a belief's source memories DO reappear in a later retrieval,
  THE service SHALL reset `injections_without_use` to 0 (a belief that becomes useful again
  is not punished for past silence).
- **R5 (opt-out, non-destructive):** THE negative signal SHALL be opt-in via
  `MCP_BELIEF_USE_FEEDBACK` (already exists); WHEN disabled, confidence derivation is
  unchanged. No belief is deleted — only confidence/status change (reversible via re-derivation).
- **R6 (no DDL):** THE implementation SHALL derive the signal from `usage_events` + store
  any counter in the existing `beliefs.metadata` JSON; it SHALL NOT add a column.

## Acceptance criteria (measurable)

- [ ] GIVEN a belief injected ≥3 times whose source_hashes never reappear in later
  retrievals, WHEN the consolidation cycle runs, THEN its confidence drops by ≥20% and,
  after enough cycles to cross 0.35, it is `superseded` and absent from `memory_context`'s
  top-k. (test: synthetic usage_events + belief, assert confidence delta + top-k absence)
- [ ] GIVEN a belief whose source reappears after some unused injections, WHEN the cycle
  runs, THEN its unused-counter is 0 and confidence is NOT penalized.
- [ ] WITH `MCP_BELIEF_USE_FEEDBACK` off, confidence derivation is byte-identical to today
  (regression).
- [ ] No schema migration added.

## Out of scope

- Positive reinforcement beyond the existing `injected_then_used` (that already works).
- Re-ranking by specificity/rarity (that is frente A — context precision — design-open).

## Notes

G0 (seven, 10/out): signal is derivable from existing data; `_derive_injected_then_used`
(usage_telemetry.py:359-412) is the mirror to invert; intervention points: belief.py:49-80
(derive_confidence), belief_service.py:200-212 (update/supersede), scheduler.py:712
(cycle). Metric-target in R-form above.
