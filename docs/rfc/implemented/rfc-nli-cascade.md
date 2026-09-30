# RFC — NLI Cascade Backend (LLM-based contradiction detection)

**Criado:** 2026-09-14 · **Autor:** Claudio Ferreira Filho (filhocf) · **Branch:** fork/main (fork-only, nunca vira PR) · **Base:** upstream/main (v11.11.x) · **Versão:** 1.0 · **Status:** Fase 1 IMPLEMENTADA (PR #1215, merged f5b1ff00) · Fase 2 PENDENTE (issue #1235)

> RFC retroativa: o backend NLI cascade já foi implementado e mergeado no upstream (#1215) sem RFC própria — esta fecha a lacuna documental e serve de spec para a Fase 2 (#1235). Segue o modelo canônico (RFC-harvest-provenance): prosa + EARS testáveis (DEVELOPMENT-STANDARDS §8.4.1).

---

## 1. Problema

### 1.1 Contexto — origem
- **Codeberg #116 → GitHub #1098** (06/jul/2026, filhocf): "Optional LLM fallback for auto_capture when heuristic confidence is low". A extração `auto_capture` depende só de regex YAML; texto que não casa é perdido silenciosamente. O rewriter LLM existe mas só roda com `use_llm=true` explícito — sem meio-termo.
  - **Impacto medido:** regex-only ~47% de captura; com LLM ~80%+; **gap ~33%** de conhecimento acionável perdido no default (289 sessões processadas confirmaram).
- A detecção de contradição (NLI) sofria do mesmo mal: o `NLIClassifier` só tinha backend `heuristic` (regex de versão/negação/antônimo), que não pega contradição semântica em linguagem natural.

### 1.2 Evidências reais
- `NLIClassifier` v11.11: só `heuristic`; backends `cascade`/`llm` inexistentes (retornavam neutral).
- `detect_contradictions_nli` classifica **até 20 pares candidatos sequencialmente** no caminho de store (awaited), timeout por tentativa de provider.

### 1.3 Causas
- Backend LLM ausente no NLI (só heurística de padrões).
- Rewriter LLM (`HarvestRewriter`) subutilizado — exigia flag explícita.

### 1.4 Risco
- Contradições semânticas passam despercebidas → beliefs incoerentes, quarentena não dispara.

---

## 2. Objetivo

Dar ao `NLIClassifier` um backend LLM (`cascade`) que reusa a cadeia de providers do harvest (`HARVEST_LLM_PROVIDERS`), degradando graciosamente para a heurística em qualquer falha, sem segunda superfície de config e sem mudar o default.

### 2.1 Não-objetivos
- Substituir a heurística (continua default e fallback).
- Novo config de providers (reusa o do harvest).
- Mudar decisões de quarentena (Fase 2 preserva label+confidence da heurística no fallback).
- Batching (mantém par-a-par).

---

## 3. Requisitos (prosa + EARS)

### Fase 1 — Backend cascade (IMPLEMENTADO, #1215)
- **R1** — THE NLIClassifier SHALL expor backend via `MCP_NLI_BACKEND` (`heuristic` default, `cascade`/`llm` opt-in).
- **R2** — WHEN backend resolve para `cascade`/`llm`, THE classifier SHALL classificar via `HarvestRewriter._call_llm`, reusando `HARVEST_LLM_PROVIDERS`.
- **R3** — THE classifier SHALL atribuir confidence 0.9 a labels definidos e 0.3 a neutral.
- **R4** — IF resposta vazia, label desconhecido, ou exceção, THEN THE classifier SHALL degradar para `_heuristic_classify`.
- **R5** — THE classifier SHALL truncar premise e hypothesis a 500 chars antes do prompt.
- **R6** — THE timeout SHALL ser configurável via `MCP_NLI_LLM_TIMEOUT` (default 30s), aplicado POR tentativa de provider.
- **R7** — WHEN `MCP_NLI_BACKEND` não setado, THE comportamento SHALL permanecer `heuristic`.
- **R8** — THE `_parse_nli_label` SHALL rejeitar hedging (>1 label → None), ancorar no 1º token, tratar prefixo `Classification:`.
- **R9** — THE call-sites `detect_contradictions_nli` e `check_beliefs_on_store` SHALL construir `NLIClassifier(backend="auto")` (switch chega ao pipeline, não hardcoded).

### Fase 2 — Reuse + observabilidade (PENDENTE, #1235)
Prosa: hoje `_llm_classify` cria um `HarvestRewriter()` novo por par e chama `_call_llm` sem checar `is_configured`; sem provider, ainda entra no fallback legado. Degradação invisível (log só debug, exceção não sanitizada; resposta vazia não loga). Corrigir sem mudar quarentena.

- **R10** — THE NLIClassifier SHALL resolver a config de provider UMA vez por run (não por par), reusando um rewriter.
- **R11** — IF nenhum provider configurado (`not rewriter.is_configured`), THEN THE classifier SHALL pular a chamada LLM e usar heurística direto, sem emitir request.
- **R12** — WHEN degradação ocorre (exceção OU resposta vazia/não-parseável), THE classifier SHALL emitir UM warning bounded (uma vez por run).
- **R13** — THE warning SHALL sanitizar o erro externo (sem newlines/control chars) e NÃO SHALL logar conteúdo de memória.
- **R14** — WHEN cai no fallback, THE classifier SHALL preservar label e confidence exatos da heurística.
- **R15** (não-funcional) — testes de parser e integração de quarentena SHALL permanecer verdes.

---

## 4. Design

### 4.1 Implementado (Fase 1)
- `NLIClassifier(backend="auto")` resolve `MCP_NLI_BACKEND`.
- `_llm_classify`: prompt one-word → `HarvestRewriter._call_llm` → `_parse_nli_label` → fallback total no `except`.
- `_classify_band` extraído (gate de complexidade, review #1215).
- Pipeline 4 estágios: entity gate → embedding pre-filter (0.4-0.75) → NLI → registro de conflito.
- Envs: `MCP_NLI_ENABLED`, `MCP_NLI_ON_STORE`, `MCP_NLI_CONFIDENCE_THRESHOLD` (0.4), `MCP_NLI_BACKEND`, `MCP_NLI_LLM_TIMEOUT` (30s).

### 4.2 Proposto (Fase 2 / guia do #1235)
- Rewriter lazy memoizado (`self._rewriter`, `self._llm_available: bool|None`) — config 1x. Curto-circuito O(1): se `is_configured()` falso, degrada o run para heurística.
- Flag `self._warned_degraded` (espelha `_warned_unimplemented`) → warning único por run.
- Helper `_warn_once(reason)`: sanitização + guarda, cobre exceção E resposta vazia.
- Fallback retorna `_heuristic_classify(...)` intacto (R14).
- Ciclo de vida: classifier 1x por run em `detect_contradictions_nli`, passado a `_classify_band` (sequencial) → estado na instância é seguro; documentar contrato (race benigna se paralelizarem).

---

## 5. Fora de Escopo
- Batching (1 chamada p/ N pares).
- Cross-agent NLI (perspective_conflict) → RFC agent-id #1100 Fase 3.
- Substituir heurística / mudar thresholds de quarentena.

---

## 6. Critérios de Aceite (Fase 2 / #1235)
- Sem provider usável: nenhum request, heurística preservada.
- Múltiplos pares num run: config resolvida uma vez.
- Exceção com newlines/control chars: sanitizada, warning bounded.
- Resposta vazia/não-parseável: warning bounded + fallback.
- Parser + integração de quarentena verdes.
- red-on-main: testes novos falham sem a mudança.
- E2E real (regra Claudio): groq→ollama→deepseek + fallback.

---

## 7. Estado / Rastreabilidade

| Item | Estado |
|------|--------|
| GitHub #1098 (ex-CB #116) — origem LLM fallback | OPEN (post-v11) |
| PR #1215 — backend cascade (Fase 1) | MERGED `f5b1ff00` (12/set) |
| Issue #1235 — reuse + observabilidade (Fase 2) | OPEN (memory-reasoning) |
| Código | `reasoning/nli.py` (`_llm_classify`, `_classify_band`, `_parse_nli_label`); `harvest/rewriter.py` (`is_configured`, `_call_llm`) |

### 8. Referências (bidirecional)
- Índices CdIA: `PILHA-PRs-runbook.md`, `REFERENCE-MEMORY-PIPELINE.md`.
- Issues: GH #1098 / CB #116 (origem), PR #1215 (Fase 1), GH #1235 (Fase 2).
- Memórias-âncora: `ef67ee4e` (2º round review #1215), `2e349e6a` (#1215 aberto), `3cd0b8f9` (decisão reorg fork), análise arch #1235 (sessão 14/set).
- Prior art: RFC-harvest-provenance (molde), #1098 (mesma filosofia heurística→LLM quando fraco).
