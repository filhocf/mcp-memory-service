# RFC-MM-02: Fact Extraction (Batch, Incremental)

**Data:** 2026-07-20 · **Reconciliada:** 2026-10-05 (ADR-0003 + evidência do código da trilogia)
**Status:** Draft (implementado na branch `validacao/prototipo-trilogia-2e1978d5`, pendente de reconciliação de migration para PR)
**Autor:** Claudio / Zero · **Arco:** learning-loop (L2 destilação)

> Reconciliação 05/out: a spec original (jul) enquadrava isto como "RAG 3.0 / tripletos de chunks
> de documentos ingeridos". O **ADR-0003** (aprendizado = uso real, não schema) e a **evidência do
> código** (`extraction/facts.py` lê `FROM memories`, não de uma tabela de chunks de docs) deslocam
> o enquadramento: a fonte dos fatos é **toda memória** — primariamente o que o agente PRODUZ no uso
> real (observações, decisões, checkpoints via `memory_store`), e secundariamente docs ingeridos.
> Mesmo pipeline, fonte unificada. Supersede o antigo `rfc-fact-extraction` (geração anterior).

## 1. Problema (do ponto de vista do cliente/agente)

Minhas memórias são episódicas e cruas: 23k fatos soltos, edges genéricas (`has_entity`) sem
semântica relacional. Quando eu pergunto "qual banco o RER usa?", recebo um parágrafo inteiro de
volta, não o fato "RER → usa → PostgreSQL". E o conhecimento que eu destilo de uma sessão
(decisões, descobertas) fica preso no texto corrido da memória — não vira estrutura navegável.

O que me atende: **destilar fatos atômicos (sujeito→predicado→objeto) do que eu já produzo**, com
confiança e proveniência, armazenados como edges tipadas no grafo — para navegação multi-hop
("o que depende de PostGIS?") em vez de recuperar texto e reler.

## 2. Reconciliação com o ADR-0003 (a mudança de enquadramento)

| Aspecto | Spec original (jul) | Reconciliado (ADR-0003 + código) |
|---------|--------------------|-----------------------------------|
| Fonte dos fatos | chunks de docs ingeridos (RAG 3.0) | **toda a tabela `memories`** — uso real (memory_store) + docs. É o que o código faz. |
| Premissa de aprendizado | implícito: enriquecer docs | explícito: **aprender do uso real** (ADR-0003); docs são só mais uma fonte na mesma tabela |
| Papel no arco | feature de RAG isolada | **L2 destilação** do learning-loop (episódico→semântico) |

Nada muda no código (ele já lê `FROM memories`). Muda a narrativa: isto NÃO é "melhorar busca em
PDFs", é **destilar conhecimento do que o agente vive**, que é o L2 do ciclo de aprendizado.

## 3. Princípio

**Batch > unitário** (20 chunks/call LLM = 20× menos overhead). **Incremental > full-scan**
(só memórias com `facts_extracted_at IS NULL`; nunca reprocessa). **Tripletos > texto** (fatos
atômicos S→P→O são navegáveis; texto cru não).

## 4. Solução (o que o código da trilogia faz)

- Flag incremental: coluna `facts_extracted_at` em `memories` (NULL = pendente).
- `get_pending_chunks`: `SELECT content_hash, content FROM memories WHERE facts_extracted_at IS NULL LIMIT N`.
- `extract_facts_batch`: 20 memórias/call ao LLM (cascade DeepSeek→Groq→Ollama), prompt pede JSON
  de tripletos `{s, p, o, confidence}`, "only explicitly stated, do not infer".
- `store_facts`: INSERT/UPDATE em `memory_graph` com `relationship_type` = predicado normalizado,
  metadata = confidence + hash do chunk fonte (proveniência). Dedup por (source, target, rel_type):
  confidence maior vence.
- `mark_processed`: UPDATE `facts_extracted_at` após o batch (idempotência).
- Scheduler: job periódico processa N por rodada; backlog drena ao longo de dias.

## 5. Requisitos (EARS)

- **M2.1** — WHEN existem memórias com `facts_extracted_at IS NULL`, THE job SHALL processá-las em
  lotes (default 20/call LLM), extraindo tripletos S→P→O com confiança.
- **M2.2** — THE extrator SHALL extrair apenas fatos EXPLÍCITOS no texto (não inferir), e omitir
  chunks sem fatos extraíveis.
- **M2.3** — WHEN um tripleto é extraído, THE serviço SHALL armazená-lo como edge tipada em
  `memory_graph` (relationship_type = predicado), com metadata contendo confidence e o hash do
  chunk fonte (proveniência).
- **M2.4** — WHEN um tripleto (source, target, relationship_type) já existe, THE serviço SHALL
  atualizar se a nova confiança for maior, senão pular (dedup).
- **M2.5** — WHEN um lote é processado, THE serviço SHALL marcar `facts_extracted_at` nas memórias
  do lote, de modo que NUNCA sejam reprocessadas.
- **M2.6** — IF o provider LLM estiver indisponível, THEN THE job SHALL pular o lote (retry na
  próxima rodada), sem marcar como processado e sem derrubar o scheduler.
- **M2.7** — THE fonte SHALL ser a tabela `memories` inteira (uso real + docs), não um store
  separado de documentos (ADR-0003).

## 6. Acceptance Criteria

- [ ] Precision >80% em corpus PT-BR (100 chunks avaliados manualmente).
- [ ] `memory_explore` mostra fatos atômicos por entidade ("RER → uses → PostgreSQL").
- [ ] Zero reprocessamento (memória processada nunca reenvia ao LLM).
- [ ] Dedup: 0 tripletos duplicados no grafo.
- [ ] Incremental: memória nova gravada hoje → fatos extraídos na próxima rodada.
- [ ] Graceful degradation: LLM offline → skip lote, retry depois.

## 7. Economia

20 chunks/call = ~20× menos calls/tempo/custo que 1-por-call (850 vs 17.000 calls para 17k chunks;
~14min vs ~5h; ~$0.50 vs ~$5-10 no DeepSeek).

## 8. Estado de implementação (branch trilogia) — CORROBORADO via git grep 05/out

| Peça | Arquivo (branch validacao) | Estado |
|------|----------------------------|--------|
| Flag incremental | `storage/migrations/014_add_facts_extracted.sql` | ✅ (⚠️ renumerar) |
| Pipeline batch (pending/extract/store/mark) | `extraction/facts.py` (370 linhas) | ✅ lógica |
| Handler/tool | `server/handlers/facts.py` | ✅ lógica |
| Testes | `tests/test_fact_extraction.py` (494 linhas) | ✅ unidade |
| **Job no scheduler (M2.1)** | — | ❌ **NÃO WIRED** — `extract_facts_batch`/`get_pending_chunks` só aparecem em facts.py+testes; nenhum job periódico chama o pipeline |
| **tool memory_facts no registry/routing** | — | ❌ **NÃO EXPOSTA** |

**Achado (corroborado):** igual à MM-03 — núcleo + testes de unidade prontos, mas **DESPLUGADO**:
nenhum job agendado dispara a extração, tool não exposta. Testes passam chamando o pipeline direto;
em produção nada roda. Para VIVER falta o WIRING (ver §9).

## 9. Pendências para virar PR (ordem corrigida pós-corroboração)

1. **WIRING (o que falta de verdade):** (a) job no ConsolidationScheduler que chama o pipeline
   de extração periodicamente (M2.1) — espelhar o padrão do harvest/quality-recalc job (opt-in via
   env); (b) expor tool `memory_facts` no registry+routing. Hoje 0 callers de produção.
2. **Colisão de migration:** `014_add_facts_extracted` COLIDE com `014_add_usage_events` no main.
   Renumerar para o próximo livre (migration_registry MAX = 14 → 015+). Lição 6ae9216.
3. **EARS → testes:** mapear M2.1-M2.7; ADICIONAR teste de integração do job (hoje só unidade).
4. Alinhar changelog + mover `planned/ → implemented/` quando o PR entrar.

## 10. Dependências

- LLM provider (fork cascade OK). memory_graph (✅ existe). Para PR upstream: #116 (NLI/LLM cascade).

## 11. Relação com o arco

É o **L2 (destilação)** do learning-loop — transforma o episódico (o que vivo) em semântico (fatos
navegáveis). Alimenta a injeção (L3): o que é injetado passa a poder ser fato destilado, não só
chunk de texto. Par da MM-03 (gaps = o que falta) e da telemetria (uso = o que ajuda).
