---
source: internal
created: 2026-06-04
status: implementing
depends_on: §8 (merged PR#15)
---

# §13 — Tool Registry Wiring

## Objetivo

Completar a extração de `server_impl.py` conectando o `TOOL_REGISTRY` declarativo (já implementado) ao runtime. Eliminar 1171 linhas de `types.Tool()` inline e 53 elif branches de dispatch.

## Pré-requisitos (todos ✅)

- §8 Handler Extraction (PR#15 merged) — handlers existem em `server/handlers/`
- `tools/registry.py` — 25 ToolDef declarativas com annotations corretas
- `tests/test_tool_registry.py` — 12 testes validando annotations, groups, duplicatas

## Arquivos a Modificar

| Arquivo | Ação |
|---------|------|
| `src/mcp_memory_service/tools/routing.py` | CRIAR — routing table {name: handler} |
| `src/mcp_memory_service/tools/__init__.py` | EDITAR — exportar ROUTING_TABLE |
| `src/mcp_memory_service/server_impl.py` | REESCREVER list_tools + call_tool, REMOVER thin wrappers |
| `tests/test_tool_registry.py` | EDITAR — adicionar testes de routing |

## Design

### 1. routing.py — Tabela de Roteamento

```python
"""Routing table: maps tool names to handler callables."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..server_impl import MCPMemoryServer

# Lazy import pattern (validated by doobidoo in PR#15 discussion):
# "intentional — prevents circular dependency and keeps cold start fast.
#  Python caches module imports after first call."

def _route(module_path: str, func_name: str):
    """Create a lazy-loading handler reference."""
    async def _handler(server: "MCPMemoryServer", arguments: dict):
        from importlib import import_module
        mod = import_module(module_path, package="mcp_memory_service")
        func = getattr(mod, func_name)
        return await func(server, arguments)
    _handler.__qualname__ = f"{module_path}.{func_name}"
    return _handler

ROUTING_TABLE: dict[str, callable] = {
    # Core memory
    "memory_store": _route(".server.handlers.memory", "handle_store_memory"),
    "memory_observe": _route(".server.handlers.memory", "handle_memory_observe"),
    # ... 25 tools total
}
```

### 2. list_tools() — Nova implementação (~15 linhas)

```python
from .tools import TOOL_REGISTRY

async def list_tools(self) -> List[types.Tool]:
    """Return canonical MCP tool list from declarative registry."""
    return [
        types.Tool(
            name=td.name,
            description=td.description,
            inputSchema=td.input_schema,
            annotations=types.ToolAnnotations(**td.annotations) if td.annotations else None,
        )
        for td in TOOL_REGISTRY
    ]
```

### 3. call_tool() — Nova implementação (~30 linhas)

```python
from .tools import ROUTING_TABLE
from .compat import is_deprecated, transform_deprecated_call

async def call_tool(self, name: str, arguments: dict | None) -> List[types.TextContent]:
    if arguments is None:
        arguments = {}
    
    # Deprecated name rewriting (preserve compat layer)
    if is_deprecated(name):
        name, arguments = transform_deprecated_call(name, arguments)
    
    # Route to handler
    handler = ROUTING_TABLE.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")
    
    logger.info("=== HANDLING TOOL CALL: %s ===", _sanitize_log_value(name))
    return await handler(self, arguments)
```

### 4. Remover thin wrappers

Os ~45 métodos `self.handle_X` que fazem apenas:
```python
async def handle_store_memory(self, arguments):
    from .server.handlers import memory as memory_handlers
    return await memory_handlers.handle_store_memory(self, arguments)
```

São redundantes com a routing table — deletar.

## Constraints (validadas com doobidoo)

1. **Lazy imports obrigatórios** — evitar circular deps (PR#15 discussion)
2. **Annotations preservadas exatamente** — readOnlyHint/destructiveHint drive OAuth scope (GHSA-2r68-g678-7qr3)
3. **Compat layer intocada** — deprecated name rewriting continua funcionando
4. **1 PR por §** — não bundlear com outras mudanças
5. **Suite verde** — rodar pytest completo antes de submeter

## Resultado Esperado

- server_impl.py: 3589 → ~2200 linhas (-1300)
- Routing centralizado e testável
- Novos handlers (§3/§4/§5/§6) se registram apenas adicionando entrada na routing table
- NLI on_store (handlers/memory.py) fica imediatamente ativo (era unreachable porque server_impl.py era o entrypoint)

## Não Faz Parte

- §9 (split config.py) — separado
- §10 (decompose sqlite_vec.py) — separado
- Migração de handlers que ainda são métodos complexos de self — só os thin wrappers
- Mudança de comportamento de qualquer tool
