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
**v1 (feito):** produtor de dados VIVO (retrieval grava returned_hashes; injection grava belief_hashes) + derivação + métricas + função de recálculo, com gate completo + E2E no banco real (reaccess=1, quality pos 1.405 / neg -0.487). 8 testes.
**v2 (declarado pendente — evita reabrir furo-D3):** WIRING = (a) job de scheduler que chama recompute_quality_scores periodicamente; (b) tool/endpoint get_assertiveness_metrics p/ o agente consultar; (c) clamp [0,1] no quality_score. Hoje as funções existem e derivam, mas nenhum job/tool as chama ainda.
