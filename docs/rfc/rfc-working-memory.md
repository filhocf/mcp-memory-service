# RFC: Working Memory Layer (contexto quente auto-gerenciado)

**Data:** 2026-09-13
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `feat/working-memory` (a partir de `upstream/main`)
**Base:** `upstream/main` v11.11.0
**Versão:** 0.1 (draft)
**Inspiração:** Mnemosyne BEAM (working/episodic tiers) + `enhancement-roadmap-issue-14.md` (context injection, upstream)
**Reintegra:** issue #14 (automatic context injection) — eleva de "busca no startup" para "camada de runtime"
**Status:** DRAFT — amadurecer localmente antes de virar issue/RFC para o Henry

---

## 1. Problema

O memory-service é hoje um store consultável: o agente busca memórias sob demanda (`memory_search`) e cola no contexto. Não existe uma camada de "memória de trabalho" com ciclo de vida próprio — contexto quente que é mantido ativamente durante a sessão, envelhece e é promovido ao longo prazo.

### Evidências

- O nosso startup-hook faz `memory_search` na abertura e injeta o resultado uma vez (evento único, pull). Não há re-injeção contínua nem gestão de TTL.
- O roadmap upstream (`enhancement-roadmap-issue-14.md`) propõe "automatic context injection" mas como hook de startup — mesmo modelo pull, não uma camada.
- Mnemosyne BEAM separa working memory (hot, TTL, auto-inject) de episodic (long-term) — o que dá recall plano de 100K a 10M mensagens.
- Efeito prático da ausência: contexto de sessão longa perde memórias relevantes que não foram buscadas na abertura; o agente não tem "o que está quente agora".

### Causas

1. **Modelo pull, não push.** A memória só entra no contexto quando o agente busca. Não há injeção proativa do que é relevante ao momento.
2. **Sem tier de trabalho.** Toda memória é tratada igual; não há distinção entre "quente/recente/em uso" e "arquivada".
3. **Sem promoção working→episodic.** Não há mecanismo de uma memória de trabalho "provar valor" (por acesso/reforço) e migrar para o longo prazo.

### Risco / motivação estratégica

Além da perda de contexto em sessões longas, a ausência de uma camada explícita amarra a memória de trabalho ao harness (hoje o "contexto quente" é reconstruído pelo steering do Kiro). Uma working memory no serviço torna esse comportamento **portável entre harnesses**.

---

## 2. Objetivo

Introduzir uma **camada de working memory** opcional: armazenamento de contexto quente com TTL/evicção, injeção proativa do que é relevante ao momento, e promoção para o store de longo prazo por reforço.

**Não-objetivos:** substituir `memory_search`; alterar o schema de `memories`; forçar a camada (deve ser opt-in).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1).

### Funcional

**R1**: Existe um store de working memory separado do de longo prazo.

> EARS: WHEN a working memory item is written, THE system SHALL store it in a working tier distinct from `memories`, tagged with a session and a timestamp.

**R2**: A working memory expira por TTL.

> EARS: WHEN a working memory item exceeds its configured TTL, THE system SHALL evict it from the working tier.

**R3**: A camada injeta contexto relevante ao momento sob demanda.

> EARS: WHEN `get_context(task)` is invoked, THE system SHALL return the working items most relevant to the task within a token budget.

**R4**: Uma working memory reforçada é promovida ao longo prazo.

> EARS: WHEN a working memory item is accessed or reinforced beyond a threshold, THE system SHALL promote it into `memories` as a consolidated entry.

**R5**: A camada é opt-in e não afeta o install padrão.

> EARS: WHERE the working memory feature is disabled, THE system SHALL behave exactly as the current pull-based model.

### Não-Funcional

**R6**: A injeção respeita orçamento de tokens.

> EARS: WHILE assembling context, THE system SHALL never exceed the configured token budget, preferring higher-relevance items.

**R7**: A promoção é idempotente.

> EARS: WHEN the same item qualifies for promotion twice, THE system SHALL promote it once and reinforce the existing long-term entry.

---

## 4. Design

- Nova tabela `working_memory` (session_id, content, embedding, importance, ttl, created_at, access_count).
- `get_context(task, budget_tokens)`: recupera working items por relevância (vetor + recência) dentro do budget.
- Scheduler: job de evicção por TTL + job de promoção (access_count/importance acima do limiar → `store_memory` consolidado).
- Opt-in via `MCP_MEMORY_WORKING_ENABLED`.
- Reuso do belief/consolidation existente para a promoção.

---

## 5. Fora de Escopo

- Substituir retrieval semântico (`memory_search` permanece).
- Persona/identidade (RFC própria).
- Multi-agente/sync (RFC própria).

---

## 6. Critérios de Aceite

- [ ] Working items são escritos em tier separado com TTL e são evictados ao expirar.
- [ ] `get_context(task)` retorna working items relevantes dentro do budget de tokens.
- [ ] Item reforçado é promovido a `memories` (idempotente).
- [ ] Feature desabilitada = comportamento pull atual intacto.
