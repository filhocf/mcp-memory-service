# LEDGER de Features — fork mcp-memory-service

> Índice vivo: responde "o que temos / o que foi pensado / o que foi landed". Fonte única.
> Regra (INVARIANTE): nenhuma feat fork-only existe sem uma linha aqui. Mudou estado → atualiza no mesmo passo.
> Espelho em memory-service: tag `mms-ledger` (durabilidade cross-máquina).

## Máquina de estados
```
IDEIA → DESIGN(RFC/discussion) → IMPL-FORK → PR-ABERTO → MERGED
                                      ├────────────→ FORK-ONLY-PERMANENTE
                                      └────────────→ SUPERSEDED-BY-UPSTREAM
```

## Feats

| feat | arco | estado | ref git | PR/issue | RFC | salvo-na-main? | nota |
|------|------|--------|---------|----------|-----|----------------|------|
| ~~D2 feedback negativo síncrono~~ | learning-loop | **REVERTIDO** | revert de dc452953 | — | rfc-mm-01 | ❌ removido | LETRA MORTA: dependia de rating manual que ninguém faz (a própria RFC-MM-01 do Claudio previa isso). Substituído por: terminar RFC-MM-01 (feedback PASSIVO) sobre a telemetria. |
| L1 telemetria proveito (usage_events) | learning-loop | IMPL-FORK | main @cc412cfe | — | — | ✅ sim | usage_events + get_usage_metrics. migration 014. Peça adjacente (não está na trilogia #1286). |
| L2 injeção proativa (memory_context) | learning-loop | IMPL-FORK | main @f752dd13 | — | — | ✅ sim | tool por tema. Peça adjacente (não está na trilogia #1286). |
| **#1304 hybrid self-hosted secondary (http)** | sync/hub | **ATRIBUÍDA A NÓS — EM PROGRESSO** | main | issue #1304 (Henry assignou filhocf 27/set, help-wanted) | rfc-hybrid-http-secondary (R1-R16) | parcial | **CENTRO DO RADAR.** Raiz que destrava delta-sync (#1345). SPEC criada (4 fases EARS). Fase1 (list_content_hashes+endpoint) = PR #1470 ABERTO upstream, CI verde, Greptile 4 corrigidos. Fase2 (RemoteHTTPStorage) = IMPL-FORK main (358b9489, G0-G5 APPROVED). Fase3 (desacoplar CF) + Fase4 (model-match) = specadas, a implementar. Estratégia: commits atômicos na main, vira PR conforme Henry absorve. |
| #1304 Fase 1: list_content_hashes + bulk endpoint | sync/hub | ✅ MERGED #1470 | pr/list-content-hashes @ upstream + main 07398f22 | PR #1470 | rfc-hybrid-http-secondary §4 | ✅ | Gate completo + Greptile 4 achados corrigidos (hybrid vazio, erro→vazio, auth test, info-disclosure). 20 tests. E2E vivo 23680 mems. |
| #1304 Fase 2: RemoteHTTPStorage secondary | sync/hub | ✅ MERGED #1471 | storage/remote_http.py + hybrid.py ramo http + config/storage.py | — | rfc-hybrid-http-secondary §6 | ✅ | Gate G0-G5 tuvok APPROVED (loop P2+warning CF P2+3 P3+doc-sync). 34 tests. MCP_HYBRID_SECONDARY_BACKEND=cloudflare\|http. Vira PR DEPOIS da Fase 1 mergear. ACHADO: espelhar PR→main apagou hook telemetria retrieve (mistake 81a783f9, fix ba4c8146). |
| **Trilogia fact/gap/feedback (jobs scheduler)** | learning-loop | **RESGATADA (branch viva)** | branch `validacao/prototipo-trilogia-2e1978d5` (pushada) | discussion #1286 (Henry validou direção) | rfc-mm-01/02/03 | 🟡 branch (não-main) | 93/93 testes passam vs v11.15. Banco vivo já tem memory_gaps+feedback_signals (tabelas órfãs). PENDENTE p/ PR: doc payload window-tools (Henry), EARS mm-03, changelog.d, resolver colisão 014. |
| NER PT-BR/EN DomainExtractors | ingestão | VERIFICAR | tag `backup/main-sirdata-20260915` @4358c29b | — | rfc-multi-store-domain-ner | ✅ provável (extraction/ner_patterns no main) | confirmar se é o mesmo do main |
| harvest Kiro IDE (messages.jsonl) | ingestão | VERIFICAR | tag `backup/main-sirdata-20260915` @d017a1d4 | — | rfc-harvest-kiro-sessions | ? | verificar vs main |
| harvest-quality pipeline v2 + distill | ingestão | ÓRFÃO — A DECIDIR | `archive/2026-06-20/feat/harvest-quality-fix` (28 únicos) | — | rfc-pipeline-harvest-quality | parcial? | distill_check job 6h, pagination, dedup. Verificar o que landou. |
| rewriter TYPE: leak fix | rating | PR-ABERTO | — | #1418 | — | ✅ sim | aguarda Henry |
| D3 query-intent | backlog | IMPL-FORK (PAUSADA) | não-commitado (WI 9fa7e0ef) | — | rfc-query-intent | ❌ não-commitado | valor marginal; decidir retomar/arquivar |

## Legenda salvo-na-main?
- ✅ sim = o código está na linha viva (main), não só em backup.
- ❌ não = só existe em tag/branch de backup → RISCO de perda, precisa veredito.
- ? / parcial = a verificar (próxima varredura).

## Métrica de assertividade + reaccess (ADR-0005, 4/out)
| feat | arco | estado | ref | nota |
|------|------|--------|-----|------|
| captura returned_hashes (retrieval) | learning-loop | IMPL-FORK | usage_telemetry.py + retrieve.py:242 | sem migration; privacidade ok |
| derive_signals (reaccess/retry_failed) | learning-loop | IMPL-FORK | usage_telemetry.py | deriva de usage_events |
| get_assertiveness_metrics (3 sub-métricas) | learning-loop | IMPL-FORK | usage_telemetry.py | re_query_rate/injection_coverage/lost_context |
| recompute_quality_scores (job RFC-MM-01) | learning-loop | IMPL-FORK (função) | usage_telemetry.py | signed_sigmoid+decay 14d; NEG_WEIGHT 2.5 |
| agent_id na telemetria (retrieve/feedback/injection) | learning-loop | IMPL-FORK | usage_telemetry.py:resolve_telemetry_agent_id + retrieve.py/metadata.py/context_injection.py | 6/out · desbloqueia ADR-0006 (L4). getenv MCP_AGENT_ID null-safe (precedência RFC#1100). derive_signals já particionava. 6 tests (test_agent_id_telemetry.py, REQ-A5 anti-contaminação + A6 empty). Banco vivo prova agent_id=zero. NÃO coberto por #1278/#1297 (esses=autor da memória; este=leitor no usage_event). Fork-only. Persistência ainda dry-run (histórico None 96% até janela 14d). |
| hostname automático no store MCP | enriquecimento | ✅ MERGED #1469 | handlers/memory.py:_resolve_hostname (3 call sites: store_memory + 2× store_session) | 6/out · RFC rfc-mcp-hostname-stamping (EARS 5 req). INCLUDE_HOSTNAME só era lido na Web API; MCP handler não resolvia. Fix: fallback socket.gethostname() quando flag on + sem client_hostname (best-effort). 7 tests. E2E quente: metadata.hostname=DNBSCDC289.741. **PR #1469 upstream (bug, fila à parte da feat). CI verde nos checks críticos (tests-prove-fix, changelog). Branch pr/mcp-hostname-stamping no worktree -dev.** |
| backfill agent_id legado | enriquecimento | FEITO (banco vivo) | UPDATE metadata json_set | 6/out · 22534 memórias NULL → zero (guri==zero, premissa confirmada). kiro(80)/unknown(2) preservados. Backup pré: mcp-db-backups/sqlite_vec-pre-agentid-backfill-20261006_082353.db. Integridade 24306=24306 embeddings. NÃO é código (operação de dados, não vira PR). |
**v1 (feito):** produtor de dados VIVO (retrieval grava returned_hashes; injection grava belief_hashes) + derivação + métricas + função de recálculo, com gate completo + E2E no banco real (reaccess=1, quality pos 1.405 / neg -0.487). 8 testes.
**v2 WIRING (FEITO 5/out manhã a5049863 DNBSCDC289 + REIMPLEMENTADO 5/out noite 14005d3f sirdata — RECONCILIADO 6/out):** scheduler `_schedule_quality_recompute_job` + `_run_quality_recompute` (opt-in `MCP_QUALITY_RECOMPUTE_SCHEDULE`=6h) delega `persist_quality_scores()` (usage_telemetry.py, 118 linhas). Dry-run por default (`MCP_QUALITY_RECOMPUTE_DRY_RUN`=true, ADR-0006: agent_id=None contamina reaccess×retry). Tool `get_assertiveness_metrics` intacta (registry+routing+handler). Gate G0-G5 (tuvok pegou P1 clobber-rating). 2944 passed. FORK-ONLY (aguarda janela N1 + agent_id em retrieve).
**⚠️ DUPLICAÇÃO 5/out:** manhã DNBSCDC289 (a5049863, env `MCP_QUALITY_RECALC_SCHEDULE`) + noite sirdata (14005d3f, env `MCP_QUALITY_RECOMPUTE_SCHEDULE`). Causa: sessão sirdata não rodou ritual de contexto → não viu LEDGER → reimplementou. Reconciliação: adotada versão sirdata (dry-run + ADR-0006) + assertiveness tool da manhã. Env unificada: `RECOMPUTE`. Testes: sirdata `test_quality_recompute.py` substituiu `test_quality_recalc_wiring.py`. Branch sirdata `feat/l4-quality-recompute-dryrun` deletável. Veredito mistake_note: 2ª ocorrência (1ª = trilogia 3/out).

## Estado de contribuição upstream (4/out) — NADA em PR ainda
Tudo fork-only. 0 PRs abertos no doobidoo. Gatilhos p/ virar PR:
- Telemetria + métrica (usage_events, memory_context, assertividade): PR QUANDO a janela de 1 semana provar valor (ADR-0005). Maturar local primeiro (RFC learning-loop).
- Trilogia fact/gap/feedback (branch validacao): 3 PRs QUANDO spec completa (doc payload window-tools #1286 + EARS mm-03 + changelog).
- delta-sync (ADR-0002): PR QUANDO implementado.
- ADRs + docs/_fork/: FORK-ONLY PERMANENTE (nunca viram PR — AGENTS.md).
