# RFC-MM-03: Gap Detection Proativa

## Problema

Quando busca semântica retorna score <0.3, o sinal se perde. Não sabemos o que FALTA
no banco. Ingerimos docs por instinto, não por demanda real.

## Solução

Registrar queries com score baixo como "gaps". Acumular → dashboard de conhecimento
faltante → sugerir o que ingerir prioritariamente.

## Implementação

- Tabela `memory_gaps` (query, max_score, timestamp, agent_id, resolved_at)
- Hook no handler de `memory_search`: se top_score < threshold (0.3), INSERT gap
- Dedup: normalizar query (lowercase, strip stopwords), agrupar similares
- Tool `memory_gaps(action='list'|'resolve'|'stats')`
- Scheduler semanal: consolidar gaps similares, reportar top-10

## Acceptance Criteria

- ≥10 gaps reais detectados em 1 semana de uso normal
- 80%+ são gaps genuínos (query legítima + banco realmente não tem)
- Falso positivo <20% (query mal formulada ou dado existe com outro wording)

## Métricas

| Métrica | Meta |
|---------|------|
| Gaps/semana registrados | ≥10 |
| Taxa de resolução | gap → ingestão → resolved |
| Precisão | gaps genuínos / total >80% |
| Impacto | buscas que falhavam agora retornam >0.5 |

## Dependências

Nenhuma (pode rodar antes de #116).

## Estimativa

2-3 dias implementação + 2 semanas observação.
