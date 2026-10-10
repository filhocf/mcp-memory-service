# SPEC-E: Adversarial eval set + continuous MRR

**Status:** planned · **Created:** 2026-10-10 · **Fork-only (maturing) · learning-loop frente E (RFC §14)**
**Author:** Claudio + Zero · **ARC:** e3dc542d · **Depends on:** G0 (seven, 10/out)

## Problem

We cannot tell if B (negative signal) and C (freshness) actually improve learning,
because nothing measures freshness/forgetting over time. The LoCoMo harness
(`tests/benchmarks/`, `scripts/benchmarks/benchmark_locomo.py`) computes MRR/recall
offline (no LLM in retrieval/ablation mode) against baseline 0.4140 — but its
`adversarial` category is QA-trickery, NOT fact-versioning/retraction. There is no
measurement of "the newer version won" or "the useless belief was forgotten". Without a
reproducible, deterministic number, B/C are faith, not engineering.

## Objective

A reproducible offline eval that emits three deterministic, commit-comparable numbers:
MRR (vs 0.4140), taxa_freshness (frente C), taxa_forgetting (frente B). Reuse the LoCoMo
harness for MRR; add a small versioned adversarial set for freshness/forgetting.

## Requirements (EARS)

- **R1 (reuse MRR harness):** THE eval SHALL reuse the existing offline LoCoMo path
  (`benchmark_locomo.py --mode retrieval|ablation`, no LLM) to emit MRR comparable to the
  recorded baseline 0.4140.
- **R2 (adversarial set — versioning):** THE eval SHALL include a versioned pair set:
  a fact asserted as v1 then updated/retracted by v2, used to compute taxa_freshness =
  fraction of pairs where injection ranks v2 above v1.
- **R3 (adversarial set — forgetting):** THE eval SHALL include injected-but-unused
  beliefs, used to compute taxa_forgetting = fraction whose confidence dropped / left the
  top-k after the configured cycles.
- **R4 (deterministic + offline):** THE eval SHALL run without network or LLM (synthetic
  set versioned in-repo under `data/` or generated in code), producing the same numbers
  across runs on the same commit.
- **R5 (comparable across commits):** THE eval SHALL print the three metrics in a stable,
  diffable format so a before/after of B or C shows the delta.

## Acceptance criteria (measurable)

- [ ] `scripts/benchmarks/<eval>.py` runs offline, emits `{mrr, taxa_freshness,
  taxa_forgetting}` deterministically; MRR within tolerance of 0.4140 on the LoCoMo subset.
- [ ] On a build WITHOUT frente C, taxa_freshness < 1.0; WITH frente C, taxa_freshness == 1.0
  (the eval detects the improvement).
- [ ] On a build WITHOUT frente B, taxa_forgetting == 0.0; WITH frente B > 0.0.
- [ ] No LLM, no network; a pytest wraps it offline.

## Out of scope

- LLM-as-judge faithfulness/answer-relevance (needs provider; separate, costlier).
- Full RAGAS metric suite (context precision/recall) — context precision is frente A
  (design-open, multi-IA research).

## Notes

G0 (seven): MRR is pure math (locomo_evaluator.py:38-43), harness auto-downloads dataset
and runs offline in retrieval/ablation; LoCoMo's `adversarial` category is QA-trickery,
not versioning — needs a NEW small set; extend `run_ablation` pattern. No schema for the
eval itself.
