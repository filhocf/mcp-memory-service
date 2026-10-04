# RFCs — árvore de arcos (fork mcp-memory-service)

> Mapa de navegação. RFC = *o quê/por quê* (pós-PRD). Decisões de arquitetura = `docs/adr/`.
> Status detalhado por RFC: `_index.md`. Consolidação 4/out (25 docs → ~11 vivos; mapa em
> ~/.kiro/tmp/mapa-rfcs-sobreposicoes.md). Linhagem APRENDIZADO = 1 ideia em 4 gerações, não 4 ideias.

## ARCO APRENDIZADO — mãe: `rfc-learning-loop` (o PORQUÊ, 🟡 parcial)
Linhagem: self-service (mai) → autolearn-autodream (mai/jun) → mm-01/02/03 (jul) → learning-loop (out).
- `rfc-mm-01-feedback-loop` ...... 🟡 L4 feedback PASSIVO · telemetria no código · falta job recálculo · ADR-0003
- `rfc-mm-02-fact-extraction` ..... L2 destilação (absorve o antigo rfc-fact-extraction, superseded)
- `rfc-mm-03-gap-detection` ....... filha indep. (o que FALTA) · 0 EARS, completar
- `rfc-self-service-*` ............ 🟡 geração anterior, absorvida (apêndice A conceitual)
- `rfc-autolearn-autodream` ....... 🟡 memory_distill feito; diagnóstico §1.3 → ADR-0003
- `rfc-server-side-lifecycle` ..... filha indep. (onde roda) · parcial
- `rfc-persona-tier` .............. linkada (identidade ≠ comportamento), NÃO absorvida
- `rfc-skill-auto-generation` ..... linkada, futura (erro→skill)
- `rfc-memory-hygiene` ............ linkada (limpar antes de destilar, R2)
- Decisões: ADR-0003 (input=uso real) · ADR-0004 (injeção única) · ADR-0005 (métrica assertividade, proposta)
- Já no código (3-4/out): usage_events (telemetria) · memory_context (injeção L3)

## ARCO MULTI-AGENTE
- HARVEST — mãe: `rfc-ingestao-multi-agente` · filha: `spec-fase0-kiro-yaml-triagem`
- SYNC — mãe: `rfc-hub-memoria-centralizada` (transporte histórico) · `rfc-delta-sync` (transporte ESCOLHIDO) · **ADR-0002** (delta-sync + aposentar OneDrive)
- PORTABILIDADE — mãe: `rfc-memory-portability` · filha: `rfc-importers`

## ARCO RETRIEVAL-ENGINE (índice leve — peças ortogonais, NÃO fundir)
- `rfc-query-intent` (prioridade baixa) · `rfc-ranking-upgrades` · `rfc-working-memory` (reusa memory_context, ADR-0004) · `rfc-embedding-quantization` (ganho real de disco)

## INFRA DE CÓDIGO
- `rfc-structural-improvements` (🟡 §8/§13 feitos) · `rfc-kiro-headless-llm-provider`

## AVULSOS
- `rfc-multimodal-memory` · `rfc-onboarding-discoverable`

## Decisões abertas (ver docs/adr/)
Nenhuma pendente das 3 contradições — resolvidas em ADR-0002/0003/0004 (4/out).
