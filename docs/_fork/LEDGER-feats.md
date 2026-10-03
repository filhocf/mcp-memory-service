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
| D2 feedback negativo síncrono (belief) | learning-loop | IMPL-FORK | main @dc452953 | — (candidato) | rfc-learning-loop / rfc-mm-01 | ✅ sim | rating −1→belief cai. E2E −47,8%. Opt-in MCP_BELIEF_USE_FEEDBACK. DIVERGE do design Henry (síncrono ≠ job 6h). |
| L1 telemetria proveito (usage_events) | learning-loop | IMPL-FORK | main @cc412cfe | — | — | ✅ sim | usage_events + get_usage_metrics. migration 014. Peça adjacente (não está na trilogia #1286). |
| L2 injeção proativa (memory_context) | learning-loop | IMPL-FORK | main @f752dd13 | — | — | ✅ sim | tool por tema. Peça adjacente (não está na trilogia #1286). |
| **Trilogia fact/gap/feedback (jobs scheduler)** | learning-loop | **ÓRFÃO — A DECIDIR** | tag `backup/main-sirdata-20260915_175233` @2e1978d5 | discussion #1286 (Henry validou direção) | rfc-mm-01/02/03 | ❌ **NÃO** | 1429L teste, migrations 013/014/015, 3 jobs. 92/93 testes passam vs main atual (vivo). FORMATO que o Henry acordou. Decidir: reland sobre v11.15 vs a reimpl de hoje cobre. |
| NER PT-BR/EN DomainExtractors | ingestão | VERIFICAR | tag `backup/main-sirdata-20260915` @4358c29b | — | rfc-multi-store-domain-ner | ✅ provável (extraction/ner_patterns no main) | confirmar se é o mesmo do main |
| harvest Kiro IDE (messages.jsonl) | ingestão | VERIFICAR | tag `backup/main-sirdata-20260915` @d017a1d4 | — | rfc-harvest-kiro-sessions | ? | verificar vs main |
| harvest-quality pipeline v2 + distill | ingestão | ÓRFÃO — A DECIDIR | `archive/2026-06-20/feat/harvest-quality-fix` (28 únicos) | — | rfc-pipeline-harvest-quality | parcial? | distill_check job 6h, pagination, dedup. Verificar o que landou. |
| rewriter TYPE: leak fix | rating | PR-ABERTO | — | #1418 | — | ✅ sim | aguarda Henry |
| D3 query-intent | backlog | IMPL-FORK (PAUSADA) | não-commitado (WI 9fa7e0ef) | — | rfc-query-intent | ❌ não-commitado | valor marginal; decidir retomar/arquivar |

## Legenda salvo-na-main?
- ✅ sim = o código está na linha viva (main), não só em backup.
- ❌ não = só existe em tag/branch de backup → RISCO de perda, precisa veredito.
- ? / parcial = a verificar (próxima varredura).
