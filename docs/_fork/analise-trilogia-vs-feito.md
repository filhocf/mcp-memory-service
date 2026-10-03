# Análise — Feedback/Trilogia: o que temos vs o que o Henry acordou vs o que fiz hoje

> Doc de planejamento (03/out). Objetivo: embasar a decisão ANTES de responder a #1286 ou abrir PR.
> Erro que originou esta doc: implementei feedback hoje SEM saber que já havia protótipo completo (2e1978d5). Falta de doc que cruze "feito ↔ main ↔ acordo upstream" → retrabalho.

## As 3 fontes (dados verificados)

### Fonte A — O que o Henry ACORDOU na discussion #1286 (aberta, autor filhocf)
- Trilogia de **3 jobs de scheduler, background, periódicos (6h), opt-in via env**:
  1. `fact_extraction` → migration **013**, tool `memory_facts`
  2. `gap_detection` → migration **014**, tool `memory_gaps`
  3. `feedback_recalculation` → migration **015**
- **3 PRs separados** (1 job + 1 migration + 1 changelog.d cada), revisados em sequência.
- Cada PR precisa de **doc do payload das window-tools** (memory_facts/memory_gaps: shape + provenance).
- Henry CONFIRMOU os claims contra v11.12.0 e deu direção: "scope is right". Pediu: migrations 013/014/015 nessa ordem (não colidir); gating por env; usar scheduler existente.
- Correção pendente que ele pediu: link Codeberg #121 (não GitHub PR #121).

### Fonte B — O protótipo que JÁ EXISTE (commit 2e1978d5, tag backup/main-sirdata-20260915_175233)
`feat: RFC-MM-01/02/03 — gap-detection, fact-extraction, feedback-loop` (15/set). Contém:
- `extraction/facts.py` (370L), `feedback/tracker.py` (372L)
- `server/handlers/facts.py` (61L), `gaps.py` (227L)
- migrations **013_add_memory_gaps / 014_add_facts_extracted / 015_add_feedback_signals**
- 153L no scheduler.py (os 3 jobs), tools/registry.py (+70L), routing.py
- TESTES: test_fact_extraction (494L) + test_feedback_loop (547L) + test_gap_detection (388L) = **1429L**
- **NÃO está no main atual** — ficou só no tag de backup. Sumiu em algum merge/reset.
- ALINHA com o acordo do Henry (jobs de scheduler, migrations 013/014/015). É O FORMATO CERTO.

### Fonte C — O que EU fiz HOJE (no main, commitado, pushado)
- D2 feedback NEGATIVO SÍNCRONO (belief.py derive_confidence_with_feedback): rating -1 na obs-fonte → contradição na hora da derivação. NÃO é job de 6h. Opt-in MCP_BELIEF_USE_FEEDBACK. E2E -47,8%.
- L1 telemetria usage_events (migration 014 minha — COLIDE com 014_add_facts_extracted do protótipo!) + get_usage_metrics.
- L2 injeção memory_context (tool, por tema) — NÃO está na trilogia do Henry.

## Os caminhos possíveis

### Caminho 1 — Resgatar o protótipo 2e1978d5 e seguir o acordo do Henry
- **Prós:** 1429L de teste já escritas; formato EXATO que o Henry acordou (3 jobs/migrations 013/014/015); é o trabalho que "sumiu" — recuperá-lo honra o já-feito. PRs saem alinhados → review rápido.
- **Contras:** o protótipo é de 15/set — pode ter bitrot (API mudou? merges desde então). Precisa rebase/validação contra o main atual. Meu trabalho de hoje (síncrono) seria descartado OU reconciliado.
- **Esforço:** médio — resgatar, rebasar, rodar os 1429L de teste, consertar o que quebrou.

### Caminho 2 — Seguir com o que fiz hoje (síncrono) e propor como alternativa
- **Prós:** está no main, provado, E2E hoje. Zero resgate.
- **Contras:** DIVERGE do acordo (síncrono ≠ job 6h; feedback de belief ≠ feedback_recalculation da trilogia). Henry provavelmente pede reformatação. Telemetria/injeção não estão no acordo — viram conversa à parte. Ignora 1429L de teste já prontas. É re-trabalho sobre re-trabalho.
- **Esforço:** baixo agora, ALTO depois (reformatar no modelo dele).

### Caminho 3 — Híbrido: resgatar o protótipo como base + aproveitar o que fiz hoje onde encaixa
- Resgatar 2e1978d5 (formato Henry) como a trilogia oficial dos PRs.
- Meu feedback síncrono de hoje: avaliar se vira um REFINAMENTO do feedback_recalculation (sinal negativo imediato além do job 6h) ou se descarta.
- Telemetria usage_events + injeção memory_context: peças ADJACENTES — propor ao Henry SEPARADAMENTE (não são a trilogia), ou manter fork-only. A telemetria até se conecta ao gap_detection (low-confidence retrieval = gap = evento).
- **Prós:** honra o acordo E o trabalho de hoje onde fizer sentido; nada se perde.
- **Contras:** mais análise de reconciliação (3 fontes de código a casar).

## Recomendação preliminar (a validar com o Claudio)
**Caminho 3 (híbrido), começando por resgatar e validar o 2e1978d5.** Porque:
1. O protótipo é o formato que o Henry JÁ aprovou → PRs alinhados, sem retrabalho de review.
2. Tem 1429L de teste → não jogar fora.
3. Meu trabalho de hoje não é perda total: a telemetria é peça nova útil (conecta com gap_detection), e o feedback síncrono pode refinar o job. Mas o CORE da trilogia é o protótipo, não o que fiz hoje.

## Pendência de PROCESSO (a causa raiz)
Falta no ESTADO.md uma coluna/seção "trabalho local vs acordo upstream vs já-implementado-em-backup". Sem isso, reimplementei algo que existia. AÇÃO: ao fechar esta análise, registrar no ESTADO o cruzamento trilogia (#1286) ↔ protótipo 2e1978d5 ↔ o que está no main, pra isso não repetir.

## Decisões abertas (para o Claudio)
1. Caminho 1, 2 ou 3?
2. Se 3: meu feedback síncrono de hoje — refina o job ou descarta?
3. Telemetria + injeção: propor ao Henry (separado da trilogia) ou fork-only?
4. A migration 014 de hoje (usage_events) COLIDE com 014_add_facts_extracted do protótipo — renumerar qual?
