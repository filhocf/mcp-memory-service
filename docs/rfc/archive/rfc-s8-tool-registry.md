# Spec: §8 Extract Inline Handlers (Phase 1 — Tool Registry)

**Date:** 2026-06-01
**Branch:** `refactor/s8-tool-registry` (from `main`)
**Repo:** `~/git/mcp-memory-service`
**Refs:** Codeberg issue #7, doobidoo comment (§8 approved)

---

## Scope (Phase 1 only)

Extract the **tool definitions** (list_tools) into a declarative registry. This is the highest-value extraction because:
1. list_tools() is ~1500 lines of tool schema definitions mixed with logic
2. Annotations (readOnlyHint/destructiveHint) drive OAuth scope — must be preserved exactly
3. A registry makes it trivial to verify annotations via test assertions

Phase 2 (extract handler implementations) is a separate PR.

---

## Design

### Tool Registry (`src/mcp_memory_service/tools/registry.py`)

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]
    annotations: dict[str, Any] = field(default_factory=dict)
    # annotations example: {"readOnlyHint": True, "title": "Search Memories"}

# All tools defined declaratively
TOOL_REGISTRY: list[ToolDef] = [
    ToolDef(
        name="memory_store",
        description="Store new information...",
        input_schema={...},
        annotations={"readOnlyHint": False, "destructiveHint": False, "title": "Store Memory"},
    ),
    # ... all tools
]
```

### list_tools() becomes trivial

```python
async def handle_list_tools(self) -> List[types.Tool]:
    from .tools.registry import TOOL_REGISTRY
    return [
        types.Tool(
            name=t.name,
            description=t.description,
            inputSchema=t.input_schema,
            annotations=types.ToolAnnotations(**t.annotations) if t.annotations else None,
        )
        for t in TOOL_REGISTRY
    ]
```

### Annotation Preservation Test

```python
def test_all_tools_have_annotations():
    """Every tool MUST have readOnlyHint set (doobidoo requirement: OAuth scope)."""
    from mcp_memory_service.tools.registry import TOOL_REGISTRY
    for tool in TOOL_REGISTRY:
        assert "readOnlyHint" in tool.annotations, f"{tool.name} missing readOnlyHint"

def test_mutating_tools_not_readonly():
    """Tools that write data must NOT be marked read-only."""
    MUTATING = {"memory_store", "memory_delete", "memory_update", ...}
    for tool in TOOL_REGISTRY:
        if tool.name in MUTATING:
            assert tool.annotations.get("readOnlyHint") is False, f"{tool.name} should not be read-only"

def test_registry_matches_current_list_tools():
    """Registry produces identical output to current list_tools (no regression)."""
    # Compare tool names, schemas, and annotations with current implementation
```

---

## Extraction Process

1. Read current `handle_list_tools()` in server_impl.py (the inner function at line ~1486)
2. Extract each `types.Tool(...)` definition into a `ToolDef` in the registry
3. Preserve ALL fields exactly: name, description, inputSchema, annotations
4. Replace the inline definitions with a loop over TOOL_REGISTRY
5. Run tests to verify identical output

---

## Files

- `src/mcp_memory_service/tools/__init__.py` — new package
- `src/mcp_memory_service/tools/registry.py` — TOOL_REGISTRY (~400 lines, declarative)
- `src/mcp_memory_service/server_impl.py` — replace list_tools body (~-1400 lines, +10 lines)
- `tests/test_tool_registry.py` — annotation assertions (~60 lines)

---

## Commit Strategy

1. `refactor(tools): extract tool definitions to declarative registry`
2. `test(tools): annotation preservation assertions`

---

## Critical Rule

**Every tool annotation MUST be preserved exactly.** readOnlyHint and destructiveHint drive OAuth scope at the HTTP layer (GHSA-2r68-g678-7qr3). A tool silently losing its read-only marking is a security regression.
