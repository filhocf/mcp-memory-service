# Harvest: Suporte a Sessões Kiro IDE

**Data:** 2026-07-21
**Autor:** Claudio + Kiro
**Branch:** `feat/harvest-kiro-ide`
**Base:** `main`
**Versão:** 1.0

---

## 1. Problema

O harvest parser (`harvest/parser.py`) não reconhece sessões do Kiro IDE. Isso significa que ~75 sessões dos primeiros meses de trabalho (março–julho 2026) — onde foram tomadas decisões arquiteturais, resolvidos bugs e definidas convenções — nunca foram colhidas para o banco de memória.

### Evidências

1. **Formato diferente:** O IDE armazena sessões em `~/.kiro/sessions/{workspace_hash}/{session_uuid}/messages.jsonl` com estrutura `{id, timestamp, payload: {type, content}}` — nenhum dos parsers existentes reconhece isso.

2. **Detecção falha silenciosamente:** O auto-detect procura `"type" in obj` → match com Claude Code (errado), ou `"kind" in obj` → não existe no IDE. Na prática, como o IDE não tem arquivos `.jsonl` soltos na raiz (está dentro de subdirs), o `find_sessions()` nem os encontra.

3. **Volume:** 75 sessões migradas, 9 workspaces, meses março a julho 2026.

4. **Formato CLI verificado (21/jul/2026):** O Kiro CLI continua usando `{version:"v1", kind:"Prompt"/"AssistantMessage"/"ToolResults"}` — parser existente funciona perfeitamente. Apenas 3 kinds em uso.

### Causa raiz

```
find_sessions() → glob("*.jsonl") na raiz do project_dir
    → Não encontra IDE (está em subdir/subdir/messages.jsonl)
    → Sessões IDE ignoradas permanentemente

parse_file() → auto-detect por first line
    → IDE tem "payload" key (nenhum parser reconhece)
    → Retorna lista vazia
```

---

## 2. Solução

Extensão do bloco Kiro existente no parser — NÃO é feature nova.

### 2.1 Novo parser: `_parse_kiro_ide_line`

Extrai texto de `payload.content` (string simples) para tipos `user` e `assistant`.

**Formato IDE (real, amostrado 21/jul/2026):**
```json
{"id": "ffe51862-...", "timestamp": "2026-03-13T11:27:47.041Z", "payload": {"type": "user", "content": "é possível migrar todas as sessões anteriores?"}}
{"id": "abc12345-...", "timestamp": "2026-03-13T11:28:02.041Z", "payload": {"type": "assistant", "content": "Sim, as sessões IDE ficam em..."}}
{"id": "def67890-...", "timestamp": "2026-03-13T11:28:05.041Z", "payload": {"type": "tool_call", "content": "", "toolName": "execute_bash"}}
```

**15 payload.type values observados:**
- `user`, `assistant` → colher (texto conversacional)
- `tool_call`, `tool_result`, `turn_start`, `turn_end`, `steering_inclusion`, `session_start`, `session_event`, `session_metadata`, `usage_summary`, `pending_interaction`, `interaction_resolved`, `sub_agent_start`, `sub_agent_complete` → ignorar

**Detecção:** `"payload" in obj and isinstance(obj.get("payload"), dict)` — key única, não existe em Claude/CLI/OpenClaw.

### 2.2 Novo método: `find_ide_sessions`

```python
def find_ide_sessions(self, sessions_root: Path, count: int = 50) -> List[Path]:
    """Glob ~/.kiro/sessions/{workspace}/{session}/messages.jsonl"""
```

- Glob: `*/*/messages.jsonl`
- Exclui diretório `cli/` (formato diferente)
- Ordena por mtime (mais recentes primeiro)

### 2.3 Integração no harvester

O `_resolve_sessions()` ganha lógica adicional:
- Se `project_path` aponta para um diretório que contém subdirs com `messages.jsonl` → auto-detect como layout IDE
- Retrocompatível: se for flat com `*.jsonl` → comportamento atual (CLI/Claude)

---

## 3. Impacto

| Aspecto | Antes | Depois |
|---------|-------|--------|
| Sessões cobertas | CLI only (~667) | CLI + IDE (~742) |
| Meses cobertos | maio–jul 2026 | **março**–jul 2026 |
| Decisões perdidas | ~75 sessões nunca colhidas | Recuperáveis via harvest |
| Risco de regressão | — | Baixo (extensão, não refactor) |

---

## 4. Implementação

### Arquivos tocados

| Arquivo | Mudança |
|---------|---------|
| `src/.../harvest/parser.py` | +`_parse_kiro_ide_line`, +detecção, +`find_ide_sessions` |
| `src/.../harvest/harvester.py` | `_resolve_sessions` auto-detect layout IDE |
| `tests/harvest/test_kiro_ide_parser.py` | Testes novos (10 casos) |

### Ordem de execução

1. Branch `feat/harvest-kiro-ide` a partir de `main`
2. Implementar parser + detecção
3. Implementar `find_ide_sessions`
4. Adaptar `_resolve_sessions` no harvester
5. Testes
6. PR (sem issue — extensão simples)

---

## 5. Testes

| # | Caso | Verifica |
|---|------|----------|
| 1 | `test_parse_ide_user_message` | user → ParsedMessage(role="user", text=...) |
| 2 | `test_parse_ide_assistant_message` | assistant → ParsedMessage(role="assistant") |
| 3 | `test_parse_ide_skips_tool_call` | tool_call → [] |
| 4 | `test_parse_ide_skips_empty_content` | content="" → [] |
| 5 | `test_parse_ide_skips_system_content` | >10k chars → [] |
| 6 | `test_parse_ide_preserves_metadata` | timestamp + id passados |
| 7 | `test_parse_ide_full_session` | mix de 15 types → só user/assistant extraídos |
| 8 | `test_find_ide_sessions_glob` | encontra messages.jsonl em layout correto |
| 9 | `test_find_ide_sessions_excludes_cli` | ignora cli/ |
| 10 | `test_auto_detect_ide_format` | primeira linha com "payload" → kiro_ide |
| 11 | `test_cli_format_unchanged` | regressão — parser CLI continua funcionando |

---

## 6. harvest-cron.sh — Colher CLI + IDE

O cron passa `project_path` apontando para `~/.kiro/sessions/cli`. Com a mudança, deve passar o **root** (`~/.kiro/sessions`) e o harvester resolve ambos os layouts:

```bash
# ANTES
"arguments":{"project_path":"/home/claudio/.kiro/sessions/cli", ...}

# DEPOIS
"arguments":{"project_path":"/home/claudio/.kiro/sessions", ...}
```

O harvester detecta automaticamente:
- Se encontra `*.jsonl` na raiz → formato CLI/Claude (comportamento atual)
- Se encontra `*/*/messages.jsonl` → formato IDE
- Combina ambos, ordena por mtime, aplica `count`

Isso é retrocompatível — se alguém ainda aponta para `cli/` explicitamente, funciona como antes.

---

## 7. Não-objetivos

- **NÃO** migra sessões (botão da UI já fez isso)
- **NÃO** colhe tool_call/tool_result (só texto conversacional)
- **NÃO** precisa de issue (extensão pontual do parser existente)
