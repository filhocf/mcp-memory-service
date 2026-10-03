# ÓRFÃOS — livro-caixa do detector (fork mcp-memory-service)

> Append-only. Prova que nenhum commit fork-only sumiu sem decisão.
> Detector: `for ref in $(git for-each-ref --format='%(refname:short)' refs/tags refs/heads | grep -iE "backup|archive|safety"); do n=$(git rev-list --count "$ref" --not main upstream/main); echo "$n|$ref"; done | sort -t'|' -rn`
> Veredito por ref: RELAND (voltar à main) · SUPERSEDED (upstream/reimpl cobre) · DESCARTAR (0 únicos, lixo).

## Varredura 2026-10-03 (main 145 à frente do upstream, pós-sync v11.15.0)

### 🔴 ÓRFÃOS COM TRABALHO ÚNICO (precisam veredito antes de deletar)
| #únicos | ref | conteúdo | veredito | data |
|---------|-----|----------|----------|------|
| 36 | `backup/main-sirdata-20260915_175233` | trilogia 2e1978d5 (fact/gap/feedback) + NER 4358c29b + harvest-kiro d017a1d4 | **A DECIDIR** (trilogia no ledger) | — |
| 28 | `archive/2026-06-20/feat/harvest-quality-fix` | harvest pipeline v2, distill job 6h, pagination, dedup, rfc1047 §3/§7 | **A DECIDIR** | — |
| 3 | `archive/2026-06-20/fork-patches` | ? | A VERIFICAR | — |
| 3 | `archive/2026-06-20/fix/harvest-openclaw-trajectories` | harvest openclaw | A VERIFICAR | — |
| 3 | `archive/2026-06-20/feat/composite-scoring` | NER multi-locale #54, graph agg #56/#61, composite scoring #55 | A VERIFICAR (parece landado) | — |
| 2 | `archive/2026-06-20/rebase/rfc1008-temporal-edges` | temporal edges | A VERIFICAR | — |
| 2 | `archive/2026-06-20/rebase/rfc1008-fact-mutability` | fact mutability | A VERIFICAR | — |
| 2 | `archive/2026-06-20/feat/harvest-kiro-parser` | Kiro CLI parser | A VERIFICAR (vs #972 landado?) | — |
| 1 | `backup/design-quality-model-pre-v1114-20260925` | design quality-model | A VERIFICAR | — |
| 1 | `archive/2026-06-20/pr/composite-scoring-v2` | composite scoring v2 | A VERIFICAR | — |
| 1 | `archive/2026-06-20/fix/harvest-openclaw-noise` | openclaw noise | A VERIFICAR | — |
| 1 | `archive/2026-06-20/feat/openclaw-harvest-v2` | openclaw v2 | A VERIFICAR | — |
| 1 | `archive/2026-06-20/feat/kiro-cli-harvest-parser` | kiro parser | A VERIFICAR | — |
| 1 | `archive/2026-06-20/docs/multilingual-embeddings` | docs #21 | A VERIFICAR | — |

### ⚪ 0 ÚNICOS — DESCARTÁVEIS (100% contidos em main/upstream, snapshots de merge)
`backup/sirdata-pre-sync-v11150` · `backup/sirdata-pre-sync-20261003` · `backup/sirdata-pre-sync-20261002` · `backup/service-sirdata-20260915_175233` · `backup/main-pre-v1114-sync-20260925-0659` · `backup/main-pre-v11140merge-20260925` · `backup/main-pre-v11140-10commits-20260928_201649` · `backup/main-pre-v11.13-sync-0919` · `backup/main-pre-sync-v1113-0920` · `backup/main-pre-sync-24set-1648` · `backup/main-pre-merge-20260930` · `backup/main-pre-merge-20260927` · `backup/main-pre-fase2-20260923` · `backup/main-pre-consolidation-20260926` · `backup/main-pre-b2b3-0918` · `backup/main-pre-1326merge-20260926` · `archive/github-workflows-pre-codeberg` · `archive/2026-06-20/rebase/rfc1-s6-anti-hallucination` · `archive/2026-06-20/rebase/rfc1-s2-belief-store`
→ **AÇÃO (pendente OK do Claudio):** deletar após re-confirmar 0 no detector. Decisão: DESCARTAR.

## Próxima varredura: a cada sync do upstream (Ritual 1) + mensal.

## Inventário COMPLETO 2026-10-03 (varredura total: branches+tags+dangling+worktrees+remotas)
Fork 100% sincronizado local (22 branches). 29 refs órfãos investigados UM A UM com evidência git grep.

### ÓRFÃOS-REAIS (3):
| ref | veredito | ação |
|-----|----------|------|
| validacao/prototipo-trilogia-2e1978d5 | RELAND (trilogia, já ledgerada) | decidir reintegração sobre v11.15 |
| doc/rfc-delta-sync-invariants | **PORTADO 3/out** (§8 invariantes #1345 → main) | branch deletável |
| docs/audit-memory-service | INCERTO baixo valor (macro-map histórico 23/set) | mover p/ _fork ou deletar |

### LIXO confirmado (26 refs — conteúdo provado no main via grep):
- 14 branches landed/obsoletas: 4 pr/*, 3 fix/*, feat/quality-model-split, feat/harvest-coverage-instrument, feat/agent-id, design/quality-model, backup/design-quality-model, 3 wip/stash-multistore (multi-store #57 landou SUPERIOR no main).
- NUANCE feat/nli-observability: OBSOLETO — resgatar REVERTERIA melhorias do main (max_achievable_confidence, provenance). Deletar, não resgatar.
- 10 dangling: de00681d(chain 23 bootstrap jul), embedding-cache stashes, cascading-fallback #873, insight-cards, temporal-decay #119, mem0-adapter, Kiro-JSONL — TODOS relandados.

CONCLUSÃO: único trabalho significativo perdido era a trilogia (resgatada) + delta-sync §8 (portado). NÃO há segundo protótipo escondido. Relatório detalhado: ~/.kiro/tmp/inventario-oculto.md.
