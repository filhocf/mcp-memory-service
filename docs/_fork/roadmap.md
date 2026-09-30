# mcp-memory-service — Mapa de Épicos (roadmap do fork)

**Criado:** 15/set/2026 · **Atualizado:** 30/set/2026 tarde (ARCO 3 rating FECHADO via #1368 no upstream — retention_periods corrigido, #1349 desmascarado; **#1378 MERGEADO** pelo Henry 13:14 UTC; #1379 APROVADO aguardando merge. Ordem de fechamento dos 4 arcos definida com Claudio no todo_list. Ver PILHA-PRs snapshot 30/set.). Fila Henry: #1379 (approved, aguarda merge) + 2 RFCs (#1345/#1346).  

> **📍 SNAPSHOT 30/set TARDE (DNBSCDC289) — fechando arcos 1 a 1:** Claudio definiu ordem de fechamento dos 4 arcos (esforço×impacto) no todo_list. **ARCO 3 (rating/quality) FECHADO:** o furo #1355 (retention_periods keyed por legados → tudo cai em 30d → quality sem efeito no decay) foi corrigido pelo **#1368** (rubenmarcus, 73674e4d) no upstream; trazido p/ nossa main (merge eee64834). Verificado: config/consolidation.py agora tem chaves da ontologia (decision:365/learning:180/pattern:90/error:30/observation:30 + legadas). IMPACTO: com retention corrigido, nosso #1349 (quality-split) VOLTA a ter efeito no decay — antes mascarado (timkjr mediu r=-0.006). 542 testes verdes. **ARCO 1 (harvest):** **#1378 MERGEADO** pelo Henry 13:14 UTC (a95f85f2 — discovery+id+resolve workspace); **#1379 APROVADO** (SQLite+idioma), aguardando merge (decisão: aguardar Henry, não self-merge). **G0 do I2 FEITO** (doc G0-design-extractor-I2.md): design-extractor = caminho alt ao PatternExtractor p/ blocos longos, reusa HarvestRewriter+locale(#1382)+NLI cascade(#1215). PRÓXIMO ARCO 1: I1 (visibilidade thinking/ToolResult) + I2 (gate: #1379 mergear→números Phase 0→alternativas baratas antes do LLM). main fork 0 atrás do upstream (eee64834).

> **📍 SNAPSHOT 30/set (DNBSCDC289):** arco harvest multi-formato ENTREGUE ao upstream. **PRs:** #1378 (workspace discover+id+resolve+guard) CLEAN/verde; #1379 (SQLite parser + idioma Phase 0) verde, aguarda review. Ambos gate TDD, Greptile SUCCESS, 0 threads. **Issues:** #1376 (discovery) + #1377 (SQLite) + #1390 (conversor mem0, 4 pontos RFC). **#1364 portabilidade:** Henry ACEITOU o modelo de 5 camadas; 3 compromissos honrados — RFC design-extraction **v0.4** (idioma = honrar locale via config/locale.py, correção do Henry: 85-89% pt-BR é do operador, não da base), **wiki Memory-Portability-Map** (5 camadas × harnesses), issue #1390. RFC nova **source-identity v0.1** (descoberta+identificação de fonte por agente — CLI/IDE/Crew têm metadado de identidade próprio). Doc CdIA INVENTARIO §2.5. Grupo I reordenado: I0(#1350 merged)+I0-lang+discovery(#1378)+SQLite(#1379) entregues; falta I1(ToolResult visibility)/I2(extractor, gated locale). **Issues novas do Henry p/ avaliar (área rating/quality):** retention_periods mismatch + quality~no-effect-on-decay + MCP_DECAY_ENABLED no-effect.
**Fonte:** 18 RFCs em `docs/rfc/` (main) + Trilogia RFC-MM + itens task-orchestrator + issues abertas doobidoo.  
**Convenção:** cada épico = 1 tema coeso que vira 1+ PR (ex: re-harvest safety). Épicos grandes têm fases.  
**Regra de fluxo:** PR sai de `upstream/main` limpo · E2E real antes de PR · doc no mesmo commit · >1 arquivo → gate · 1-PR-por-vez (fila do Henry).

> **Par de docs que seguimos:** ESTE roadmap (visão de épicos) + `pilha-prs-runbook.md` (estado operacional da pilha). Mexeu/mergeou → atualizar AMBOS.

> **📍 SNAPSHOT 29/set (DNBSCDC289 — manhã):** Sessão foco memory-service. **(1) RFC #1364 portabilidade:** Henry corrigiu a matriz célula-a-célula (OpenCode tem lifecycle plugin, harvest Kiro/OpenClaw real, `MemoryImporter` já existe) e redefiniu escopo como **N adapters + M conversores** (não N×M), propondo conversor mem0 como 1º PR. **Respondemos** (discussioncomment-18662539): aceitamos correções factuais + N+M, mas reabrimos o lado do harness — "alcançável via MCP" ≠ "prefere este store", que é uma PILHA de 5 camadas (conectividade → conector/plugin → hooks → override de preferência → **toolkit de uso/skill**), com evidência empírica (Hermes vem com SQLite nativo; a T'Pol ignorou nosso MCP até eu forçar preferência; Kiro deu trabalho árduo). **Foco Claudio:** Kiro, Hermes, OpenClaw, OpenCode, DeepSeek. **Proposta central: WIKI viva** (matriz evolui no lugar, progresso por harness) em vez de thread — pedimos ao Henry o caminho onde colocá-la (has_wiki=true no upstream). Aguarda ele apontar local. **(2) RFC design-extraction → v0.3** (commit fork `671098cc`): adicionado o **eixo IDIOMA** — R0.4 (Phase 0 mede idioma por bloco via langid, MEDIÇÃO não inferência) + R3.1 (extractor/NLI multilíngue-pt-BR, **gated** no que o R0.4 reportar; reusa backend cascade #1215). Corpus é majoritariamente pt-BR → extractor en-only degradaria silenciosamente. **CORREÇÃO DE ENTENDIMENTO:** o I0/Phase 0 do #1350 (contagem seen/extracted/dropped per-block kind) JÁ está mergeado — o próximo trabalho é **ESTENDER** esse instrumento com a dimensão de idioma, não criar do zero. **PRÓXIMO: implementar a extensão de idioma no Phase 0** (gate: RFC pronta → dev-tests RED → dev-python GREEN → reviewer). **(3) PR #1373** (backfill supersession) segue MERGEABLE, CI verde, Greptile sem novos P1 — aguarda Henry mergear.

> **📍 SNAPSHOT 28/set (DNBSCDC289 — TARDE, resgate sessões):** **Feature fork-only nova: action `harvest` no `memory_consolidate`** (commit `0ccaf01e` na main). Harvest sob demanda com `path` (params `sessions/use_llm/dry_run/force_reharvest`), **in-process** (grafo/dedup/provenance íntegros — standalone degrada, provado no piloto). Preenche o gap do `memory_harvest` bloqueado no HTTP (GHSA-7crr-2r7w-cpfm). ⚠️ **1º commit `aee64cad` reintroduzia o path-traversal** (path do cliente sem validação) — pego pelos gates arch+reviewer; **fix `0ccaf01e`**: guard `resolve()`+allowlist `MCP_HARVEST_ALLOWED_ROOTS` (default fechado). 16 testes incl. bloqueio traversal/symlink. reviewer **APROVADO PARA PR**. **Resgatadas 195 conversas SQLite CLI** (dez25–jun26, só no `data.sqlite3`) → 37 mems com grafo; 0 missing embeddings. **LIÇÃO: implementei sem gates 2× no dia → gate pegou vuln de segurança real.** PENDENTE: doc (feito: REFERENCE-MEMORY-PIPELINE §2.5 + AGENTS + este) → **PR upstream** (candidato B-harvest-ondemand; sincronizar upstream + checar issue vizinha antes; provável RFC curta). Outros acervos agora triviais (backup 2039 payload-wrapped, IDE 554 precisa parser history[], KiroCrew).

> **📍 SNAPSHOT 28/set (DNBSCDC289):** **#1349 (quality split #1312) MERGEADO pelo Henry** (28/set 03:07, commit upstream `97e699e0`). **O ARCO RATING/QUALITY-MODEL ESTÁ ENTREGUE AO UPSTREAM** — a peça central (separar `computed_quality` de `user_rating`, materializar effective score, forgetting lê computed) é oficial na v11.14.0+. main mergeada com upstream (7 commits: #1349 nosso + #1358 triage-digest GH + #1356 CF topK + #1357/#1351 docs-roadmap + #1360/#1146 log-sanit + #1353 test-hybrid). **main ahead 62 / behind 0**, pushada github `98461cf9`, backup/main-pre-1349merge-20260928. Suíte quality 6/6 verde no venv de produção. Serviço reiniciado v11.14.0 healthy (23.113 mems). **FILA HENRY: VAZIA** (0 PRs nossos). Próximo alvo (ORDEM DE ATAQUE): H1 #1225 (bug high órfão, avaliar valor) ou D3 (query-intent quick win). Arco rating restante = F1/F5/F6 (design/config, não código urgente) + revalidar G0 (base mudou: #1291/#1240/#1216/#1312 mexeram no terreno).

> **📍 SNAPSHOT 27/set (NOITE — fim de sessão sirdata):** dia fechou a pilha quase inteira. **#1348 MERGEADO** (versioned/superseded, #1318). **#1350 MERGEADO** (harvest coverage instrument #1287 I0 — fix Greptile per-block counting keyed pelo kind do bloco + deep-copy do coverage\_report; gate G3-G5, commit rebaseado). **#1349 (quality split #1312) PRONTO e ready, aguarda Henry** — fechou o ÚLTIMO furo que o levou a draft: o association-boost em `decay.py update_memory_relevance_metadata` regravava `quality_score` com o valor boostado, desfazendo down-vote humano. Fix: boost é **retention-only** (eleva relevance\_score via quality\_multiplier sobre computed\_quality; NÃO toca quality\_score = effective\_quality(computed,user\_rating)); removidos campos `quality_boost_*` do metadata (codec ainda round-trips, ninguém lê p/ decisão). Teste do Henry adicionado (down-vote acima do MIN\_CONNECTIONS → quality\_score fica 0.25) + reescrito test\_association\_quality\_boost\_persists\_to\_memory p/ semântica retention-only. 395 quality+consolidation verdes, CI 14/14, commit fc88bebf. **RFC #1345 (delta-sync) → v0.3**: incorporados os 4 invariantes de aceite do @ducanhnguyen223 (§8: idempotência (agent\_id,event\_id)+tombstones; ordenação HLC+tie-breaker; consistência embedding/embedding\_pending; identidade/escopo no apply do peer; +cursor por-peer como fonte de verdade, PRAGMA data\_version só p/ staleness local). Branch doc/rfc-delta-sync-invariants, comentário postado. RFC #1346 (design-extraction) sem novos comentários. ⚠️ **github/main behind 60 do upstream** — main do fork precisa merge do upstream/main (rebase da linha fork-only) numa próxima sessão. FILA HENRY: só #1349 (REVIEW\_REQUIRED) + review das 2 RFCs.

> **📍 SNAPSHOT 24/set:** fila upstream **VAZIA** (0 PRs nossos abertos). Mergeados desde 18/set: **#1297** (Fase 2 agent\_id, 24/set), **#1265** (nli-obs/B2, 19/set), **#1288** (F2 rating last\_accessed, 22/set). Cedidos à Vera (massimiliano1991): **#1294/#1289** e **#1216** (closed). **Canal hub VPS FEITO** (2 camadas nginx+API key, doc SPEC-hub §12) → destrava D7. Novo: **#1301** (Henry pediu opinião OAuth/API-Key — respondida, dual-auth já existe). RFCs #1290 (quality) e #1286 (trilogia) publicadas como discussions (aguardam Henry).

> **📍 SNAPSHOT 26/set (noite):** Henry mergeou tudo — README revamp (#1322/#1323, 589→265 linhas) + 7 commits. main = v11.14.0+14 (github 0b7ed4ea, backup/main-pre-1326merge). **#1224 CLOSED** (nossa corroboração ajudou). **#1318 ainda OPEN** (Henry olha os comentários depois — nossa posição Opção 1 aguarda). 🎯 **#1326 (evolve through MemoryService so they get scored) é INPUT DIRETO pro arco rating E pro #1318:** o `_try_evolve()` chamava `update_memory_versioned()` direto, PULANDO quality scoring/agent\_id/entity/plugins — dado de produção deles: “301 de 348 mems sem score eram evolved harvest”. Criaram `MemoryService.evolve_memory()` que envolve versioned+scoring. Isso é o buraco do F1 (quality null) parcialmente tapado E o lugar natural onde o fix do #1318 (setar coluna superseded\_by) encaixa. Merge teve 1 conflito real (nossa verify\_session\_coverage era anterior aos fixes Greptile) → resolvido com upstream (superset). Regressão: 689 passed.

> **📍 SNAPSHOT 26/set (manhã):** upstream andou 3 commits em consolidation/ (todos absorvidos, merge limpo — não temos fork-only ali): **#1302** (UTC decay ref\_time), **#1317** (fix: contradiction detection nunca fazia supersede — bug de fundo, reescreveu [contradictions.py](http://contradictions.py)), **#1320** (feat `MCP_CONSOLIDATION_AUTO_SUPERSEDE`, default true). main = **v11.14.0 + 7 commits** (602eeefe→c6747103, backup/main-pre-consolidation-20260926). ⚠️ **DECISÃO: setamos `AUTO_SUPERSEDE=false`** (env compartilhado + sirdata.env) — o #1317 LIGOU o superseding-por-contradição que estava dormente; com nosso `graph_only`+`CONSOLIDATION_ENABLED=true`, memórias “contradicts” (conf≥0.75) sumiriam do retrieval na próxima consolidação. `STORE_ASSOCIATIONS=false` NÃO protegia (só gateia o caminho memories\_only; graph\_only passa direto pelo \_auto\_supersede). false = mantém aresta no grafo + ambas visíveis. Conservador enquanto arco rating/#1312 aberto. Serviço sirdata ainda NÃO reiniciado com o código novo (aguarda OK). **Vizinhança do arco rating:** #1317/#1320 usam `superseded_by` ativamente → informa o design de qualidade (#1312) e o F6 anti-hallucination.

> **📍 SNAPSHOT 25/set:** main mergeada para **v11.14.0 + 4 commits** (#1306/#1146, #1307, #1315, #1316; merge limpo, backup/main-pre-v11140merge-20260925). **Discussion #1312** (quality-model RFC v0.2, arco B2) POSTADA — 4 perguntas p/ Henry (normalização rating→quality, threshold D4a, materialização, codec version). ⚠️ **#1290 (22/set) é antecessor do #1312 — duplicata temática, fechar como superseded.VPS hub A0-A3 COMPLETO**: banco autoritativo corrigido (era memory.db 419 mems, agora sqlite\_vec.db 19.585), v11.14.0, consolidação ligada, sync bug-auth-401 corrigido (mistake a1de2c29), SPEC-hub §12 reconciliada. **Deriva pendente (A4, não iniciado):** hosts pararam de subir hot.db recente ~10 dias — investigar [hot-backup.sh](http://hot-backup.sh) + OneDrive do lado dos hosts. Revalidação arco rating: F2 resolvido upstream (#1288+#1291); F1/F3/F4/F5/F6 abertos (design/config, não corrupção) — ver ~/.kiro/tmp/arco-rating-revalidacao-25set.md.

## 🔥 PIPELINE DE CONTRIBUIÇÃO — estado 26/set (fim de dia) — Henry engajado, 5 frentes

Balanço do dia: de manhã a fila parecia “seca” (tudo mergeado); à noite o Henry respondeu 3 discussions nossas COM escopo de PR + apareceu 1 issue vizinha. Todas na nossa área (quality/harvest/storage/consolidation). Ordem sugerida de ataque nas próximas sessões:

| # | Frente | Estado c/ Henry | Próximo passo | Escopo definido? |
| --- | --- | --- | --- | --- |
| **1** | **#1318** versioned/superseded | ✅ **PR #1348 MERGEADO** (27/set) | — | ✅ concluído |
| **2** | **#1312** quality-model | ✅ **PR #1349 MERGEADO** (28/set, upstream 97e699e0) — arco rating entregue | — (arco central concluído; resta F1/F5/F6 design/config) | ✅ SIM (2 campos origem; forgetting/decay leem computed\_quality; boost NÃO reescreve quality\_score; normalização −1/0/+1→0.25/0.5/0.9) |
| **3** | **#1287** design-extraction (grupo I) | ✅ **#1350 (Phase 0 instrumento) MERGEADO** (27/set) + **RFC #1346** aberta | aguardar Henry na RFC #1346; extractor real é fase seguinte | 🟡 Phase 0 feito; extractor pós-RFC |
| **4** | **#1285** agent\_id F2/F3 | 🔵 discussão ativa | amadurecer Fase 3 | 🟡 distinct agent\_id NECESSÁRIO mas nunca suficiente p/ perspective\_conflict — precisa 2º sinal |
| **5** | **#1304** hybrid remote secondary | ✅ ASSIGNADO; **RFC #1345 delta-sync v0.3** responde os invariantes do revisor | aguardar Henry; delta-sync sequenciado atrás do #1304 | 🟡 #1345 §8 formaliza idempotência/ordenação/embedding/escopo |

### 📮 ANTES DE CODAR — promessas de comunicação a postar (estratégia Claudio 27/set: esvaziar comunicação antes do código)

| Promessa | Onde | Estado |
| --- | --- | --- |
| Responder 2 perguntas do #1304 | #1304 | ✅ POSTADO 27/set (issue comment 5855739880) |
| Abrir **RFC delta-sync como issue própria** | **#1345** | ✅ ABERTA 27/set (v0.2, contra agent\_id #1100, §7 framing #1304). Aguarda resposta Henry |
| Abrir **RFC design-extraction como issue própria** | **#1346** | ✅ ABERTA 27/set (v0.2 c/ Phase 0/coverage≠yield/3º estado dashboard) |
| #1290 fechar como superseded do #1312 | #1290 | ✅ FECHADA 27/set (OUTDATED) |

**#1290** = duplicata do #1312 (fechar superseded). **#1330** (@timkjr, review nosso APPROVED) = deixado pro Henry mergear (Greptile P1/P2 pendentes do autor). **#1224** = CLOSED.

**Regra reforçada (Claudio 2x hoje):** NÃO classificar como “done” notificação que toca território ativo nosso — #1287 e #1304 quase viraram done sem comentar e renderam contribuição de peso.

## Legenda de dimensionamento

*   **Esforço:** 🟢 baixo (≤1 sessão) · 🟡 médio (1-2 sessões) · 🔴 alto (3+ sessões / multi-PR)
    
*   **Dificuldade:** ★ (mecânico) · ★★ (design local) · ★★★ (arquitetural, toca vários módulos)
    
*   **Passos:** nº aproximado de PRs/fases
    
*   **Dep. Henry:** precisa OK dele antes (feature grande) ou é contribuição direta
    

## A. MERGED (atualizado 25/set — tudo mergeado, fila nossa vazia)

| Épico | Estado | Nota |
| --- | --- | --- |
| harvest provenance (#1243) | ✅ MERGED | — |
| verify\_session\_coverage (#1252) | ✅ MERGED | — |
| warn-env (#1253) | ✅ MERGED | \= B/F5 |
| release-bump exemption (#1250) | ✅ MERGED (fb8aba4c) | 6 edges/4 rodadas — lição gate+E2E |
| B2 nli-observability (#1265, closes #1235) | ✅ MERGED 19/set | E2E real pegou bug tupla que mocks escondiam |
| F2 rating last\_accessed (#1288) | ✅ MERGED 22/set | decay lê last\_accessed, não updated\_at |
| **B3 agent\_id Fase 1+2 (#1278 + #1297)** | ✅ MERGED 24/set | filtro opt-in + header X-Agent-ID. **Destrava delta-sync** |
| **#1312 quality-model split (#1349)** | ✅ MERGED 28/set (upstream 97e699e0) | **arco rating — peça central.** computed_quality vs user_rating, effective score materializado, forgetting lê computed. Resta F1/F5/F6 (design/config) |
| canal hub VPS (infra, não-PR) | ✅ FEITO 24/set | 2 camadas nginx auth\_basic + API key. Doc SPEC-hub §12 |
| #1301 OAuth/API-Key (opinião p/ Henry) | ✅ RESPONDIDA 24/set | dual-auth já existe no middleware; má-config provável. Web layer (fora mandato merge) |

> **Fila upstream (nossa) VAZIA em 25/set.** Próximos candidatos a abrir: B1 re-harvest (código pronto) ou H1 #1225 (bug órfão high). #1224 FECHADO.

## B. FILA CURTA — B1/B2/B3 absorvidos; **B4 harvest-ondemand PRONTO p/ PR (28/set)**

| # | Épico | O que é | Esforço | Dif. | Passos | Estado |
| --- | --- | --- | --- | --- | --- | --- |
| **B4** | **harvest on-demand action** | action `harvest` no `memory_consolidate`: dispara harvest de um `path` sob demanda, in-process (grafo íntegro), com guard de path (`MCP_HARVEST_ALLOWED_ROOTS`). Resolve o gap do `memory_harvest` bloqueado no HTTP. | 1 PR | ★★ | sincronizar upstream · checar issue vizinha · (provável RFC curta) · abrir PR | 🟢 **CÓDIGO PRONTO na main fork (`0ccaf01e`), gates OK (arch+dev-tests+reviewer), 16 testes. Falta: sincronizar+checar vizinhança+abrir PR.** |
| ~~B1~~ | ~~re-harvest safety (R7)~~ | — | — | — | — | ✅ **ABSORVIDO pelo upstream (verificado 26/set)**: force\_reharvest no schema ([registry.py:825](http://registry.py:825)), should\_filter\_tracker trata found==0, tracker conta stored. Os 3 fixes do Henry já entraram. NÃO é mais trabalho pendente. |
| ~~B2~~ | ~~NLI observability (#1235)~~ | — | — | — | — | ✅ **MERGED #1265 (19/set)** |
| ~~B3~~ | ~~agent\_id multi-agent (#1100)~~ | — | — | — | — | ✅ **MERGED (F1 #1278 + F2 #1297, 24/set)** |

> **Próximo PR concreto = B4 harvest on-demand** (código pronto+gated na main fork; falta sincronizar upstream + checar issue vizinha antes de abrir).

## C. TRILOGIA RFC-MM (a “Onda 2” — o maior bloco parado)

RFC: `rfc-self-service-memory-intelligence.md` (717L, 7 seções). §1/§2/§4/§5/§7 JÁ shipparam no upstream.  
Falta: os 3 pilares de background (migrations 013/014/015 + tools + handlers). **✅ DESTRAVADO 25/set:** #1254 foi fechado, mas re-apresentado como **Discussion #1286** — e o **Henry VALIDOU** os claims contra v11.12.0/main (“they all hold”): confirmou que faltam `memory_facts`/`memory_gaps` em tools/registry.py e que migrations param em 012. Deu clarificação de escopo (é **background enrichment**, NÃO inter-agent messaging — esse já é padrão estabelecido zero-build via README “Multi-Agent Cluster”). Ou seja: deixou de ser “aguarda Henry” → **pode codar** (reescrever sobre v11.14.0; código-base em `2e1978d5`).

| # | Épico | O que é | Esforço | Dif. | Passos | Dep. Henry |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | **fact-extraction** | job 6h: observação→fato estruturado (memory\_facts) | 🔴 | ★★★ | 2-3 PR (migration+módulo+tool+handler) | ✅ validado #1286 |
| C2 | **gap-detection** | busca de baixa confiança → registra lacuna (memory\_gaps) | 🔴 | ★★★ | 2-3 PR | ✅ validado #1286 |
| C3 | **feedback-loop** | recalibra confiança de belief por uso/rating | 🔴 | ★★★ | 2-3 PR | ✅ validado #1286 |
| C4 | §6 anti-halluc (parcial) | abstain/insufficient-evidence explícito no retrieve | 🟡 | ★★ | 1 PR | talvez |

## D. MNEMOSYNE (9 RFCs inspiradas na ferramenta do Hermes/T’Pol — memória 7e811712)

Amadurecidas no fork (13/set). Ordem de valor sugerida na RFC: quantization+hygiene primeiro (quick wins de tamanho), depois as arquiteturais.

| # | Épico | RFC | O que é | Esforço | Dif. | Passos |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | **embedding quantization** | rfc-embedding-quantization (108L) | int8/bit vectors: 82→21MB (int8) ou →3MB (bit). MCP\_MEMORY\_VEC\_TYPE | 🟡 | ★★ | 1-2 PR (+ validar recall PT-BR) |
| D2 | **memory hygiene** | rfc-memory-hygiene (114L) | audit\_noise dry-run + clean\_noise + secret detection. Ataca 243MB FTS | 🟡 | ★★ | 1-2 PR |
| D3 | **query intent** | rfc-query-intent (98L) | classificação regex bilíngue PT/EN → ajusta pesos vetor/FTS | 🟢 | ★★ | 1 PR |
| D4 | **ranking upgrades** | rfc-ranking-upgrades (109L) | Weibull decay por tipo + polyphonic recall (4 vozes + re-rank) | 🟡 | ★★★ | 1-2 PR |
| D5 | **working memory** | rfc-working-memory (106L) | camada contexto quente (TTL, auto-inject, promoção→episodic) | 🔴 | ★★★ | 2-3 PR |
| D6 | **persona tier** | rfc-persona-tier (105L) | identidade portável auto-gerada + canonical store SSOT | 🔴 | ★★★ | 2-3 PR |
| D7 | **delta sync** | rfc-delta-sync (114L) | event-log delta multi-agente + cripto opcional (malha Zero/T’Pol/Scotty) | 🔴 | ★★★ | 3+ PR |
| D8 | **multimodal memory** | rfc-multimodal-memory (109L) | imagem/vídeo/áudio→texto via visão, sem BLOB. Caso ativo: infográfico Debian | 🔴 | ★★★ | 2-3 PR |
| D9 | **memory importers** | rfc-importers (106L) | BaseImporter + adaptadores (holographic/Hermes first). Vetor de adoção OSS | 🟡 | ★★ | 1-2 PR |

## E. SKILL AUTO-GENERATION (já tem itens task-orch RFC-SC-01/02/03)

RFC: `rfc-skill-auto-generation.md` (160L). Depende do skill-curator-mcp (nosso), não só do memory-service.

| # | Épico | Item | O que é | Esforço | Dif. |
| --- | --- | --- | --- | --- | --- |
| E1 | skill\_scout ampliar fontes | a097a7bc | PyPI, npm, awesome-lists | 🟡 | ★★ |
| E2 | sugestão proativa de skill | 4ff4474d | quando match < limiar | 🟡 | ★★ |
| E3 | gap detection ↔ tasks | c44caadd | correlacionar com tasks executadas | 🟡 | ★★★ |

## F. HIGIENE / MENORES — AUDITADO 15/set (maioria obsoleta/feita)

Backlog criado em mai/2026 (fork defasado). Upstream v11.12.0 absorveu quase tudo. Veredito:

| # | Item | Estado | Ação |
| --- | --- | --- | --- |
| F1 | CodeQL + dependabot + release notes | codeql/dependabot/release.yml JÁ existem; falta só auto-merge + release-notes-auto (discutível) | ❌ CORTADO (baixo valor, Henry CI-opinado) |
| F2 | README revisão | subjetivo | ❌ CORTADO |
| F3 | Onboarding por-cliente | `_get_onboarding_guide(client_type)` tem claude-code+kiro; falta openclaw/cursor/… | ✅ ÚNICO que fica → **migra para grupo G** |
| F4 | Legacy tools deprecation | v11 JÁ removeu a camada de tools legadas ([compat.py](http://compat.py)); item perdeu objeto | ❌ CORTADO (obsoleto) |
| F5 | warn env não-reconhecida | PR #1253 aberto | ✅ FEITO |
| F6 | Web update-check configurável | MCP\_UPDATE\_GIT\_REMOTE/BRANCH JÁ existem no upstream | ✅ RESOLVIDO (Henry) |

**Grupo F esgotado:** F5 feito, F6 resolvido, F1/F2/F4 cortados, F3 vai para G.

## G. CLIENT ADAPTERS — “traga sua memória” por cliente (estratégia de adoção)

Estratégia em DUAS metades por cliente/harness externo, no estilo Mnemosyne (“venha, trazemos suas memórias”):

*   **G-adapt (usar):** o cliente usa o memory-service como memória NATIVA — integração rica estilo `claude-hooks/` (hooks, auto-capture, session-harvest, natural-triggers). Hoje SÓ Claude Code tem isso (`claude-hooks/` no upstream). Falta Kiro CLI, OpenClaw, Hermes, Cursor, etc.
*   **G-import (trazer):** puxar a memória que o cliente já tem para o store — é o **D9 (rfc-importers)**, que cobre mem0/letta/zep/holographic(Hermes)/agentic. As duas metades juntas = a jornada completa de adoção.

| # | Épico | O que é | Esforço | Dif. | Passos | Dep. Henry |
| --- | --- | --- | --- | --- | --- | --- |
| G1 | **kiro-hooks** | integração Kiro CLI (espelha claude-hooks/: hooks, auto-capture, session-harvest) | 🟡 | ★★ | 1-2 PR | contribuição direta |
| G2 | **hermes adapter + importer** | Hermes usa o store como memória + importer holographic (par com D9). Valor interno alto (T’Pol/Scotty) | 🔴 | ★★★ | 2-3 PR | talvez |
| G3 | **openclaw adapter** | integração OpenClaw (referência: ClawHub/marketplace) | 🟡 | ★★ | 1-2 PR | contribuição direta |
| G4 | **outros clientes** | Cursor, Continue, Windsurf, Zed — config/onboarding formalizado (parte cruza F3 onboarding) | 🟡 | ★★ | 1 PR cada | direta |

> Nota: G-adapt (usar) é NOVO (sem RFC — escrever RFC-client-adapters). G-import é o D9 (RFC existe). Falta uma RFC-client-adapters que amarre a estratégia das duas metades. Padrão a espelhar: `claude-hooks/` (upstream).

## H. ISSUES ABERTAS UPSTREAM — cruzamento inicial 16/set, revisado 25/set (ver notas de atualização abaixo)

> **⚠️ Atualização 27/set (auditoria de issues via gh):** **#1224 agora CLOSED** — NÃO é mais alvo (as menções abaixo a "#1224 alvo real" são de 25/set, superadas). **#1146 tem dono ativo** (massimiliano1991) — NÃO pegar. Órfãs vivas restantes no nosso mandato: **#1225** (store sem embedding row, high, OPEN — único candidato H) e #1106 (web layer, fora mandato). Fechadas: #1224, #1216, #1102. Ver árvore ASCII (nó H) para o estado corrente.

> **⚠️ Atualização 24/set:** H3 **#1216 CLOSED** (Vera/massimiliano1991 resolveu — não é mais alvo). #1294/#1289 (nosso follow-up F2) **cedido à Vera e CLOSED**. **#1301** (novo, OAuth/API-Key) entrou — Henry pediu opinião, respondida (dual-auth já existe, web layer fora do mandato). #1102 (quality scorer) segue com VijaySreekar. Reler assignees antes de pegar QUALQUER issue — o cenário muda em ~24h.

> **⚠️ Atualização 25/set (verificado no GitHub):#1102 CLOSED** (H6 resolvido, não é mais alvo). **PR #1229 CLOSED** (o que “bloqueava” #1224) → **#1224 (critical, memory stop mata PID) VOLTOU a ser órfão OPEN sem assignee = ALVO REAL disponível** no lugar do #1216. **#1225 (high, sem embedding row) segue OPEN sem assignee.#1146 (log-sanit) sendo drenado incrementalmente por massimiliano1991** (PR #1314 storage/graph.py; #1306/#1146 handlers/memory.py já mergeado no nosso sync) — NÃO pegar, tem dono ativo. **Fila upstream de terceiros NÃO-vazia:** #1317 (@timkjr, contradiction detection never superseded — toca consolidation/, vizinho do arco rating/belief, MERECE OLHAR), #1314 (@massimiliano1991), #1302 (@linhongyu510 UTC decay). 0 PRs NOSSOS abertos (fila nossa segue livre).

Releitura das issues abertas do doobidoo e cruzamento com este roadmap. Divididas em: já-mapeadas,  
BUGS ÓRFÃOS (sem dono/PR — oportunidade de contribuição direta, alto valor de confiança), e features post-v11.

### 🎯 H-resgate 28/set — issues NOSSAS do Codeberg cruzadas com o código (autoria @filhocf)

Varredura das 24 issues abertas + cruzamento arquivo:linha do que já implementamos desde jul/2026 (quando foram abertas no Codeberg). timkjr #1352/#1354/#1355 (bugs consolidation, reais e confirmados) DEIXADOS com ele (ofereceu PR; decisão Claudio 28/set não pegar).

| # (CB) | Tema | Veredito (código atual) | Ação 28/set |
| --- | --- | --- | --- |
| #1098 (CB116) | LLM fallback auto_capture | ✅ SUPERADA — `classifier.py` multi-provider (groq→ollama→deepseek) + `auto_capture.py` min_confidence 0.6 + `harvester.py:379` use_llm; +provenance/coverage/reharvest | **FECHADA** (comment+close) |
| #1095 (CB102) | Hermes/SQLite adapter | 🟡 PARCIAL — parser multi-formato (claude/kiro/kiro-cli-v4 #1346) + `/api/harvest` + harvest on-demand (usado p/ 195 conversas SQLite) cobrem o núcleo; falta adapter genérico poll-based | **ATUALIZADA** → arco ingestão retroativa, PR em breve (re-escopo Hermes→SQLite genérico) |
| #1096 (CB113) | Rate-limit per-agent | 🟡 MADURA — agent_id (#1278/#1297) destravou o keying; falta throttle no `call_tool` (só existe web/oauth per-IP) | **ATUALIZADA** → arco multi-agente/hub, PR em breve |
| #1099 (CB117) | Embedding cache LRU+content-addr | 🟡 PARCIAL — query cache OK (`retrieve.py`→`embeddings.py:482`); store pula re-embed via dedup; MAS `_EMBEDDING_CACHE` dict sem bound (não LRU) + chave `hash(text)` instável entre processos. Fix: sqlite_vec usar `shared.py` LRU (que o milvus já usa) + content_hash | **COMENTADA** (status+fix), PR candidato pequeno |
| #1097 (CB114) | Prometheus/OTel metrics | 🔴 NÃO implementado (grep zero) — só via MCP tools | **MANTER** aberta, sem urgência |

**2 PRs sinalizados "em breve":** (1) SQLite data-source adapter genérico (#1095); (2) rate limiter no call_tool keyed por agent_id (#1096). Ambos fora do CODEOWNERS (server/storage) → PR normal c/ aprovação Henry.


### H-map — issues que JÁ são épicos nossos

| Issue | Épico | Nota |
| --- | --- | --- |
| ~~#1254~~ | C (Trilogia RFC-MM) | ✅ CLOSED → re-apresentado como **Discussion #1286**, **Henry VALIDOU** (25/set) → pode codar |
| #1247 | A/#1250 | ✅ MERGED (release-bump) |
| ~~#1235~~ | B2 (NLI observability) | ✅ MERGED #1265 |
| ~~#1100~~ | B3 (agent\_id) | ✅ MERGED F1 #1278 + F2 #1297 |
| #1095 | **G2 (hermes adapter)** | ⭐ a issue do Henry JÁ existe p/ o nosso G2 — vincular ao abrir |
| #1093 | ci ML lane | maintenance, baixa prio |

### H-bug — status revisado 16/set (releitura: vários JÁ têm dono/PR — NÃO pegar)

| # | Issue | Sev | Status 25/set (verificado GitHub) | Ação |
| --- | --- | --- | --- | --- |
| **H2** | **#1224** memory stop mata PID | 🔴 critical | ✅ **PR #1229 CLOSED (25/set) — SEM dono, SEM PR, OPEN** · área cli/lifecycle | ⭐ **ALVO REAL** (fix contido, alto valor — substitui o #1216 fechado) |
| **H1** | **#1225** store sem embedding row | 🔴 high | ✅ **OPEN, SEM assignee (25/set)** · #1237 cobriu o guard mas issue segue aberta; autor concluiu que gap veio de rebuild/migração (sem write path vivo) | ⚠️ avaliar: guard já existe, valor real é backfill/detecção — confirmar antes |
| ~~H4~~ | **#1146** 573 f-strings não sanitizados | 🟡 maint | ⛔ **zsxh1990 CLAIMED** (“PR shortly”) | NÃO pegar — pisaria em contribuidor |
| ~~H3~~ | ~~#1216~~ dedup 0.85 inanição belief/quarantine | 🟡 | ⛔ **CLOSED (massimiliano1991)** — não é mais alvo | — (alvo migrou p/ H2 #1224) |
| H5 | **#1106** API/dashboard sem store/partition | 🟡 bug | sem dono | disponível, mas web layer (fora mandato) |
| ~~H6~~ | ~~#1102~~ quality scorer openai≠local | 🟡 bug | ✅ **CLOSED (25/set)** — resolvido | — |

> LIÇÃO (reforçada 25/set): num repo ativo, o estado das issues muda em ~24h. #1216 (era “único alvo”) FECHOU;  
> #1229 (que bloqueava #1224) FECHOU → #1224 voltou a ser alvo. SEMPRE reler assignee + último comentário +  
> PRs citando ANTES de pegar. **Alvo real no nosso mandato hoje (25/set): #1224 (critical, órfão)**; #1225 (high) a avaliar.

### H-cf/milvus — backends (fora do nosso uso direto; baixa prio p/ nós)

| # | Issue | Nota |
| --- | --- | --- |
| #1236 | cloudflare tag-filter teto 50 vizinhos | não usamos CF |
| #1113 | cloudflare/hybrid recusa embeddings externos | não usamos CF |
| #1201/#1112 | Milvus parity + CI | não usamos Milvus |
| #1117 | SSE auth: api\_key em query → ticket/cookie | segurança web layer |

### H-feat — features post-v11 (backlog do Henry; avaliar valor p/ nós)

| # | Issue | Cruza com | Nota |
| --- | --- | --- | --- |
| #1103 | LLM summarization de memórias | D-adjacente | pode informar C/D |
| #1099 | layered embedding cache (LRU + content-addr) | perf | 🟡 PARCIAL (ver H-resgate 28/set) — cache existe no sqlite_vec mas dict sem bound + chave hash() instável; fix = usar shared.py LRU + content_hash. PR candidato |
| #1097 | métricas Prometheus/OTel | G/obs | 🔴 NÃO implementado (grep zero) — MANTER aberta, sem urgência |
| #1096 | rate-limit por-agente MCP | agent\_id/B3 | 🟡 MADURA — agent_id (#1278/#1297) destravou keying; falta throttle no call_tool. PR em breve (arco multi-agente/hub) |
| #1098 | LLM fallback auto\_capture confiança baixa | harvest | ✅ FECHADA 28/set — superada por classifier.py multi-provider + min_confidence + harvester:379 |
| #1094 | YAML-LD frontmatter + RDF/SHACL (Vault-LD) | research | linked-data |
| #1114 | dashboard concentric ring layout | UI | cosmético |

> **Achado do cruzamento (atualizado 25/set):** #1146 (f-strings não sanitizados) é a versão EM ESCALA do log-injection  
> do #1253 — dominamos o padrão (\_sanitize\_log\_value), MAS agora tem dono ativo (massimiliano1991, PR #1314 + #1306  
> já mergeado). NÃO pegar. Oportunidade órfã viva = **#1224 (critical, cli/lifecycle)**; #1225 (high) a avaliar (guard já existe).

## I. HARVEST DESIGN-EXTRACTION (o gap “sessões ricas, colheita pobre” — RFC 26/set)

RFC: `rfc-harvest-design-extraction.md` (nova, 26/set). **Reabre o GAP DE PRODUTO que a RFC-harvest-provenance deixou aberto:** provenance+tracker resolveram *como* e *se* colhemos, NÃO *o quê* — o harvest ainda descarta **análise de design longa** (não casa frase-gatilho) e **ignora ToolResults** (`parser.py:32` KIRO\_KIND\_MAP não mapeia ToolResult).

**Contradição resolvida (importante):** o piloto R10 disse “não recolher em massa o JÁ colhido” (6.929 mems, só ~302 cruas) — verdadeiro e ORTOGONAL a isto. Este épico é sobre o conteúdo rico que NUNCA foi colhido (design longo + ToolResults), provado pelo caso #1100 (23 análises + 72 linhas ToolResult → “1 memória”). Não é “sobra” (refuta jimy-r no #1287 para o nosso uso): é o prato principal descartado por limitação estrutural.

| # | Épico | O que é | Esforço | Dif. | Dep. |
| --- | --- | --- | --- | --- | --- |
| **I0** | **instrumento de cobertura** (Henry, #1287) | parser conta o que VIU e DESCARTOU por tipo de bloco. Pré-requisito: “coverage mensurável ANTES de mudar o extractor”. | ✅ MERGED (#1350) | ★★ | — |
| **I0-lang** | **extensão de idioma no Phase 0** (R0.4) | idioma detectado por bloco, split extracted/dropped (heurístico zero-dep). DIAGNÓSTICO por-operador, não gate. | ✅ (PR #1379) | ★★ | I0 |
| **IA** | **discovery multi-layout** | find_sessions acha workspace `{hash}/{uuid}/messages.jsonl` + session_id único + resolve + path guard | ✅ MERGED (#1378, 30/set) | ★★ | — |
| **IB** | **parser SQLite (Crew)** | conversations_v2 read-only + history[] estruturado | ✅ MERGED (#1379, 30/set) | ★★ | — |
| I1 | **ToolResults CLI {kind}** | extrai ToolResults (msg `kind=ToolResults` + bloco `toolResult`) via helper de navegação aninhada, espelha v4 (role assistant, injected por bloco, sem cutoff, verbatim); `thinking` redacted → só contado | 🟢 FORK (78e29b05) | ★★ | IA/IB |
| I2 | **design-extractor** (R2/R3/**R3.1**/R4) | blocos longos → LLM “extraia decisão+porquê+trade-off”; proveniência `harvest:mode:design`. **Honra locale do operador** via config/locale.py (R3.1 v0.4, NÃO gate por fração); reusa HarvestRewriter+NLI cascade #1215. **G0 FEITO** (doc G0-design-extractor-I2.md) | 🔴 | ★★★ | I1, #1379 |
| I3 | **controle de ruído** (R5/R6/R7) | opt-in `MCP_HARVEST_DESIGN_ENABLED`; taxa de adoção contada dia-1; 3º estado dashboard (rodou/conteúdo presente/pipeline não representou — Henry); evolve em vez de duplicar | 🟡 | ★★ | I2 |
| I4 | **server-side no scheduler** (R8) | rodar sobre sinais implícitos, não ação manual (convergência #1287) | 🟡 | ★★ | I2 |

> **DIRECIONAMENTO HENRY (#1287, 26/set) — muda a RFC + é PROMESSA PENDENTE:** ele pediu “write the RFC as you planned, own thread” (NÃO dobrar no #1286). A RFC precisa incorporar antes de virar discussion pública: **I0 Phase 0 (instrumento de cobertura primeiro)**, separar **coverage de yield** (nosso 23→1 é número de COBERTURA, não yield; ≠ do <5%/0-18 que são yield real), **3º estado do dashboard**, **alternativas mais baratas** (melhor trigger-set OU parsear tool-results podem bastar antes de LLM), migração/compat, escopo do 1º PR (os “usual four”). Só depois: abrir discussion própria pingando @doobidoo (cumpre a promessa).  
> **GATE (§4 da RFC, disciplina R10):** pilotar contra 5-10 sessões densas (#1100, #1318, auto-supersede 26/set), medir cobertura recuperada vs. ruído. **NÃO confundir com #1103** (VijaySreekar): #1103 = summarization RETRIEVAL-time (o que SAI); grupo I = extração HARVEST-time (o que ENTRA). Opostas, complementares.

```scss
mcp-memory-service (fork = linha viva · v11.14.0+7 · 26/set)

  ⚡ ORDEM DE ATAQUE (o que fazer, nesta ordem):
     1️⃣  H1 #1225   — bug high órfão (store sem embedding row). #1224 FECHADO.
     2️⃣  D3          — query-intent PT/EN. Quick win, melhora NOSSA busca.
     3️⃣  Arco rating — DESIGN primeiro (Discussion #1312, input novo do #1317/#1320). Não codar ainda.
     4️⃣  D1 + D2     — quick wins de disco (−60 a −80MB no banco de 543MB).
     5️⃣  C (trilogia)— bloco grande, Henry validou. Multi-PR, planejar.
     6️⃣  G1 + arquit.— adoção (kiro-hooks) → D5/D6/D7.
│
├─ A. ✅ MERGED — tudo drenado, fila nossa VAZIA
│     #1243 #1250 #1252 #1265 #1288 #1278/#1297 · +consolidation #1302/#1317/#1320 (26/set)
│     +27/set: #1348 (versioned/superseded) · #1350 (harvest coverage instrument I0)
│     +28/set: #1349 (quality-split) · #1365 (health off-lock) · #1366 (parser Kiro v4) · #1367 (embedding cache LRU)
│     +29-30/set: #1373 (backfill supersession) · #1378 (harvest discovery+id+resolve workspace) · #1368 (retention ontology — fecha ARCO 3)
│     ✅ #1379 (SQLite+idioma) MERGEADO (9079737b, 30/set 13:32) — ARCO 1: ambos PRs no upstream
│
├─ B. ✅ ESGOTADA — B1/B2/B3 todos absorvidos pelo upstream (nada a fazer)
│
├─ C. TRILOGIA RFC-MM  🔴 o maior bloco — ✅ Henry VALIDOU (#1286), pode codar  →  passo 5️⃣
│   ├─ C1 fact-extraction  🔴★★★
│   ├─ C2 gap-detection    🔴★★★
│   ├─ C3 feedback-loop    🔴★★★
│   └─ C4 anti-halluc §6   🟡★★
│
├─ D. MNEMOSYNE (9 RFCs — trazer da ferramenta do Hermes)
│   ├─ quick wins:  D3 query-intent 🟢 →2️⃣  ·  D1 quantization 🟡 →4️⃣  ·  D2 hygiene 🟡 →4️⃣
│   ├─ médios:      D4 ranking 🟡  ·  D9 importers 🟡 ←(par do grupo G)
│   └─ arquiteturais: D5 working-mem 🔴 →6️⃣ · D6 persona 🔴 →6️⃣ · D7 delta-sync 🔴 (RFC #1345 v0.3, §8 invariantes) →6️⃣ · D8 multimodal 🔴
│
├─ 🧩 ARCO RATING (nosso, EM WORK) — DESIGN antes de código  →  passo 3️⃣
│   ├─ #1312 quality-model → PR #1349 ✅ MERGEADO (28/set, upstream 97e699e0) — arco central ENTREGUE
│   ├─ fad44c3b design (gargalo PROVIDER_CODES) · f4114d8b ranking composto
│   └─ F1/F3/F4/F5/F6 abertos (design/config) · F2 já resolvido upstream
│
├─ E. SKILL AUTO-GEN (E1/E2/E3 — cruza skill-curator-mcp)  🟡
│
├─ F. ✅ ESGOTADO (F5 feito, F6 resolvido, F1/F2/F4 cortados, F3→G)
│
├─ G. CLIENT ADAPTERS ("traga sua memória")  →  passo 6️⃣
│   ├─ G1 kiro-hooks 🟡 (espelha claude-hooks/ · NOSSO uso)  ·  G2 hermes 🔴 (issue #1095)
│   └─ G3 openclaw 🟡  ·  G4 cursor/continue/windsurf/zed 🟡
│
├─ H. ISSUES ÓRFÃS UPSTREAM (bugs sem dono — contribuição direta)
│   ├─ H1 #1225 store sem embedding row 🔴high 🟡★★★ (OPEN · guard já existe, avaliar valor) ⭐ ALVO 1️⃣
│   ├─ H5 #1106 API/dashboard store     🟡 (OPEN · web layer, fora mandato)
│   └─ ~~H2 #1224 (CLOSED)~~ · ~~H3 #1216 (CLOSED)~~ · ~~H4 #1146 (dono: massimiliano1991)~~ · ~~H6 #1102 (CLOSED)~~
│
├─ I. HARVEST DESIGN-EXTRACTION  🟡 — "sessões ricas, colheita pobre" (RFC #1346; RFC fork v0.4 idioma=locale)
│   │  harvest descartava sessões inteiras (formato) + análise longa + ToolResults
│   ├─ I0 instrumento cobertura      ✅ MERGED (#1350) — conta seen/extracted/dropped per-block kind
│   │   └─ I0-lang extensão idioma   ✅ (PR #1379, R0.4: idioma/bloco split extracted/dropped — MEDIÇÃO)
│   ├─ IA discovery multi-layout     ✅ MERGED (#1378, 30/set) — find_sessions acha workspace + id + resolve + guard
│   ├─ IB parser SQLite (Crew)       🟢 APPROVED (#1379, conversations_v2 read-only + history[]) ← aguarda merge Henry
│   ├─ I1 ToolResults CLI {kind}         🟢 FORK (78e29b05) — extrai ToolResults msg+bloco; thinking redacted=só contado
│   ├─ I2 design-extractor (LLM)     🔴★★★ G0 FEITO (doc G0-design-extractor-I2.md) — caminho alt ao PatternExtractor p/ blocos longos; reusa HarvestRewriter+locale(#1382)+NLI cascade(#1215); honra locale (R3.1 v0.4)
│   ├─ I3 controle de ruído          🟡★★  (opt-in MCP_HARVEST_DESIGN_ENABLED + yield dia-1 + 3º estado dashboard)
│   └─ I4 server-side no scheduler   🟡★★
│   ⚠️ GATE: #1379 mergear → rodar Phase 0 (números por-tipo/locale) → alternativas baratas (R2.1) antes do LLM → G3
│   📄 RFC nova: rfc-harvest-source-identity v0.1 (camada "qual agente/encarnação produziu a sessão")
│

```

## Extremos (para priorizar)

*   **MAIS FÁCIL / menos passos:** D3 (query-intent), H1 #1225 (avaliar valor). 🟢 ★ — 1 PR. (#1224 fechado.) (B/F esgotados.)
*   **MAIS DIFÍCIL / mais passos:** D7 delta-sync (multi-agente + cripto, 3+ PR, ★★★) e a Trilogia RFC-MM C1-C3 (migrations+background+tools, ✅ Henry já validou no #1286). 🔴 ★★★.
*   **MAIOR VALOR/ESFORÇO (quick wins de impacto):** D1 quantization (−61 a −79MB de disco), D2 hygiene (−24 a −73MB FTS). Atacam o banco de 466MB.
*   **MAIOR VALOR ESTRATÉGICO:** D5 working-memory + D6 persona (portabilidade da identidade Zero/T’Pol entre harness) + D7 delta-sync (malha de memória da tripulação).

## Contagem total

**~30 épicos abertos:** A (todos mergeados) + 1 fila curta (B1) + 4 trilogia (C, validada) + 9 Mnemosyne (D) + 3 skill-gen (E)

*   F esgotado (F3→G) + 4 client-adapters (G) + 2-3 issues órfãs upstream vivas (H2/#1224 + H1/#1225 a avaliar + H5; #1216/#1102 fechados, #1146 com dono). Menos recorrentes/discussões/backends fora de uso.

## Sequência recomendada — detalhamento (visão rápida = “ORDEM DE ATAQUE” na árvore acima; atualizada 26/set)

1. H-bugs órfãos primeiro (NOVO) — bugs do Henry sem dono são contribuição direta de alto valor,não competem na fila de feature e constroem confiança. Ordem: H2 #1224 (critical, fix contido — PR #1229 fechado 25/set, voltou a ser órfão = TOPO)→ H1 #1225 (high, recall silencioso, ainda órfão). H4 #1146 agora tem dono ativo (massimiliano1991, PR #1314) — NÃO pegar.
2. F (higiene) — ✅ ESGOTADO (F5 feito, F6 resolvido, F1/F2/F4 cortados, F3→G). Não é mais passo.
3. B (drenar legado) — B2 (#1265) e B3 agent_id (#1278/#1297) JÁ MERGEADOS. Sobra só B1 re-harvest safety (código pronto, task c5a86779; fila nossa vazia → pode abrir).
4. C (Trilogia RFC-MM) — ✅ Henry VALIDOU no #1286 (25/set) (“claims hold”, faltam memory_facts/gaps + migrations pós-012). Deixou de aguardar → pode codar (reescrever sobre v11.14.0, base 2e1978d5). Bloco maior parado, agora destravado.
5. Quick wins D1/D2/D3 — impacto de disco/qualidade em paralelo.
6. G (client adapters) + D9 — adoção; G1 kiro-hooks primeiro; G2 vincula issue #1095.
7. Arquiteturais D5/D6/D7 + G2 hermes — base estável, multi-PR.

Racional: bugs órfãos (H) e F não travam a fila de review; B fecha o que já está pago (código pronto);  
C precisa de groundwork. Atacar bug crítico/high do Henry ANTES de empurrar mais features = leitura correta  
de prioridade do maintainer (ele abriu #1224/#1225 como critical/high e ninguém pegou).