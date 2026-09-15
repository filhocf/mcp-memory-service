# RFC: Harvest Provenance & Safe Re-harvest

**Data:** 2026-09-13
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `feat/harvest-provenance` (empilhada sobre `pr/scheduled-harvest`)
**Base:** `upstream/main` v11.11.0 (via `pr/scheduled-harvest`)
**Versão:** 0.5 (draft — + Fase 4 Session Digest temático)
**Estende:** `docs/rfc/pipeline-harvest-quality.md`, `docs/rfc/harvest-kiro-ide-sessions.md`
**Reintegra:** questão #4 do Codeberg #104 (Session transcript mining), nunca resolvida
**Status:** DRAFT — amadurecer localmente antes de virar issue/RFC para o Henry

---

## 1. Problema

O acervo de colheitas de sessão mistura dois regimes de qualidade sem qualquer marca que os distinga, e o mecanismo de idempotência impede a correção.

### Evidências (13/set/2026, banco de produção sirdata, 20.857 memórias)

- **~3.440 memórias `session-harvest`** + **3.475 `mining`** (session-miner standalone jul/2026) = duas origens distintas, ambas sem proveniência de método.
- Distribuição de tamanho de `session-harvest`: `<80 chars` 108 · `80–200` 2.152 (63%) · `200–500` 1.186 · **`>500` apenas 5 (0,15%)**.
- Amostras curtas são cópia crua da `source_line` (texto conversacional fragmentado) — assinatura de extração heurística/regex sem reescrita LLM.
- Prefixo `[MINED]` proposto no CB #104 (questão #4): **zero** ocorrências. Nunca foi implementado.

### Causas (confirmadas no código)

1. **Sem proveniência.** `harvester.py` grava `metadata={"confidence", "source": "harvest"}` idêntico para todo método. Nenhum campo registra LLM vs heurística, provider/modelo ou versão do pipeline.
2. **Regimes misturados.** Quando `rewrite` falha, o item é descartado (`if result:`); quando `rewriter is None`, cai no classifier heurístico que armazena cru. Sem marca, indistinguíveis.
3. **Bug de idempotência.** `consolidation/scheduler.py::_run_scheduled_harvest` marca a sessão como colhida por `r.session_id` existir, ignorando `r.stored`. Sessão com `stored=0` (LLM falho) nunca é reprocessada. Comprovado: zero `session-harvest` desde 12/set (job rodou com LLM quebrado).

### Risco

Se a sessão-fonte for deletada (plano de liberar OneDrive), uma colheita heurística pobre vira a única memória daquele trabalho — perda irreversível. É preciso poder recolher via LLM e verificar cobertura antes de deletar.

---

## 2. Objetivo

Tornar a colheita **auditável, reprocessável e segura para deleção da fonte**, via proveniência no tagging, recolheita seletiva e verificação pré-deleção.

**Não-objetivos:** reescrever extração (coberto por `pipeline-harvest-quality.md`); alterar formatos de sessão (coberto por `harvest-kiro-ide-sessions.md`).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1): prosa primeiro, EARS depois; **uma ação por frase**; sujeito = componente (`THE harvester`, `THE scheduler`); SHALL=obrigatório. Cada requisito é testável (origina teste G3 RED).

### Funcional — Fase 1 (Proveniência)

**R1**: Toda memória colhida registra o método de extração como tag.

> EARS: WHEN a harvest candidate is stored, THE harvester SHALL tag it `harvest:method:llm` if it was LLM-rewritten, otherwise `harvest:method:heuristic`.

**R2**: A memória registra o método também em metadata (para consulta programática).

> EARS: WHEN a harvest candidate is stored, THE harvester SHALL set `metadata.harvest_method` to `"llm"` or `"heuristic"`.

**R3**: Colheitas via LLM registram o provider e o modelo usados.

> EARS: WHEN a candidate is rewritten successfully by an LLM provider, THE harvester SHALL set `metadata.harvest_model` to `"<provider>/<model>"`.

**R4**: A versão do pipeline é registrada para permitir migração futura.

> EARS: WHEN a harvest candidate is stored, THE harvester SHALL set `metadata.harvest_pipeline_version` to the current integer version.

**R5**: A sessão de origem é rastreável (para verificação pré-deleção).

> EARS: WHEN a harvest candidate is stored, THE harvester SHALL set `metadata.harvest_session_id` to the source session id.

**R6**: O acervo legado sem proveniência é identificável.

> EARS: WHERE an existing `session-harvest` memory has no `harvest_method`, THE backfill SHALL tag it `harvest:method:heuristic-legacy`.

### Funcional — Fase 2 (Recolheita seletiva + fix do tracker)

**R7**: O tracker só marca uma sessão como colhida quando algo foi armazenado.

> EARS: WHEN a scheduled harvest processes a session, THE scheduler SHALL add it to the harvest-tracker only if `stored > 0`.

**R8**: É possível forçar a recolheita de sessões já marcadas.

> EARS: WHEN harvest is invoked with `force_reharvest=true`, THE harvester SHALL re-process the target sessions ignoring the harvest-tracker.

**R9**: A recolheita via LLM evolui a memória existente em vez de duplicar.

> EARS: WHEN a re-harvested insight is similar (>= 0.85) to an existing memory, THE harvester SHALL evolve it via versioned update instead of storing a duplicate.

**R10**: É possível selecionar recolheita por método de origem.

> EARS: WHEN `reharvest_by_method(method="heuristic")` is invoked, THE harvester SHALL target only memories tagged `harvest:method:heuristic*`.

### Funcional — Fase 3 (Verificação pré-deleção)

**R11**: É possível medir a cobertura de uma sessão na memória antes de deletá-la.

> EARS: WHEN `verify_session_coverage(session_id)` is invoked, THE system SHALL return `{coverage, missing_insights, low_quality_matches}` comparing an in-memory LLM re-harvest against stored memories.

**R12**: A deleção de sessão é sinalizada como insegura abaixo do limiar de cobertura.

> EARS: IF `coverage < threshold` (default 0.9), THEN THE system SHALL flag the session as not-safe-to-delete.

> **Status (15/set):** R11/R12 submetidos ao upstream no PR #1252 (`verify_session_coverage`, método + 4 unit + E2E real). Split do #1243. Aguarda review do Henry.

### Funcional — Fase 4 (Session Digest temático)

Motivação: o harvest de insights pontuais captura frases-gatilho ("decidi X", "o bug era Y") mas **perde o arco de trabalho** — análises de design extensas e o "o que já foi feito" de um tema ao longo de várias sessões. Diagnóstico real (issue #1100): 20 sessões de trabalho de RFC colhidas produziram apenas fragmentos, porque o conteúdo de design estava em mensagens longas e em `ToolResults` que o extractor de frase-curta descarta. O digest resolve isso: um resumo por **tema** (não por sessão — uma sessão toca vários temas), preservando o contexto de trabalho sem guardar o transcript bruto.

O digest **coexiste** com os insights pontuais (não substitui): insights refinam o processo (mistake-notes, convenções acionáveis); o digest dá o panorama do que foi feito. Escopo: esta fase adiciona a **capacidade** de gerar digests; a política de *quando arquivar sessões* é do usuário/harness, fora do MCP.

**R17**: O harvest pode agrupar as mensagens de uma sessão por tema antes de resumir.

> EARS: WHEN a session is harvested in digest mode, THE harvester SHALL group its messages into topic segments (e.g. by issue/feature/subject) rather than treating the session as a single unit.

**R18**: Cada tema detectado gera um digest de trabalho standalone.

> EARS: WHEN a topic segment is identified, THE harvester SHALL produce one `session-digest` memory summarizing what was worked on, decisions made, and open items for that topic.

**R19**: O digest inclui o contexto de ferramentas (não só mensagens de conversa).

> EARS: WHILE building a digest, THE harvester SHALL consider `ToolResults` content as context (unlike pointwise insight extraction, which ignores it).

**R20**: O digest é rastreável à sessão e ao tema de origem.

> EARS: WHEN a `session-digest` is stored, THE harvester SHALL tag it with the detected topic and record `harvest_session_id` in metadata.

**R21**: O digest não substitui os insights pontuais.

> EARS: WHEN digest mode runs on a session, THE harvester SHALL still emit pointwise insights (they are complementary, not mutually exclusive).

### Não-Funcional

**R13**: A proveniência é aditiva e não altera o contrato existente.

> EARS: THE provenance tagging SHALL only add new tags and metadata keys (never modify existing ones).

**R14**: O backfill é idempotente.

> EARS: WHEN the backfill runs again, THE backfill SHALL skip memories already tagged `heuristic-legacy`.

**R15**: O backfill suporta simulação antes de aplicar.

> EARS: WHERE `dry_run=true`, THE backfill SHALL report the changes without writing them.

**R16**: A recolheita em massa respeita pacing.

> EARS: WHILE re-harvesting a large session set, THE harvester SHALL honor the backoff pacing (#1234).

---

## 4. Design

### Metadata de proveniência (bloco novo em `store_memory`)
```json
{
  "source": "harvest",
  "confidence": 0.85,
  "harvest_method": "llm",                     // "llm" | "heuristic" | "heuristic-legacy"
  "harvest_model": "deepseek/deepseek-chat",   // provider/model; null p/ heuristic
  "harvest_pipeline_version": 3,
  "harvest_session_id": "<uuid>",
  "harvested_at": "2026-09-13T...Z"
}
```

### Arquivos
- `harvest/rewriter.py` — `RewriteResult` passa a carregar `provider`/`model` do call bem-sucedido.
- `harvest/harvester.py` — propaga método+modelo+sessão ao `store_memory` (R1-R4).
- `harvest/models.py` — campos no `RewriteResult`.
- `consolidation/scheduler.py` — fix do tracker `stored>0` (R6) + `force_reharvest` (R7). **Este arquivo é introduzido por `pr/scheduled-harvest` → por isso a feat empilha sobre ela.**
- Backfill: script idempotente (R5, R13).
- `reharvest_by_method` / `verify_session_coverage`: tools novas (R9, R10).

---

## 5. Fora de Escopo

- Reescrita do extractor/patterns (já em `pipeline-harvest-quality.md`).
- Novos formatos de sessão (já em `harvest-kiro-ide-sessions.md`).
- Deleção automática de sessões (a RFC só torna a deleção *segura*; quem deleta é o usuário/rotina externa).
- **Política de arquivamento de transcripts** (quando/para onde mover os JSONL) — é específica do harness/usuário (formatos e locais variam por agente), fora do MCP. A RFC entrega a *capacidade* de digest; o *gatilho de arquivamento* é do usuário.

---

## 6. Critérios de Aceite

- [ ] Novas colheitas LLM saem com `harvest:method:llm` + `harvest_model` preenchido.
- [ ] Novas colheitas heurísticas saem com `harvest:method:heuristic`.
- [ ] Backfill marca acervo legado como `heuristic-legacy` (dry-run first, idempotente).
- [ ] Tracker só marca sessão com `stored>0` (teste red-on-main: sessão stored=0 não entra no tracker).
- [ ] `force_reharvest=true` reprocessa sessão já trackeada.
- [ ] Recolheita evolui memória similar (>=0.85) em vez de duplicar.
- [ ] `verify_session_coverage` retorna cobertura + insights faltantes.
- [ ] Default path inalterado (colheita sem as flags novas comporta-se como hoje).
- [ ] Digest mode agrupa uma sessão multi-tema em N digests (um por tema), não 1 por sessão.
- [ ] Digest considera ToolResults como contexto; insights pontuais continuam emitidos (coexistência).
- [ ] `session-digest` tem tag do tema + `harvest_session_id`.
- [ ] Digest recupera o arco de trabalho do #1100 (validação real: as 20 sessões viram digests navegáveis por tema).
- [ ] Testes: método llm, método heuristic, backfill idempotente, tracker stored>0, force_reharvest, evolve-not-duplicate, coverage, digest-por-tema, digest-coexiste-com-insights.

---

## 7. Faseamento e transporte

| Fase | Escopo | PR upstream? |
|------|--------|--------------|
| 1 | Proveniência + backfill legacy | Sim (útil a todos) |
| 2 | Fix tracker (correctness) + recolheita seletiva | Sim — fix do tracker é o candidato mais forte (Henry gosta de correctness) |
| 3 | Verificação pré-deleção | Avaliar (pode ser específico demais) |

**Ordem na pilha (1-PR-por-vez):** #1234 → `pr/scheduled-harvest` → `feat/harvest-provenance`. Rebase a cada merge.
**GATE:** G0 arch (call-sites reais) → G3 testes RED → G4 GREEN → G5 review subagent + integração end-to-end com Ollama local + validar proveniência nos 3 providers.

---

## 8. Referências e Rastreabilidade

> Índices de rastreamento vivem no CdIA (`~/git/conhecimentos-de-ia/ferramentas/mcp/memory-service/`) — consultar ANTES de caçar issue por issue no GH/CB. Regra: ao mexer em issues/PRs deste tema, atualizar o índice correspondente.

**Índices de rastreamento (CdIA):**
- `PILHA-PRs-runbook.md` — estado vivo da pilha de PRs (branches, ordem, o que mergeou).
- `REFERENCE-MEMORY-PIPELINE.md` — mapa do pipeline + problemas diagnosticados + issues por área.
- `RECONCILIACAO-v11.10.0.md` — reconciliação fork↔upstream (o que já está no upstream vs fork-only).
- `comparativo-mcp-memory-service.md` — comparativo geral.

**RFCs relacionados (fork, `docs/rfc/`):**
- `pipeline-harvest-quality.md` — pipeline v2 (base que esta RFC estende).
- `harvest-kiro-ide-sessions.md` — formatos de sessão / parser.

**Issues/PRs (GH doobidoo = origem; CB = congelado, histórico):**
- CB #104 (closed) — RFC Session transcript mining; **questão #4 (proveniência: `[MINED]` prefix + quality score inicial + promoção por acesso) reintegrada aqui, nunca resolvida.**
- GH #1098 / CB #116 (open) — LLM fallback quando heurística tem baixa confiança (alinhar com R7-R10).
- GH #1102 / CB #174 (open) — scorer openai-compatible não substitui classifier local (qualidade).
- GH #1111 → PR #1234 (aberto) — harvest backoff/pacing (R16 reusa).
- CB #67 (closed) — backlog post-V11 (contexto de priorização do Henry).

**Memórias-âncora (buscar por hash):**
- `caa1a179` — investigação formatos de sessão + estado real do harvest (12/set).
- `98f6ffcd` — DeepSeek renovado; `4d7b7db3` — Groq + modelo descontinuado (13/set).
- `c6c0aee6` — topologia da pilha empilhada; `08a23d7a` — ajuste do fluxo RFC/EARS/fork.
- `8ed84762` — reintegração da busca histórica de issues/RFCs.
