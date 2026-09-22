# RFC: Quality Model — computed score vs human rating

**Date:** 2026-09-22
**Author:** Claudio + Zero (Kiro CLI)
**Branch:** `design/quality-model` (from fork `main`)
**Status:** DRAFT v0.1 — internal maturation before upstream discussion
**Area:** `quality/` (we are CODEOWNER)
**Prior art (do not reinvent):** `docs/rfc/rfc-self-service-memory-intelligence.md` §4 ("confidence + provenance first-class, separate from the raw score"); `original_quality_before_boost` precedent in `consolidation/decay.py:289`.

---

## 1. Problem (plain language)

Today `quality_score` is a single overloaded field. Six different sources write to it — the AI scorer, the implicit scorer, the async batch scorer, manual rating (MCP and HTTP twins), the decay association-boost, and Milvus conflict resolution. Ten consumers read it — decay multiplier, forgetting retention thresholds, four rerank weights, graph sort, analytics tiers, and bootstrap ranking — and **none of them can tell where the number came from**.

The concrete failure: when a human rates a memory, the rating is blended (`0.6*user + 0.4*existing`) into the same `quality_score` the machine computes. The human opinion and the machine guess overwrite each other in one field. The human's rating can be diluted or lost; the machine's guess can erase the human's judgment. "One notebook, scribbled over by two teachers."

Empirical state (this deployment, 22,709 memories): 246 have `quality_score` (1.1%), **zero** have `quality_provider`, 138 have `user_rating`. Effective quality today = human rating + a 0.5 default. The AI scorer has effectively never persisted here.

## 2. Goal

Separate **human opinion** from **machine guess**, and make the human opinion authoritative. The value the system uses for ranking and forgetting must reflect: *if the user rated it, the user's rating wins; otherwise use the machine's computed score.*

## 3. Decisions (taken)

- **D1 — Two separate signals, not one field.** Keep the human rating and the computed score as distinct, each preserving its own origin and history. (Two notebooks, not one.)
- **D4 — Human opinion wins, always.** When a user rating exists, it is authoritative for every consumer (ranking + forgetting). The computed score applies only when there is no user rating. This is override-with-preservation, **not** a fixed blend. The old `0.6*user + 0.4*existing` blend is removed — it is the root of the confusion.
- **D4a — A negative rating means "don't surface", not "destroy".** A 👎 lowers the memory in search ranking immediately, but a single 👎 does **not** trigger aggressive forgetting. This separates two axes that were collapsed: *relevance in search* vs *survival in the store*. Rationale: "the human disapproves of this content" ≠ "this is unimportant" — a hard lesson (`NEVER do X`) may earn a 👎 yet must be preserved. **Multiple 👎 (accumulated in `rating_history`) do lead to forgetting** — repeated disapproval is genuine disposability.

## 4. Model

Two **origin** fields, both additive (no schema change; live in `metadata` like `source_type`):

- `computed_quality` — the machine's score, written by the scorer/ai_evaluator, carrying its existing `quality_provider` + `quality_components` (provenance preserved).
- `user_rating` — the human signal (already exists: rating/feedback/timestamp/history), untouched by the machine.

**Effective quality is materialized on write, not projected on read.** When a rating or a computed score is written, the composed effective value is written into the existing `metadata['quality_score']`. This is deliberate: ~7 consumers read `metadata.get('quality_score')` **raw** (bypassing the `Memory.quality_score` property), including a real ranking path (`web/api/search.py:196,212`) and two that operate on plain dicts with no `Memory` object at all (`storage/mixins/retrieve.py:866`, `harvest/bootstrap_utils.py:106`). A read-time projection would miss all of these. Materializing at write time means every existing reader gets the correct value with **zero consumer changes**.

Composition rule written into `quality_score`:

```
effective_quality(memory):
    if user_rating is present:
        base = normalize(user_rating)      # human wins (ranking axis)
    elif computed_quality is present:
        base = computed_quality            # machine fallback
    else:
        base = 0.5                         # legacy/unknown default (unchanged)
    return base
```

The origin fields (`computed_quality`, `user_rating`) are preserved separately so a later recompute or rating removal can re-derive `quality_score` without losing history. `quality_score` stops being "the machine's number" and becomes "the effective number everyone already reads" — semantically compatible with D4 (human wins → the human value is what gets materialized).

**Forgetting axis (D4a) reads `rating_history`, not just the effective score.** Aggressive archival requires N accumulated 👎, not a single one — so a one-off negative rating de-ranks in search but does not delete a preserved lesson.

## 5. Open sub-decisions (to resolve in this RFC)

### D2 — Provenance honesty
The manual rating must not masquerade as a machine provider. Two candidates:
- (a) Add `user_rating` as an explicit code `'ur'` to `PROVIDER_CODES` (`metadata_codec.py:27-38`) so sync round-trips honestly instead of silently degrading to `'im'` (implicit).
- (b) Keep `quality_provider` strictly for machines; represent rating provenance in the separate `user_rating` field only (never in provider).
**Recommendation:** (b) — provider stays "which engine computed", rating lives in its own field. `effective_quality` knows the source by *which field is set*, not by a provider label. Simpler, no closed-vocabulary surgery.

### D3 — Reversibility
When the machine later recomputes, it writes `computed_quality` — it must **never** clobber `user_rating`. Because the two are separate fields (D1), reversibility is free: removing a rating falls back to `computed_quality` automatically. No `original_quality_before_rating` needed — separation gives it for free. (Contrast: the boost needed `original_quality_before_boost` precisely because it overwrote the single field.)

### D5 — Backward compat & sync
- Existing 138 rated memories: `user_rating` already present; a one-shot backfill can set `computed_quality = quality_score` where a machine score exists, so nothing is lost.
- Sync (`compress_metadata_for_sync`, `metadata_codec.py:279-299`) currently DISCARDS `user_rating`/`rating_history` — only the effect on `quality_score` travels. To make the human opinion sync across machines (our multi-host setup), `user_rating` must enter the sync schema as a new positional CSV field.
- **PREREQUISITE, not a footnote — codec versioning.** The CSV is positional (`metadata_codec.py:186-190`, 13/16 field variants). Adding `user_rating` as a new positional field means a host running an *older* codec that reads a row with the new field will silently ignore it → the rating does not propagate until every host is upgraded. This must be gated by an explicit codec version bump, and rolled out before relying on cross-host rating sync. Decode of older rows stays backward-compatible (missing field → absent, not error).

## 6. Consumers — impact
None change behavior on day one. Because effective quality is **materialized into `metadata['quality_score']` on write** (§4), every existing reader — including the ~7 that read the raw metadata and the two that operate on plain dicts — transparently gets the composed value. Follow-up: consumers that want the split (e.g. analytics distinguishing human-approved vs machine-scored) read the two origin fields (`computed_quality`, `user_rating`) directly.

Note: both rating twins must be touched together — `handle_rate_memory` (MCP, `server/handlers/quality.py:176`) and `rate_memory` (HTTP, `web/api/quality.py`) — to avoid the drift already latent between them.

## 7. Out of scope
- The composite ranking (hybrid recall + ranked rerank) — separate item (f4114d8b), consumes whatever `quality_score` (materialized effective) returns.
- Turning on the AI scorer (F1) — depends on this model landing first, so computed vs rating don't fight.

## 8. Open questions for upstream (doobidoo)
- **Normalization of `user_rating` into effective quality.** The rating is `-1/0/+1`. How should it map onto the `0..1` effective scale that decay/forgetting/ranking consume? The current blend does `(rating+1)/2` → 👎 = 0.0 exactly, which under "human wins" would drop a memory to the floor. Options: a floor above 0 for 👎 (de-rank without min-retention), or a dedicated rating→quality curve. Prefer to settle this with you since it feeds the retention thresholds you own.
- **Accumulation threshold for D4a (negative-rating forgetting).** A single 👎 de-ranks but must not delete; multiple 👎 lead to forgetting. What is the exact criterion read from `rating_history` — N distinct negative ratings? A net-negative sum? Over what window? This needs to fit the existing retention model in `forgetting.py`, which you know best.
- **Materialization vs read-time projection.** We chose to materialize effective quality into `quality_score` at write time (vs a property-based read-time projection) because ~7 consumers read the raw metadata field and two operate on plain dicts with no `Memory` object. Is materialization acceptable, or is there a reader you'd rather keep authoritative?
- **Sync schema change for `user_rating`.** Making the human opinion sync across hosts needs `user_rating` in the CSV codec, gated by a codec version bump (older hosts silently ignore the new positional field until upgraded). Acceptable to coordinate a codec version for this?
