# RFC: agent_id em todas as memórias + resolução de conflito cross-agent

**Data:** 2026-09-13
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `feat/agent-id` (a partir de `upstream/main`, NÃO empilhada na pilha de harvest)
**Base:** `upstream/main` v11.11.0 (22c3dde3)
**Versão:** 0.1 (draft)
**Issue:** GitHub #1100 (origem Codeberg #118) — Henry confirmou publicamente "@filhocf is implementing it" (Fase 1)
**Estende:** `docs/rfc/rfc-self-service-memory-intelligence.md` (v1.0) — que já ASSUME `agent_id` por observação (§Observation Store: "cada observação tem session_id, agent_id, ...") e constrói o Bootstrap Profile **per-agent** (§4, URI `memory://agent/{agent_id}/bootstrap`) em cima disso, mas NÃO especifica como o `agent_id` chega à memória. Esta RFC é o **pré-requisito de plumbing** que a self-service dava como dado.
**Reintegra:** o sintoma `conflict:unresolved` observado entre memórias T'Pol/Hermes (base compartilhada) — é o caso que a Fase 3 resolve.
**Status:** DRAFT — amadurecer localmente; Fase 1 é o compromisso público em curso

---

## 0. Relação com a self-service RFC (prior art)

A `rfc-self-service-memory-intelligence.md` (Claudio/Spock/Kiro, mai-jul/2026) definiu a visão macro: Observation Store (append-only, cada observação com `session_id`+`agent_id`) → Belief Store governado → **Bootstrap Profile per-agent**. Ela **assume** `agent_id` existente em cada observação, mas o `memory_store` atual não o aceita nem persiste — a plumbing nunca foi implementada.

Esta RFC (#1100) **não concorre** com a self-service; ela **habilita** o `per-agent` dela:
- Fase 1 (agent_id no store) = torna real a premissa "cada observação tem agent_id".
- Fase 2 (filtro) = base para `memory://agent/{agent_id}/bootstrap`.
- Fase 3 (NLI cross-agent) = a resolução de contradição que a self-service pressupõe mas não detalha.

Escopo desta RFC = a plumbing mínima de identidade de autor. A camada de belief/bootstrap per-agent permanece na self-service RFC.

---

## 1. Problema

`agent_id` existe hoje apenas no contexto de `commit_session_legacy` (metadata de sessão). Memórias individuais criadas via `memory_store` **não têm identidade de autor**. Num deployment multi-agente (Zero/Kiro, T'Pol, Scotty/Hermes compartilhando um sqlite_vec), isso causa quarentenas incorretas.

### Evidências (código real, 13/set/2026)

- `models/memory.py`: o dataclass `Memory` tem `metadata: Dict[str, Any]` como bolsa extensível. Campos como `source_type`, `credibility`, `access_count`, `last_accessed_at` já são **properties sobre metadata** (L261, L271, L250, L255) — não colunas. `agent_id` segue exatamente esse padrão: aditivo, sem migração de schema.
- `services/memory_service.py::store_memory` (L373) é a camada que o handler chama; hoje não propaga autor.
- `reasoning/nli.py::detect_contradictions_nli` (L127) decide contradição/quarantine sem olhar autor — trata memórias de agentes diferentes como se fossem do mesmo.
- `storage/mixins/retrieve.py`: filtros WHERE seguem padrão `where_conditions.append(...)` (L302-308) — agent_id entra no mesmo molde.

### Cenário real (produção)

- Agente A grava: "session-miner é redundante — harvest o substitui".
- Agente B grava: "session-miner tem valor único para síntese narrativa".
- NLI marca contradição → quarantine. Mas ambos estão corretos nos seus contextos analíticos. O sistema não sabe que vêm de agentes diferentes com escopos diferentes.

### Causas

1. **Sem identidade de autor por memória.** `memory_store` não aceita nem persiste quem escreveu.
2. **NLI cego a autor.** Contradição entre perspectivas de agentes distintos é tratada como contradição real do mesmo autor.
3. **Sem filtro por autor.** `memory_search`/`memory_list` não filtram por agente.

### Risco

Quarentenas incorretas removem conhecimento válido de recall. Em base compartilhada (nosso caso: 3 agentes), o problema é ativo e observado.

---

## 2. Objetivo

Dar identidade de autor às memórias (opcional, backward-compatible) e ensinar o NLI a distinguir contradição real (mesmo agente) de conflito de perspectiva (agentes diferentes), incrementalmente.

**Não-objetivos:** camada externa de event-sourcing (proposta por terceiro na issue — Henry respondeu "pass"); alterar schema da tabela (agent_id vive em metadata); resolver sync multi-máquina (RFC delta-sync separada).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1): prosa primeiro, EARS depois; uma ação por frase; sujeito = componente; SHALL=obrigatório; cada requisito origina teste G3 RED.

### Funcional — Fase 1 (identidade de autor)

**R1**: `memory_store` aceita um `agent_id` opcional.

> EARS: WHEN a memory is stored with an `agent_id` argument, THE store handler SHALL persist it in the memory metadata.

**R2**: Na ausência do argumento, o autor é inferido do ambiente.

> EARS: WHERE `agent_id` is not provided, THE store handler SHALL fill it from the `MCP_AGENT_ID` environment variable when set.

**R3**: A ausência total de autor é preservada como desconhecida.

> EARS: WHERE neither `agent_id` argument nor `MCP_AGENT_ID` is present, THE stored memory SHALL have a null `agent_id` (unknown), unchanged from current behavior.

**R4**: `agent_id` é exposto como property do modelo (padrão dos demais campos de metadata).

> EARS: WHEN `Memory.agent_id` is read, THE model SHALL return `metadata.get("agent_id")`.

### Funcional — Fase 2 (filtro na busca)

**R5**: `memory_search` filtra por autor.

> EARS: WHEN `memory_search` is invoked with an `agent_id` filter, THE retrieval SHALL return only memories whose `agent_id` matches.

**R6**: `memory_list` filtra por autor.

> EARS: WHEN `memory_list` is invoked with an `agent_id` filter, THE listing SHALL return only memories whose `agent_id` matches.

### Funcional — Fase 3 (NLI cross-agent)

**R7**: Contradição do mesmo agente permanece contradição real.

> EARS: WHEN two contradicting memories share the same non-null `agent_id`, THE NLI SHALL treat it as a real contradiction and keep the current quarantine behavior.

**R8**: Contradição entre agentes distintos é conflito de perspectiva, não quarentena.

> EARS: WHEN two contradicting memories have distinct non-null `agent_id`, THE NLI SHALL classify it as a perspective conflict and SHALL NOT quarantine either memory.

**R9**: Autor desconhecido preserva o comportamento atual.

> EARS: WHERE either memory has a null `agent_id`, THE NLI SHALL fall back to the current author-agnostic behavior.

### Não-Funcional

**R10**: A mudança é backward-compatible (aditiva).

> EARS: THE agent_id feature SHALL only add an optional metadata key and optional parameters, never altering existing table schema or the meaning of existing fields.

**R11**: A Fase 3 não altera decisões de quarentena onde não há sinal de autor.

> EARS: WHEN evaluated against the existing NLI test suite (author-less memories), THE Phase 3 change SHALL keep all current quarantine decisions unchanged.

---

## 4. Design

### Fase 1 (mínima, cirúrgica)
- `models/memory.py`: property `agent_id` sobre metadata (espelha `source_type`/`credibility` — L261/L271). Zero mudança de schema.
- `server/handlers/memory.py`: `handle_store` aceita `arguments.get("agent_id")`; fallback `os.environ.get("MCP_AGENT_ID")`; injeta em `metadata["agent_id"]` antes de montar `Memory(...)`.
- `services/memory_service.py::store_memory`: propaga o param (assinatura opcional, default None).
- Schema do tool `store_memory` (server_impl.py / mcp_server.py): declarar `agent_id` opcional. **Isolar do bloco que `feat/harvest-provenance` toca em server_impl.py (seções distantes — sem conflito).**

### Fase 2
- `storage/mixins/retrieve.py`: `where_conditions.append("json_extract(metadata, '$.agent_id') = ?")` no molde dos filtros existentes (L302).
- Param `agent_id` em `memory_search`/`memory_list`.

### Fase 3
- `reasoning/nli.py::detect_contradictions_nli` (L127): antes de quarentenar, comparar `agent_id` dos dois lados. Mesmo autor → mantém; autores distintos → status `perspective_conflict` (novo, não quarantine); algum null → comportamento atual.

### Isolamento (análise de colisão 13/set)
- Conjunto de arquivos DISJUNTO das 4 branches abertas (pilha harvest). Único contato: `server_impl.py` (Fase 1 schema) — bloco distante do de harvest-provenance.
- Branch `feat/agent-id` sai de `upstream/main` (NÃO empilha na pilha harvest) → PR independente, não bloqueado pelo #1234.

---

## 5. Fora de Escopo

- Event-sourcing externo (Henry respondeu "pass" ao AllSource na issue).
- Migração de schema (agent_id em metadata, não coluna).
- Sync multi-máquina (RFC delta-sync).
- Backfill de autor em memórias legadas (null=unknown é aceitável; backfill é opcional futuro).

---

## 6. Critérios de Aceite

### Fase 1 (o compromisso público)
- [ ] `memory_store(agent_id="zero")` persiste em `metadata.agent_id`.
- [ ] Sem argumento + `MCP_AGENT_ID=zero` → agent_id preenchido do env.
- [ ] Sem argumento e sem env → `agent_id` null (comportamento atual intacto).
- [ ] `Memory.agent_id` retorna `metadata.get("agent_id")`.
- [ ] Schema do tool declara `agent_id` opcional; nenhum banco existente afetado.
- [ ] Teste RED-on-main por requisito (G3).

### Fase 2
- [ ] `memory_search(agent_id="zero")` retorna só memórias do zero.
- [ ] `memory_list(agent_id=...)` idem.

### Fase 3
- [ ] Mesmo agent_id contradizendo → quarantine (atual).
- [ ] Agentes distintos contradizendo → perspective_conflict, sem quarantine.
- [ ] Memória com agent_id null → comportamento atual; suíte NLI existente 100% verde.
