# RFC: Structural Improvements for mcp-memory-service

**Author:** architect-analysis  
**Date:** 2026-06-01  
**Status:** Draft  
**Continues from:** RFC #1 (§0–§7)

---

## Summary Table

| § | Title | Priority | Effort | Risk | Dependencies |
|---|-------|----------|--------|------|--------------|
| §8 | Extract remaining inline handlers from server_impl.py | P0 | 3d | Low | None |
| §9 | Split config.py by domain | P1 | 2d | Medium | None |
| §10 | Decompose sqlite_vec.py into focused modules | P1 | 4d | Medium | §8 |
| §11 | Make torch/transformers optional (ONNX-first) | P2 | 3d | High | None |
| §12 | Add pytest-cov to CI and establish coverage baseline | P0 | 1d | Low | None |

**Total estimated effort:** 13 developer-days  
**Breaking changes:** §11 only (dependency change for pip users without extras)

---

## §8 — Extract Remaining Inline Handlers from server_impl.py

### Problem

`server_impl.py` is 4396 lines. The `MemoryServer` class has 62 handler methods. While 43 already delegate to `server/handlers/*.py`, **18 handlers still contain inline logic** totaling ~900 lines of business logic that should live in handler modules:

| Handler | Line | Lines of Logic | Target Module |
|---------|------|----------------|---------------|
| `handle_memory_harvest` | 3035 | 188 | `handlers/harvest.py` (new) |
| `handle_memory_distill` | 3277 | 89 | `handlers/harvest.py` (new) |
| `handle_memory_conflicts` | 3366 | 15 | `handlers/quality.py` |
| `handle_memory_resolve` | 3381 | 27 | `handlers/quality.py` |
| `handle_mistake_note_add` | 3408 | 11 | `handlers/memory.py` |
| `handle_mistake_note_search` | 3419 | 9 | `handlers/memory.py` |
| `handle_mistake_note_update` | 3428 | 13 | `handlers/memory.py` |
| `handle_mistake_note_delete` | 3441 | 9 | `handlers/memory.py` |
| `handle_commit_session_legacy` | 3450 | 91 | `handlers/session.py` (new) |
| `handle_get_bootstrap_profile` | 3716 | 141 | `handlers/session.py` (new) |

Additionally, `list_tools()` (lines 1512–2674, **1163 lines**) is a single method containing all tool schema definitions as inline dicts. This should be extracted to a declarative registry.

The `register_handlers` method (line 998) contains 5 nested async functions for resources/prompts (lines 1001–1485, **484 lines**) that should be in a `handlers/protocol.py`.

### Proposed Solution

1. **Create `server/handlers/harvest.py`** — move `handle_memory_harvest` and `handle_memory_distill` logic.
2. **Create `server/handlers/session.py`** — move `handle_commit_session_legacy`, `handle_get_bootstrap_profile`, and helper methods (`_post_commit_learning`, `_scheduled_distill_check`, `_scheduled_contradiction_check`, `_increment_session_counter`, `_get_session_count`, `_reset_session_counter`).
3. **Move mistake_note_* handlers** to existing `handlers/memory.py`.
4. **Move conflict handlers** to existing `handlers/quality.py`.
5. **Create `server/tool_registry.py`** — extract tool schema definitions from `list_tools()` into a declarative list. The method becomes a 5-line loader.
6. **Create `server/handlers/protocol.py`** — extract resource/prompt handlers from `register_handlers`.

After extraction, `server_impl.py` should be ~2200 lines: class init, storage initialization, `call_tool` dispatcher, and thin delegation stubs.

### Files Affected

- `src/mcp_memory_service/server_impl.py` (reduce from 4396 → ~2200 lines)
- `src/mcp_memory_service/server/handlers/harvest.py` (new, ~300 lines)
- `src/mcp_memory_service/server/handlers/session.py` (new, ~350 lines)
- `src/mcp_memory_service/server/handlers/memory.py` (add ~50 lines)
- `src/mcp_memory_service/server/handlers/quality.py` (add ~50 lines)
- `src/mcp_memory_service/server/handlers/protocol.py` (new, ~500 lines)
- `src/mcp_memory_service/server/tool_registry.py` (new, ~1200 lines)
- `src/mcp_memory_service/server/handlers/__init__.py` (update exports)

### Effort Estimate

3 developer-days (mechanical extraction, no logic changes)

### Dependencies

None — can start immediately.

### Migration Strategy

Pure refactoring. All handler signatures remain identical. The `self` parameter is passed as first arg to module-level functions (existing pattern in `handlers/memory.py`). No API changes.

---

## §9 — Split config.py by Domain

### Problem

`config.py` is 1327 lines mixing 8 distinct configuration domains into a single flat namespace:

| Domain | Lines (approx) | Variables |
|--------|---------------|-----------|
| Environment/dotenv loading | 34–68 | Helper functions |
| Path resolution | 245–288 | `BASE_DIR`, `BACKUPS_PATH`, etc. |
| Storage backend selection | 305–568 | `STORAGE_BACKEND`, SQLite, Cloudflare, Milvus, Hybrid configs |
| HTTP/SSE/Transport | 570–615 | `HTTP_PORT`, `MCP_SSE_*`, CORS, TLS |
| OAuth | 764–1011 | 30+ OAuth variables |
| Quality system | 1033–1095 | `MCP_QUALITY_*`, hybrid search |
| Consolidation | 1120–1195 | `MCP_CONSOLIDATION_*`, graph modes |
| Feature flags & misc | 1196–1327 | Custom types, maintenance, entity extraction |

The file also contains 3 utility functions (`safe_get_int_env`, `safe_get_bool_env`, `safe_get_optional_int_env`) that are used everywhere but defined inline.

### Proposed Solution

Split into a `config/` package:

```
src/mcp_memory_service/config/
├── __init__.py          # Re-exports all public names (backward compat)
├── _env.py              # dotenv loading, safe_get_* helpers
├── paths.py             # BASE_DIR, BACKUPS_PATH, SQLITE_VEC_PATH
├── storage.py           # Backend selection, SQLite, Cloudflare, Milvus, Hybrid
├── transport.py         # HTTP, SSE, CORS, TLS, mDNS
├── oauth.py             # All OAuth configuration
├── quality.py           # Quality system, hybrid search
├── consolidation.py     # Consolidation, graph modes
└── features.py          # Feature flags, custom types, maintenance
```

The `__init__.py` re-exports every public constant so that existing `from .config import X` imports continue working unchanged.

### Files Affected

- `src/mcp_memory_service/config.py` → `src/mcp_memory_service/config/` (8 files)
- No other files need changes (re-exports maintain backward compatibility)

### Effort Estimate

2 developer-days

### Dependencies

None — can be done in parallel with §8.

### Breaking Changes

None. The `__init__.py` re-exports maintain the existing import interface:
```python
from .config import STORAGE_BACKEND, SQLITE_VEC_PATH  # still works
```

---

## §10 — Decompose sqlite_vec.py into Focused Modules

### Problem

`sqlite_vec.py` is 4504 lines — the largest file in the codebase. It contains the full `SqliteVecMemoryStorage` class with responsibilities spanning:

| Responsibility | Lines (approx) | Methods |
|---------------|----------------|---------|
| Initialization & extension loading | 229–1266 | `__init__`, `initialize`, `_load_sqlite_vec_extension`, `_initialize_embedding_model` |
| CRUD operations | 1267–1603 | `store`, `store_batch`, `delete`, `get_by_hash`, `update_memory_metadata` |
| Search (vector + BM25 + hybrid) | 1603–2110 | `retrieve`, `retrieve_hybrid`, `_search_bm25`, `_fuse_scores`, `_fuse_rrf` |
| Tag-based queries | 2111–2365 | `search_by_tag`, `search_by_tags`, `search_by_tag_chronological` |
| Delete operations | 2366–2785 | `delete_by_tag`, `delete_by_tags`, `delete_by_timeframe`, `delete_before_date` |
| Metadata & stats | 2786–3521 | `get_stats`, `get_all_memories`, `count_all_memories`, `get_all_tags_with_counts` |
| Graph/visualization | 3522–4044 | `get_graph_visualization_data`, `get_relationship_type_distribution` |
| Conflict detection | 4045–4274 | `_detect_conflicts`, `_record_conflicts`, `get_conflicts`, `resolve_conflict` |
| Memory evolution | 4274–4504 | `retrieve_with_staleness`, `update_memory_versioned`, `get_memory_history` |

Note: Graph operations are already partially extracted to `storage/graph.py` (949 lines) via mixin/composition. The remaining graph methods in sqlite_vec.py are visualization-specific.

### Proposed Solution

Use a **mixin pattern** (already established with `graph.py`) to split the class:

```
src/mcp_memory_service/storage/
├── sqlite_vec.py          # Core class, init, CRUD (~1600 lines)
├── sqlite_vec_search.py   # Search mixin: retrieve, hybrid, BM25 (~600 lines)
├── sqlite_vec_tags.py     # Tag queries mixin (~300 lines)
├── sqlite_vec_stats.py    # Stats, metadata, listing (~500 lines)
├── sqlite_vec_conflicts.py # Conflict detection & resolution (~250 lines)
├── sqlite_vec_evolution.py # Versioned updates, history (~250 lines)
├── graph.py               # (existing, 949 lines — unchanged)
├── base.py                # (existing, 1375 lines — unchanged)
└── ...
```

The main class uses multiple inheritance:
```python
class SqliteVecMemoryStorage(
    SqliteVecSearchMixin,
    SqliteVecTagsMixin,
    SqliteVecStatsMixin,
    SqliteVecConflictsMixin,
    SqliteVecEvolutionMixin,
    MemoryStorage,
):
    ...
```

### Files Affected

- `src/mcp_memory_service/storage/sqlite_vec.py` (reduce from 4504 → ~1600 lines)
- `src/mcp_memory_service/storage/sqlite_vec_search.py` (new, ~600 lines)
- `src/mcp_memory_service/storage/sqlite_vec_tags.py` (new, ~300 lines)
- `src/mcp_memory_service/storage/sqlite_vec_stats.py` (new, ~500 lines)
- `src/mcp_memory_service/storage/sqlite_vec_conflicts.py` (new, ~250 lines)
- `src/mcp_memory_service/storage/sqlite_vec_evolution.py` (new, ~250 lines)

### Effort Estimate

4 developer-days (careful extraction needed — shared state via `self.conn`, `self._generate_embedding`, etc.)

### Dependencies

Should be done after §8 to avoid merge conflicts in the same PR cycle.

### Risks

- Mixin method resolution order (MRO) — Python's C3 linearization handles this but requires careful ordering.
- Shared private methods (`_row_to_memory`, `_run_in_thread`, `_execute_with_retry`) must remain in the base class.
- Test coverage for sqlite_vec is extensive (89K test file) — all tests must pass unchanged.

---

## §11 — Make torch/transformers Optional (ONNX-First)

### Problem

The core `dependencies` in `pyproject.toml` (lines 47–73) include:

```toml
"sentence-transformers>=2.2.2",
"torch>=2.0.0",
"transformers>=4.30,<5.0.0",
```

These pull ~2GB of downloads for a memory service that already has a working ONNX alternative (`embeddings/onnx_embeddings.py`). The `[sqlite]` optional extra already includes `onnxruntime`, but the base install still requires torch.

Current state:
- `USE_ONNX` config flag exists (line 399 of config.py)
- `onnx_embeddings.py` is fully functional (10K lines)
- `_HashEmbeddingModel` fallback exists in sqlite_vec.py (lines 159–227) for when no ML model loads
- The `[ml]` extra already groups torch/sentence-transformers

### Proposed Solution

1. **Move torch/sentence-transformers/transformers from `dependencies` to `[ml]` extra** (they're already duplicated there).
2. **Make ONNX the default embedding backend** when torch is not installed.
3. **Update `_initialize_embedding_model`** (sqlite_vec.py line 988) to:
   - Try ONNX first if `USE_ONNX=true` or torch is not importable
   - Fall back to sentence-transformers if available
   - Fall back to hash embeddings as last resort
4. **Update install docs** to recommend `pip install mcp-memory-service[sqlite]` for lightweight installs.

New dependency tree:
```toml
dependencies = [
    # ... (all current deps MINUS torch, sentence-transformers, transformers)
    "tokenizers>=0.22.2",  # keep — used by ONNX tokenizer
]

[project.optional-dependencies]
ml = [
    "sentence-transformers>=2.2.2",
    "torch>=2.0.0",
    "transformers>=4.30,<5.0.0",
]
sqlite = [
    "onnxruntime>=1.14.1",
]
```

### Files Affected

- `pyproject.toml` (move 3 deps from core to `[ml]`)
- `src/mcp_memory_service/storage/sqlite_vec.py` (`_initialize_embedding_model`, lines 988–1231)
- `src/mcp_memory_service/config.py` (default `USE_ONNX` to `true` when torch unavailable)
- `README.md` (update install instructions)
- `.github/workflows/` (CI already tests with ONNX — verify)

### Effort Estimate

3 developer-days (includes testing all embedding paths)

### Dependencies

None — independent of other sections.

### Breaking Changes

**Yes — for users who `pip install mcp-memory-service` without extras.**

Mitigation:
- Add a runtime warning on first use if no embedding backend is available
- Document the change in CHANGELOG as a **minor** version bump (not patch)
- The `[full]` extra continues to install everything
- Docker images continue to include `[ml]`

### Risk Assessment

- **High risk** if done carelessly — embedding model initialization is the most complex code path
- The `_HashEmbeddingModel` fallback (deterministic, no ML) already exists as safety net
- CI must test: (a) ONNX-only, (b) torch-only, (c) both, (d) neither (hash fallback)

---

## §12 — Add pytest-cov to CI and Establish Coverage Baseline

### Problem

- `pytest-cov` is listed in `[dev]` extras (line 80 of pyproject.toml) but **not used in CI workflows**
- `.coveragerc` exists (line in repo root) with extensive `omit` patterns
- `[tool.coverage.run]` and `[tool.coverage.report]` are configured in pyproject.toml (lines 137–175)
- **Actual coverage is unknown** — no baseline, no gate, no trend tracking

### Proposed Solution

1. **Add `--cov` flag to pytest in CI** (the main test workflow):
   ```yaml
   - run: pytest --cov=src/mcp_memory_service --cov-report=xml --cov-report=term-missing
   ```

2. **Upload coverage to Codecov or similar** for PR annotations.

3. **Set initial gate at 0%** (report-only) — do NOT block PRs on coverage initially.

4. **After 2 weeks**, analyze the baseline and set a reasonable gate (likely 40–50% given the extensive omit list).

5. **Add coverage badge** to README.

### Files Affected

- `.github/workflows/test.yml` (or equivalent CI workflow — add `--cov` flags)
- `pyproject.toml` (already configured — no changes needed)
- `README.md` (add badge)

### Effort Estimate

1 developer-day

### Dependencies

None — can be done immediately, in parallel with everything else.

### Breaking Changes

None.

---

## Priority Order (Execution Sequence)

```
Week 1:  §12 (coverage) + §8 (handler extraction) — in parallel
Week 2:  §9 (config split) + §8 continued
Week 3:  §10 (sqlite_vec decomposition)
Week 4:  §11 (ONNX-first) — requires most testing
```

Rationale:
- §12 first because it gives visibility into what §8–§11 might break
- §8 is P0 because it's the highest-impact, lowest-risk change
- §9 is independent and can overlap with §8
- §10 depends on §8 being merged (avoids conflicts in server_impl.py)
- §11 is last because it's the only breaking change and needs the most validation

---

## Appendix: Handlers Delegation Map (Current State)

### Already Delegating (43 handlers → server/handlers/*.py)

All handlers in `handle_store_memory`, `handle_memory_observe`, `handle_store_session`, `handle_retrieve_memory`, `handle_memory_search`, `handle_retrieve_with_quality_boost`, `handle_memory_list`, `handle_search_by_tag`, `handle_delete_memory`, `handle_memory_delete`, `handle_delete_by_tag`, `handle_delete_by_tags`, `handle_delete_by_all_tags`, `handle_cleanup_duplicates`, `handle_update_memory_metadata`, `handle_consolidate_memories`, `handle_memory_consolidate`, `handle_consolidation_status`, `handle_consolidation_recommendations`, `handle_scheduler_status`, `handle_trigger_consolidation`, `handle_pause_consolidation`, `handle_resume_consolidation`, `handle_debug_retrieve`, `handle_exact_match_retrieve`, `handle_get_raw_embedding`, `handle_recall_memory`, `handle_check_database_health`, `handle_get_cache_stats`, `handle_recall_by_timeframe`, `handle_delete_by_timeframe`, `handle_delete_before_date`, `handle_memory_ingest`, `handle_ingest_document`, `handle_ingest_directory`, `handle_memory_quality`, `handle_rate_memory`, `handle_get_memory_quality`, `handle_analyze_quality_distribution`, `handle_memory_graph`, `handle_find_connected_memories`, `handle_find_shortest_path`, `handle_get_memory_subgraph`.

### Still Inline (18 handlers — target of §8)

`handle_memory_harvest` (L3035, 188 lines), `handle_memory_distill` (L3277, 89 lines), `handle_memory_conflicts` (L3366, 15 lines), `handle_memory_resolve` (L3381, 27 lines), `handle_mistake_note_add` (L3408), `handle_mistake_note_search` (L3419), `handle_mistake_note_update` (L3428), `handle_mistake_note_delete` (L3441), `handle_commit_session_legacy` (L3450, 91 lines), `handle_get_bootstrap_profile` (L3716, 141 lines), plus protocol handlers: `handle_list_resources` (L1001), `handle_read_resource` (L1057), `handle_list_resource_templates` (L1127), `handle_list_prompts` (L1151), `handle_get_prompt` (L1242), `handle_list_tools` (L1486/1512, 1163 lines), `handle_call_tool` (L1490/2675).

---

## Appendix: config.py Domain Boundaries

| Lines | Domain | Key Variables |
|-------|--------|---------------|
| 34–100 | Env helpers | `_find_and_load_dotenv`, `safe_get_int_env`, `safe_get_bool_env` |
| 100–244 | Validation helpers | `safe_get_optional_int_env`, range validation |
| 245–304 | Paths | `BASE_DIR`, `BACKUPS_PATH`, `SQLITE_VEC_PATH` |
| 305–568 | Storage backends | `STORAGE_BACKEND`, Cloudflare, Hybrid, Milvus configs |
| 570–663 | Transport/HTTP | `HTTP_PORT`, SSE, CORS, TLS, mDNS, embedding model |
| 664–763 | Integrity/Consolidation | `INTEGRITY_CHECK_*`, `CONSOLIDATION_*` |
| 764–1032 | OAuth | 30+ OAuth variables, key loading, issuer detection |
| 1033–1095 | Quality | `MCP_QUALITY_*`, hybrid search, mistake note threshold |
| 1096–1195 | Consolidation advanced | Quality boost, graph storage mode |
| 1196–1327 | Features/Misc | Custom types, maintenance, entity extraction |

---

## Appendix: sqlite_vec.py Method Groups

| Group | Line Range | Method Count | Candidate Module |
|-------|-----------|--------------|------------------|
| Init/Extension | 229–1266 | 18 | Keep in sqlite_vec.py |
| CRUD | 1267–1603 | 4 | Keep in sqlite_vec.py |
| Search | 1603–2110 | 7 | `sqlite_vec_search.py` |
| Tag queries | 2111–2365 | 3 | `sqlite_vec_tags.py` |
| Delete ops | 2366–2785 | 7 | Keep in sqlite_vec.py (CRUD) |
| Stats/Listing | 2786–3521 | 12 | `sqlite_vec_stats.py` |
| Graph viz | 3522–4044 | 4 | `sqlite_vec_stats.py` |
| Conflicts | 4045–4274 | 4 | `sqlite_vec_conflicts.py` |
| Evolution | 4274–4504 | 4 | `sqlite_vec_evolution.py` |

---

## Non-Goals (Explicitly Out of Scope)

1. **Unifying 4 storage backends** — This is a much larger architectural decision (Strategy pattern, adapter layer). Deferred to a future RFC.
2. **Rewriting the consolidation system** — Already well-modularized in `consolidation/`.
3. **Removing deprecated tool names** — Handled by `compat.py`, low priority.
4. **Web/OAuth refactoring** — Separate concern, separate RFC.

## §13 — Wire Modular Handlers via Tool Registry + Routing Table

**Added:** 2026-06-04 (post-§8 merge)
**Status:** Implementing
**Depends on:** §8 (merged PR#15)
**Spec:** s13-tool-registry-wiring.md

### Context

§8 extracted handler *bodies* to `server/handlers/`. But `server_impl.py` still:
- Defines 21 `types.Tool()` inline in `list_tools()` (1171 lines)
- Dispatches via 53 `elif name ==` branches in `call_tool()`
- Has ~45 thin wrapper methods `self.handle_X` that just delegate

§13 completes the extraction by wiring the declarative `TOOL_REGISTRY` + a routing table.

### Deliverables

1. `tools/routing.py` — dict `{name: lazy_handler}` using lazy imports (validated by doobidoo)
2. `list_tools()` → iterate `TOOL_REGISTRY` (1171 lines → 15)
3. `call_tool()` → routing table lookup (53 elif → dict.get)
4. Remove thin wrappers (redundant with routing)

### Result

- server_impl.py: 3589 → ~2200 lines (-1300)
- New handlers register by adding 1 entry to routing table
- NLI on_store becomes reachable (was dead code with old dispatch)

### doobidoo Alignment

- Issue #7: "§8 yes please" + "annotations must be preserved" ✅ (12 tests)
- PR #15 discussion: "thin delegates are transitional" + "lazy imports intentional" ✅
- Issue #1: "§3 gets closest read since it touches core dispatch" — §13 is pure refactor, no behavior change
