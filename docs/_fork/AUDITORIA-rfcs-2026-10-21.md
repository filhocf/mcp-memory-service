# Auditoria das RFCs do fork — fork/main x upstream

**Data:** 2026-10-21 · **Fonte:** `fork/main @ 9d62f6d3 2026-10-20` · **Metodo:** inventario de `docs/rfc/`, cruzamento com a API do upstream (PR/issue/discussion) e com `git diff upstream/main..main -- src/`.

> *implementada* = feature presente em `src/`; *upstream* = existe PR mergeado no `doobidoo/mcp-memory-service`. A maioria e implementada no fork e NAO esta no upstream.


## 1. Fotografia

| medida | valor |
|---|---|
| RFCs no fork | **89** (64 `planned/`, 25 `implemented/`) |
| RFCs com PR mergeado citado | 23 |
| RFCs sem nenhum PR mergeado | 66 |
| Codigo fork-only | **16 arquivos novos** + 33 modificados em `src/` |
| PRs nossos mergeados no upstream | 101 (de 114 enviados) |


O ponto que desfaz a confusao: **o fork nao e um projeto paralelo.** E o upstream + 16 arquivos novos. O resto dos 453 commits a frente e documentacao (`docs/rfc/planned` 112 commits, `ESTADO.md` 60, `LEDGER` 32).


### Arquivos de codigo que so existem no fork
```
src/mcp_memory_service/cli/doctor.py
src/mcp_memory_service/data/store_terms.json
src/mcp_memory_service/extraction/facts.py
src/mcp_memory_service/harvest/agents/__init__.py
src/mcp_memory_service/harvest/agents/kiro.yaml
src/mcp_memory_service/harvest/tracker_utils.py
src/mcp_memory_service/harvest/triage.py
src/mcp_memory_service/reasoning/store_terms.py
src/mcp_memory_service/server/handlers/facts.py
src/mcp_memory_service/server/handlers/gaps.py
src/mcp_memory_service/storage/context_injection.py
src/mcp_memory_service/storage/migrations/013_add_memory_gaps.sql
src/mcp_memory_service/storage/migrations/014_add_usage_events.sql
src/mcp_memory_service/storage/migrations/020_add_facts_extracted.sql
src/mcp_memory_service/storage/migrations/021_add_belief_embedding.sql
src/mcp_memory_service/storage/usage_telemetry.py
```


## 2. Situacao por arco

| arco | RFCs | estado verificado | evidencia | acao |
|---|---|---|---|---|
| **delta-sync** | 10 | Fechado no upstream (5 fases + fixes #1522) | #1478/#1485/#1487/#1489/#1494/#1562 mergeados | mover specs para implemented/ |
| **hermes/UIAA** | 6 | Fechado no FORK (D3/D7/D8, 20/out); D4 no upstream | doctor.py e instalador em src/; #1598 mergeado | mover D3/D7/D8/agent-id; D5 fica |
| **harvest** | 9 | Absorvido pela ingestao multi-agente | #1350/#1366/#1378/#1379/#1395 mergeados | arquivar 3 absorvidas; manter sessoes |
| **ingestao-multi** | 2 | Guarda-chuva vivo (#1393, #1346) | — | manter |
| **learning-loop** | 12 | Fork-only, vivo (o NORTE) | context_injection.py, usage_telemetry.py so no fork | manter |
| **dreaming** | 8 | Fork-only: INC1/2/3/6 feitos; INC4 cancelado; INC5/7 pendentes | opt-ins em src/ | manter |
| **belief** | 3 | Fork-only, a doenca: derive_beliefs copia (314/314) | belief_service.py divergiu do upstream | corrigir rfc-s2 -> planned/ |
| **rating-quality** | 5 | Fechado, upstream | #1349/#1368/#1391/#1404 + #1215 | manter em implemented/ |
| **multi-store** | 2 | Base no upstream; divida #1465/#1466 aberta | #1395/#1469 mergeados | manter |
| **agent-id** | 1 | Upstream | #1278/#1297/#1598 | manter |
| **portabilidade** | 6 | Absorvida (5 camadas, #1364) | wiki no upstream | arquivar RFC + 4 anexos |
| **hub-sync-legado** | 3 | Superseded pelo delta-sync (ADR-0002) | hub-and-spoke abandonado 4/out | arquivar 2; hybrid-http -> implemented/ |
| **inbox-inter-agente** | 1 | Viva, aguardando Henry (#1529) | RFC commit e2fd1cf0 | manter |
| **estrutura-refactor** | 5 | Refactor entregue, sem PR proprio | s8/s9/s13 ja no codigo | arquivar 4 |
| **gates-G0** | 3 | Artefatos de processo | — | arquivar 3 |
| **backlog-ideias** | 13 | 13 RFCs de 30/set, sem codigo, sem PR | — | DECISAO do Claudio |

## 3. As quatro acoes

### 3.1 Mover `planned/` -> `implemented/` (17) — entregues
```
rfc-delta-sync.md
spec-delta-sync-fase1.md
spec-delta-sync-fase2.md
spec-delta-sync-fase3.md
spec-delta-sync-fase4a.md
spec-delta-sync-fase4b.md
spec-delta-sync-fase4c.md
spec-delta-sync-fase4d.md
spec-delta-sync-fase5.md
spec-delta-sync-1522-fixes.md
rfc-hybrid-http-secondary.md
spec-d3-mms-doctor.md
spec-d7-instalador.md
spec-d8-porta-transporte.md
spec-agent-id-streamable.md
spec-fase0-kiro-yaml-triagem.md
spec-store-visibility.md
```


### 3.2 Mover `implemented/` -> `planned/` (1) — status mentiroso
`rfc-s2-belief-store.md` — a propria RFC avisa "marcada implemented por engano".


### 3.3 Arquivar (20) — absorvidas, superseded ou artefato de gate
```
rfc-sync-multi-agente.md
rfc-hub-memoria-centralizada.md
rfc-harvest-source-identity.md
rfc-harvest-kiro-sessions.md
rfc-harvest-design-extraction.md
rfc-memory-portability.md
rfc-memory-portability-agent-hermes.md
rfc-memory-portability-agent-kiro.md
rfc-memory-portability-memory-mem0.md
rfc-memory-portability-memory-mnemosyne.md
rfc-self-service-memory-intelligence.md
rfc-learning-loop-hermes-ideas.md
rfc-g0-store-ner.md
rfc-g0-i1-toolresults-cli-kind.md
rfc-g0-design-extractor-i2.md
rfc-s13-tool-registry-wiring.md
rfc-s8-handler-extraction.md
rfc-s8-tool-registry.md
rfc-s9-split-config.md
rfc-structural-improvements.md
```


### 3.4 Manter (51) — 38 em `planned/` + 13 em `implemented/`


## 4. O que faz sentido e o que nao faz

**Manter como documento tecnico vivo:** `rfc-belief-synthesis` (diagnostico da doenca), `rfc-inter-agent-inbox` (tese falsificavel, 4 falhas de heartbeat como evidencia), `spec-learning-loop-b/c/e` e `rfc-learning-loop-a-rerank` (descrevem codigo que roda e e medido), `rfc-harvest-sessoes` (61% nunca colhidas — dor aberta). Backlog com mecanismo claro: `working-memory`, `memory-hygiene`, `ranking-upgrades`, `embedding-quantization`.

**Nao faz sentido manter na arvore viva:** guarda-chuvas que duplicam o ESTADO (`rfc-learning-loop`, `rfc-dreaming-loop` — manter so como indice curto); os 4 anexos de portabilidade (viram wiki no upstream); gates G0 (evidencia de processo, nao de produto); `rfc-structural-improvements` (generico, sem criterio nem dono); `rfc-query-intent` (PAUSADA e declarada de valor marginal).

**O que nao fazer:** nao apagar nada de `implemented/` que tenha ido ao upstream (e o registro de que o trabalho existiu); nao mover `spec-hermes-state-db-importer` (D5 — o `--apply` nunca rodou); nao tratar "sem PR citado" como "nao entregue" (7 specs de delta-sync estao assim e todas foram mergeadas).

## 5. Riscos revelados pela auditoria

1. **Dois SHAs do LEDGER fora da `main`**: `4358c29b` (NER PT-BR/EN) e `d017a1d4` (harvest Kiro IDE). Marcados "VERIFICAR" desde 12/out, nunca resolvidos — definicao de risco de perda.
2. **`_index.md` declara 47 RFCs** (23+24) contra **89 reais**: quem navega por ele nao encontra metade do acervo.
3. **`ARCOS.md` (14/out) nao conhece** F2 store visibility, reranker medido, doctor, instalador, indice uniforme — seis mudancas de estado.


## 6. Resolucao das pendencias (21/out, mesmo branch)

- `rfc-query-intent` arquivada — decisao do Claudio.
- Veredito das 2 linhas `VERIFICAR` do LEDGER: `4358c29b` (NER PT-BR/EN) e `d017a1d4` (harvest Kiro IDE) **ambas portadas ao upstream** (`upstream/main` tem `ner_patterns/pt_BR.yaml` e `messages.jsonl` em harvester.py/parser.py). Nenhuma perdida; LEDGER corrigido.
