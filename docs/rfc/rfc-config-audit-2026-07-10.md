# RFC: Configuration Audit & Optimization — filhocf fork

**Date**: 2026-07-10
**Author**: filhocf (Claudio Ferreira Filho)
**Status**: ACTIVE — findings from 2-day deep investigation (09-10/jul/2026)

## Context

After running consolidation for the first time successfully (26K associations, 125 clusters),
we discovered multiple configuration gaps and design behaviors we weren't aware of.
This document captures ALL findings for future reference.

## 1. Critical Fixes Applied (09-10/jul/2026)

### 1.1 include_embeddings regression (PR #126 upstream)
- **Problem**: PR #985 (ours) accidentally removed `include_embeddings=True` from consolidator
- **Cause**: Gemini reviewer feedback during incremental time_horizon PR
- **Impact**: Consolidation ran with 0 results since PR #985 merged
- **Fix**: Restore `include_embeddings=True` in `_get_memories_for_horizon()` (3 call sites)
- **Status**: PR #126 open upstream + applied in fork

### 1.2 GRAPH_STORAGE_MODE feedback loop
- **Problem**: `dual_write` (default) stores associations as both graph edges AND memories
- **Impact**: Bank grew 18K→44K (27K association-memories). Feedback loop: consolidation processes association-memories → creates meta-associations → unbounded growth
- **Cause**: We never read the `.env.example` which recommends migrating to `graph_only`
- **Fix**: `MCP_GRAPH_STORAGE_MODE=graph_only` + `MCP_CONSOLIDATION_STORE_ASSOCIATIONS=false` + cleanup 27K memories
- **Status**: ✅ Applied locally. NOT an upstream bug — documented behavior.

### 1.3 contradiction_check json parse error
- **Problem**: Scheduler crashed every 6h with "Expecting value: line 1 column 1"
- **Cause**: `handle_memory_conflicts` returns plaintext "No unresolved conflicts found." when empty, but scheduler did `json.loads()` on it
- **Fix**: try/except around json.loads, skip plaintext responses
- **Status**: ✅ Applied in fork. Could be PR upstream (trivial).

### 1.4 PreToolUse hook MCP tools (Kiro CLI specific)
- **Problem**: Kiro CLI passes `@server/tool_name` for MCP tools, not `tool_name`
- **Fix**: `TOOL_PURE="${TOOL##*/}"` in pre-enforcement.sh
- **Status**: ✅ Applied. Kiro CLI behavior, not mcp-memory-service.

### 1.5 kiro-session-reaper killing legitimate sessions
- **Problem**: 171 kills in 42 days, including legitimate idle sessions
- **Fix**: Disabled from cron. No longer needed (Kiro CLI improved lifecycle).
- **Status**: ✅ Disabled.

## 2. Design Behaviors We Misunderstood

### 2.1 NLI on_store lives ONLY in MCP handler
- **Location**: `server/handlers/memory.py` lines 248-270
- **Implication**: `MemoryService.store_memory()` (used by harvest, auto_capture, internal code) BYPASSES contradiction detection
- **Our expectation**: NLI runs on every memory stored
- **Reality**: NLI only runs when memory is stored via MCP tool call from agent
- **Impact**: 2,272 harvested memories entered without contradiction check
- **Possible fix**: Implement batch contradiction check post-harvest (fork feature)

### 2.2 bootstrap_profile ignores task_summary
- **Parameter**: `task_summary` is accepted in the tool schema but NEVER used for ranking
- **What it actually does**: `list_memories(page_size=20)` per type → returns 20 MOST RECENT
- **Our expectation**: Profile contextual to current task
- **Reality**: Profile reflects most recent activity regardless of task
- **Possible fix**: Replace `list_memories` with `memory_search(query=task_summary)` for contextual ranking

### 2.3 Consolidation horizons — "daily" does NOTHING for clustering
- **ENABLED_PHASES config**:
  - daily: ONLY decay scoring (no clustering, no associations, no compression)
  - weekly: clustering + associations + compression
  - monthly: + forgetting
  - quarterly/yearly: deep archival
- **Our mistake**: Running `daily` and expecting clusters
- **Fix**: Use `weekly` for productive consolidation. ✅ Already corrected.

### 2.4 Beliefs _NOISE_PREFIXES filter existed but stale beliefs not cleaned
- **Filter**: `_NOISE_PREFIXES` in `belief_service.py` prevents NEW noise beliefs
- **Problem**: 1,958 beliefs created BEFORE filter was added remained in table
- **Fix**: SQL purge + expanded prefixes. ✅ Applied.

## 3. Configuration Gaps (should add to our env file)

| Env Var | Recommendation | Why |
|---------|---------------|-----|
| `MCP_SCHEDULE_MONTHLY=01 04:00` | ADD | Deep consolidation + forgetting |
| `MCP_MEMORY_INCLUDE_HOSTNAME=true` | ADD | 3-machine setup needs origin tagging |
| `MCP_FORGETTING_ACCESS_THRESHOLD=180` | ADD | Protect rarely-accessed references (90 days too aggressive) |
| `MCP_MEMORY_SQLITE_PRAGMAS=journal_mode=WAL,busy_timeout=15000,cache_size=20000` | CONSIDER | Explicit control for concurrent access |

## 4. Unused Features Available

| Feature | Since | What it does | Priority for us |
|---------|-------|-------------|-----------------|
| `MCP_ENTITY_EXTRACTOR_MODULES` | v11.4.0 | Pluggable domain NER | HIGH (our pt_br locale) |
| `scoring="composite"` | v11.2.0 | Graph+semantic reranking | HIGH (better search) |
| `memory_consolidate(action="merge")` | v11.4.0 | Merge N memories into 1 | MEDIUM (manual dedup) |
| `time_horizon="incremental"` | v10.64.0 | Bounded-latency consolidation | MEDIUM (hook integration) |
| Temporal edges `valid_from/valid_until` | v10.68.0 | Point-in-time queries | LOW |
| Fact mutability classification | v10.68.0 | stable/volatile/ephemeral | LOW |

## 5. Next Actions

- [ ] Add env vars from section 3
- [ ] Implement batch contradiction check post-harvest (fork)
- [ ] Fix bootstrap_profile to use task_summary for ranking (fork, evaluate for upstream PR)
- [ ] Evaluate `scoring="composite"` for memory_search default
- [ ] Audit onboarding guide against our actual usage
- [ ] Submit contradiction_check json parse fix as upstream PR (trivial, high value)
