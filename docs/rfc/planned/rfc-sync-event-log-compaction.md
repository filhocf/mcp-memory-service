# RFC: Sync Event-Log Compaction — bound the delta-sync log

**Data:** 2026-10-29
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `fix/sync-event-log-compaction` (a partir de `upstream/main`)
**Base:** `upstream/main` (delta-sync já em `implemented/`)
**Versão:** 0.1 (draft)
**Classificação:** BUG do arco `delta-sync` (log cresce sem bound) — sem fila de feat
**Arco:** delta-sync
**Status:** DRAFT — amadurecer localmente antes de virar PR para o Henry

---

## 1. Problema

A tabela `sync_events` (event log do delta-sync, ADR-0007/0008/0010) é **append-only e nunca é podada**. Cada mutação de metadata de memória grava um evento `update_metadata` (`metadata.py:213`). Os recomputes periódicos locais (quality, utility, consolidation) reescrevem metadata de **todas** as memórias várias vezes ao dia, gerando dezenas de milhares de eventos idempotentes por dia que o log retém para sempre.

### Evidências (29/out/2026, banco de produção DNBSCDC289)

Banco inchou de ~500 MB (semana de 08/out) → ~700 MB (semana de 15/out) → **1,9 GB** (29/out). Forense por `dbstat`:

| Grupo (tabela + índices) | Tamanho | Linhas |
|---|---|---|
| **`sync_events` + 4 índices** | **~935 MB** (≈ metade do banco) | **1.364.093** |
| `memory_graph` + índices | ~396 MB | 740.898 |
| `memory_content_fts` | ~246 MB | — |
| `usage_events` + índice | ~107 MB | 42.427 |
| `memories` (dado real) | 132 MB | 31.629 |
| embeddings (vec chunks) | ~50 MB | — |

Dentro de `sync_events`:

- **1.326.865 de 1.364.093 eventos (97%) são `op='update_metadata'`** (vs 33.966 `create`, 3.262 `delete`).
- Média de **~53 `update_metadata` por `content_hash`** (top: 113); distribuídos por ~31.040 hashes.
- **~100-135 mil eventos/dia** (24-27/out), coincidindo com o salto para 1,9 GB.
- Payload típico: `{"updates": {"computed_quality": 1.0, "quality_score": 1.0}, ...}` — recompute reescrevendo o **mesmo valor**.

> Nota: atualiza o diagnóstico de `rfc-memory-hygiene` (medição 18/set, banco 505 MB, FTS como maior peso). O perfil **mudou**: em outubro, `sync_events` ultrapassou o FTS. O inchaço de outubro é o **event log**, não ruído de conteúdo (cujo `candidate_ratio` medido foi 3%).

### Causa

`update_metadata` registra no event log cada reescrita de metadata, mas o log nunca é compactado. Dois fatores somam:
1. **Volume:** recomputes idempotentes de estado derivado local (quality/utility) são sincronizáveis sem necessidade — reescrevem o mesmo valor.
2. **Retenção infinita:** não há mecanismo de compaction nem de poda, mesmo para eventos já propagados a todos os peers.

### Risco de não agir

Crescimento ~1,2 GB/mês sem teto. Efeitos colaterais já observados: WAL inflado (782 MB), `PRAGMA integrity_check` de startup estoura o timeout de init (warning todo restart + porta abre ~30 s atrasada), disco pressionado, backups/sync (`hot.db`) cada vez maiores.

---

## 2. Objetivo

Dar um **teto ao event log** por **compaction semântica segura**: colapsar a cadeia redundante de `update_metadata` por memória para o **estado LWW resolvido**, preservando a convergência do sync entre peers. Secundariamente, reduzir o volume na fonte (recompute local não precisa gerar evento sincronizável — ver §5 território adjacente).

**Não-objetivos:** quantização de embeddings (`rfc-embedding-quantization`); poda de ruído/secret/órfãos de conteúdo (`rfc-memory-hygiene`); alterar a semântica de resolução LWW ou de `recreate_of` (apenas preservá-la).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1).

### Funcional

**R1**: A compaction colapsa a cadeia de `update_metadata` de uma memória sem alterar o estado materializado.

> EARS: WHEN compaction runs over a `content_hash`, THE system SHALL replace that memory's `update_metadata` events with a single consolidated event whose resolved per-field LWW state is identical to the state produced by the full chain.

**R2**: A compaction só toca eventos causalmente estáveis (já propagados a todos os peers).

> EARS: WHERE an event's `seq` is greater than the minimum `last_seq_pushed` across all known peers, THE compaction SHALL NOT remove or rewrite it.

**R3**: A compaction preserva a fronteira de recriação (`recreate_of`).

> EARS: WHERE a `content_hash` has more than one incarnation (a `create` after a `delete`), THE compaction SHALL compact within each live incarnation only and SHALL NOT merge events across the recreation boundary.

**R4**: `create` e `delete` nunca são compactados.

> EARS: THE compaction SHALL only consolidate `update_metadata` events and SHALL leave `create` and `delete` events untouched.

**R5**: A compaction é um job agendado, idempotente e observável.

> EARS: WHEN the compaction job completes, THE system SHALL report events removed, bytes reclaimed, and SHALL leave a second immediate run with nothing to do.

**R6**: A compaction devolve espaço ao disco.

> EARS: WHEN a compaction batch removes events, THE system SHALL run `VACUUM` (or incremental) and report bytes reclaimed.

### Não-Funcional

**R7**: A compaction nunca regride o relógio nem o cursor.

> EARS: THE compaction SHALL preserve HLC monotonicity and SHALL NOT advance or rewind any sync/push cursor.

**R8**: A compaction falha fechada.

> EARS: IF a compaction batch cannot complete atomically, THE system SHALL roll back the whole batch and leave the log unchanged.

---

## 4. Design

### 4.1 Critério de poda segura (causal)

O `push_cursor.last_seq_pushed` por peer registra até onde o log já foi propagado. O **watermark seguro** é `MIN(last_seq_pushed)` entre todos os peers conhecidos. Eventos com `seq ≤ watermark` já foram vistos por todos → compactáveis. Eventos acima do watermark ficam intactos (um peer atrasado ainda pode precisar deles). Na topologia atual (1 peer `hub-vps`), o watermark é o `last_seq_pushed` do hub.

### 4.2 Compaction semântica (preserva LWW por campo)

⚠️ **O ponto crítico.** `_resolve_md_fields` (sync/apply.py) faz **LWW field-level**: cada campo de metadata (`tags`, `memory_type`, custom keys, `updated_at`) tem vencedor próprio = menor `_winner_key` na encarnação viva. **Manter o último evento cru PERDE** campos cujo vencedor está num evento anterior. Logo a compaction NÃO é "keep MAX(seq)"; é:

1. Para cada `content_hash` com eventos `update_metadata` abaixo do watermark:
2. Reconstruir o estado LWW resolvido reusando a MESMA função de resolução do sync (não reimplementar — chamar o resolver, garantindo paridade).
3. Escrever **um** `update_metadata` consolidado com o estado resolvido, HLC = o do evento vencedor (não um novo HLC — R7), `seq` ≤ watermark.
4. Remover os demais `update_metadata` daquele hash abaixo do watermark.
5. Tudo numa transação por lote; fail-closed (R8).

### 4.3 Agendamento

Job no `ConsolidationScheduler` (onde já vivem quality/utility recompute), cadência diária (alinhado ao precedente PowerSync de compaction diária). Kill-switch por env (`MCP_SYNC_COMPACTION_ENABLED`).

### 4.4 Estimativa (lab 29/out, cópia do banco vivo)

| Alavanca | Resultado medido |
|---|---|
| Compaction `update_metadata` + VACUUM | **1928 MB → 1039 MB (−46%)** |
| sync_events: 1.382.818 → 62.247 linhas | update_metadata 1.345.590 → 25.019 |
| integrity_check pós-VACUUM | `ok`; memórias/embeddings/beliefs intactos |

> ⚠️ O lab usou poda ingênua (MAX(seq)) só para medir TAMANHO/integridade física. A compaction REAL (§4.2) preserva LWW por campo — número de redução esperado é equivalente, mecânica é mais fina.

---

## 5. Território adjacente (fora do escopo deste BUG, registrar)

- **Recompute local não-sincronizável (causa raiz do volume).** Quality/utility é estado derivado determinístico e local; não precisa viajar como ~100k eventos/dia. Marcá-lo fora do event log atacaria a GERAÇÃO, não só o acúmulo. Mexe no contrato de sync → **FEAT própria + discussão com o Henry** (não entra neste bug). Abrir RFC separada se o Claudio aprovar a direção.
- **Órfãos `memory_graph`** (97.765 / 740.898 = 13%) → `rfc-memory-hygiene` (já existe), não aqui.
- **Retenção `usage_events`** (janela deslizante + rollup) → hygiene ou RFC curta própria.
- **Quantização de embeddings** → `rfc-embedding-quantization` (já existe).

---

## 6. Blast radius (estado compartilhado — G0 pelo seven, 29/out)

`sync_events` é lido/escrito por **mais caminhos que os 5 iniciais** — o G0 encontrou 2 leitores laterais materiais. Qualquer mudança DEVE provar que TODOS convergem.

**Escritores:** `metadata.py:213` (update_metadata, ÚNICO emissor), `store.py:304,473` (create), `delete.py:119,215` (delete).

**Leitores (os 5 da RFC + 2 laterais achados no G0):**
| Caminho | path | papel | interação com compaction |
|---|---|---|---|
| resolução LWW | `apply.py:422 _load_live_events` + `:494 _resolve_md_fields` | reconstrói estado vivo field-level | **REUSAR** (não reimplementar) — paridade + fronteira de encarnação |
| materialização | `apply.py:587 _materialize_update_metadata` | orquestra os 3 passos | é o estado que o consolidado deve reproduzir |
| pull servidor | `web/api/sync_events.py:77` feed `WHERE seq>?` | serve eventos ao peer | poda ≤ watermark é invisível a quem já passou |
| pull/push cursor | `orchestrator.py:72 sync_cursor` / `:269 push` | cursor por seq | não quebra se poda ≤ MIN(cursor) |
| bootstrap | `bootstrap.py:53 MAX(seq)` + `:66-83 HLC-par ROW_NUMBER` | watermark + HLC por hash | **consolidado deve preservar HLC-par do vencedor** senão bootstrap emite clock menor |
| resolver | `resolver.py:46 _winner_key` | total-order (menor vence) | HLC é PAR ordenado, não MAX por coluna |
| **recreate_of (LATERAL)** | `store.py:110 WHERE op='delete'` | carimba recreate no novo create | SEGURO sse R4 (delete nunca compactado) — cobrir em teste |
| **seed HLC boot (LATERAL)** | `base.py:589 _seed_last_hlc_on_first_boot MAX(hlc)` | piso de monotonicidade no boot | se remover evento de maior HLC sem preservar par no consolidado → seed regride → edit futuro perde |

**Condições não-negociáveis (G0):**
1. Reusar `_load_live_events`+`_resolve_md_fields` — paridade bit-a-bit com o sync.
2. Evento consolidado: **HLC-par do vencedor** (não gerar novo; não MAX por coluna) + **seq ≤ watermark** + **event_id determinístico** (padrão `_deterministic_event_id` do bootstrap, para idempotência).
3. Compactar **só `op='update_metadata'`**, **só abaixo de `MIN(last_seq_pushed)`**, **por encarnação viva**; `create`/`delete` intactos.

Checklist Greptile do G5 aplica direto: item 1 (campo trafega ponta-a-ponta / não vazar chave local-only para o payload), item 4 (HLC par ordenado), item 6 (cursor não regride).

---

## 7. Critérios de Aceite (G0 fechou os testes T1-T7)

- [ ] **T1 paridade LWW multi-campo:** estado consolidado == fold da cadeia completa, com vencedores de campos em eventos diferentes (tags no evento X, memory_type no evento Y).
- [ ] **T2 HLC-par preservado:** após compaction, `bootstrap._read_snapshot` elege o MESMO (physical,logical) por hash; `_seed_last_hlc_on_first_boot` (base.py:589) não regride o clock.
- [ ] **T3 recreate_of intacto:** `store.py:110` ainda elege o delete dominante correto (deletes não tocados — R4).
- [ ] **T4 watermark:** nenhum evento com `seq > MIN(last_seq_pushed)` tocado; `sync_cursor`/`push_cursor` inalterados (R2/R7).
- [ ] **T5 recreation boundary:** encarnações não mescladas; compactar hash com create-após-delete não vaza campos da encarnação morta (R3).
- [ ] **T6 idempotência + fail-closed:** 2ª run imediata é no-op (event_id determinístico); lote falho deixa o log idêntico (R5/R8).
- [ ] **T7 convergência 2 instâncias:** hub+spoke HTTP real — compactar o spoke NÃO altera o resultado do sync contra o hub (prova quente, padrão G5).
- [ ] **`tests-prove-fix` verde:** teste de compaction falha em `main` (sem o fix) e passa na branch.
- [ ] VACUUM roda e reporta bytes recuperados (R6).

---

## 8. Plano de implementação (gates)

- **G0** — ✅ FEITO (seven, 29/out). Blast radius: 5 caminhos + 2 leitores laterais (store.py recreate_of, base.py seed HLC). Função a reusar confirmada (`_load_live_events`+`_resolve_md_fields`). Veredito: viável/seguro sob as 3 condições não-negociáveis (§6). Recomendação: `index_repository` antes do G3 (grafo 10 dias defasado).
- **G3** — testes RED T1-T7 (rok). Incluir os 2 leitores laterais (T2 seed HLC, T3 recreate_of).
- **G4** — código: job de compaction + kill-switch `MCP_SYNC_COMPACTION_ENABLED` + reuso do resolver (não reimplementar). HLC-par do vencedor, seq ≤ watermark, event_id determinístico.
- **G5** — checklist Greptile (§6) + subagent(tuvok) + E2E quente 2 instâncias. Doc-sync (architecture-overview/troubleshooting se citarem o log).
- **PR** — `Fixes` (se houver guarda-chuva do delta-sync) + 2 runs `tests-prove-fix`. Bug = sem fila.
- **Aplicar no banco vivo** — SÓ após código provado; backup (`VACUUM INTO`) antes; replicar ao hub VPS no mesmo fluxo.
