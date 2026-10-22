# Spec: §8 Handler Extraction from server_impl.py

**Date:** 2026-06-01
**Branch:** `refactor/s8-handler-extraction` (create from `main`)
**Repo:** `~/git/mcp-memory-service`
**Tests:** ALL existing tests MUST pass unchanged. No new tests needed (pure refactoring).

---

## Objective

Extract 18 inline handler methods from `server_impl.py` into handler modules following the existing delegation pattern. After extraction, `server_impl.py` should be ~2200 lines (down from ~4400).

## Delegation Pattern (FOLLOW EXACTLY)

### In the handler module (e.g., `server/handlers/harvest.py`):
```python
async def handle_memory_harvest(server, arguments: dict) -> List[types.TextContent]:
    """Harvest memories from session transcripts."""
    # ... logic moved here ...
```

### In `server_impl.py` (thin stub):
```python
async def handle_memory_harvest(self, arguments: dict) -> List[types.TextContent]:
    """Harvest memories (delegates to handler)."""
    from .server.handlers import harvest as harvest_handlers
    return await harvest_handlers.handle_memory_harvest(self, arguments)
```

Key: `self` is passed as first arg `server` to the module-level function.

---

## Extraction Map

### 1. Create `src/mcp_memory_service/server/handlers/harvest.py`

Move from server_impl.py:
- `handle_memory_harvest` (L3119, 188 lines)
- `handle_memory_distill` (L3361, 89 lines)

### 2. Create `src/mcp_memory_service/server/handlers/session.py`

Move from server_impl.py:
- `handle_commit_session_legacy` (L3534, 91 lines)
- `handle_get_bootstrap_profile` (L3800, 141 lines)
- `_post_commit_learning` (helper, called by commit_session_legacy)
- `_scheduled_distill_check` (helper)
- `_scheduled_contradiction_check` (helper)
- `_check_consolidation_threshold` (helper)
- `_background_consolidation` (helper)
- `_increment_session_counter` (helper)
- `_get_session_count` (helper)
- `_reset_session_counter` (helper)
- `_get_bootstrap_resource_uri` (static helper)
- `_read_bootstrap_resource` (helper)

NOTE: The scheduler helpers (`_scheduled_*`, `_check_consolidation_threshold`, `_background_consolidation`) access `self._consolidation_counter` and `self._distill_lock`. These should remain as methods on the class OR be passed the relevant state. Evaluate which is cleaner — if they need >2 attributes from self, keep them as class methods and only extract the public handlers.

### 3. Add to existing `src/mcp_memory_service/server/handlers/memory.py`

Move from server_impl.py:
- `handle_mistake_note_add` (L3492, 11 lines)
- `handle_mistake_note_search` (L3503, 9 lines)
- `handle_mistake_note_update` (L3512, 13 lines)
- `handle_mistake_note_delete` (L3525, 9 lines)

### 4. Add to existing `src/mcp_memory_service/server/handlers/quality.py`

Move from server_impl.py:
- `handle_memory_conflicts` (L3450, 15 lines)
- `handle_memory_resolve` (L3465, 27 lines)

### 5. Create `src/mcp_memory_service/server/handlers/protocol.py`

Move from server_impl.py (the nested functions inside `register_handlers`):
- Resource listing/reading logic (L1001–L1126)
- Resource templates logic (L1127–L1150)
- Prompts listing/getting logic (L1151–L1485)

These are currently nested `async def` inside `register_handlers()`. Extract them as module-level functions that receive `server` as first arg.

---

## What NOT to extract (keep in server_impl.py)

- `__init__` and initialization logic
- `register_handlers` method (but empty its nested functions)
- `handle_call_tool` dispatcher (the routing switch)
- `handle_list_tools` (will be extracted to tool_registry.py in a SEPARATE PR)
- Storage initialization methods
- Any method that accesses >3 private attributes of self (too coupled)

---

## Validation

After ALL extractions:
```bash
cd ~/git/mcp-memory-service
.venv/bin/python -m pytest tests/ -x -q --timeout=120
```

ALL tests must pass. If any test fails, the extraction is wrong — revert and fix.

---

## Commit Strategy

One commit per extraction group:
1. `refactor: extract harvest handlers to server/handlers/harvest.py`
2. `refactor: extract session handlers to server/handlers/session.py`
3. `refactor: move mistake_note handlers to server/handlers/memory.py`
4. `refactor: move conflict handlers to server/handlers/quality.py`
5. `refactor: extract protocol handlers to server/handlers/protocol.py`

Run tests after EACH commit. Do not batch.
