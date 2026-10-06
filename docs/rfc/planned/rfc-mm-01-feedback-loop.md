> ✅ PARTIALLY IMPLEMENTED: usage_events + usage_telemetry.py materializam o tracking passivo (L4). Falta job de recálculo. Ver ADR-0003. Fonte de verdade: uso real (não commit_session_legacy).

# RFC-MM-01: Feedback Loop Automático (Server-Side, Zero Disciplina)

**Data:** 2026-07-20
**Status:** Draft
**Autor:** Claudio / Kiro

## Problema

17K memórias com quality score médio 0.5 (default). Banco não sabe o que é útil.
Bootstrap profile poluído. Ratings manuais falham (agente não lembra de chamar).
Hooks falham pelo mesmo motivo — dependem de disciplina que não existe.

## Princípio

**Observar comportamento, não pedir declaração.** O server já vê o padrão de uso.
Assim como analytics web não pede "essa página foi útil?" — infere do comportamento.

## Solução: Tracking Passivo Server-Side

O server rastreia correlação entre buscas e ações subsequentes do mesmo agent_id.

### Sinais positivos (memória útil):

| Padrão observado | Sinal | Peso |
|-----------------|-------|------|
| `memory_search` retorna hash A → próximo `memory_store` tem conteúdo similar a A | Referenciou | +1.0 |
| `memory_search` retorna hash A → próximo request cita hash A (ex: `memory_graph(hash=A)`) | Drill-down | +0.8 |
| Hash A retornado em múltiplas buscas diferentes (reacesso) | Recorrente | +0.5 |

### Sinais negativos (memória inútil):

| Padrão observado | Sinal | Peso |
|-----------------|-------|------|
| `memory_search` retorna [A..J] → próximo `memory_search` é query refinada (retry) | Retry = falhou | -0.5 para todos |
| Hash A retornado 10x mas NUNCA referenciado em nenhum call subsequente | Sempre ignorado | -0.3 (acumula) |

### Neutro (sem sinal):

- Nenhuma interação em 5min após busca → ignora (sessão pode ter acabado)

## Implementação

### 1. Session buffer (leve, in-memory)

```python
# Por agent_id, janela deslizante de 5min
class SearchSession:
    agent_id: str
    timestamp: datetime
    returned_hashes: list[str]  # hashes retornados no último search
    expired: bool = False       # True após 5min sem atividade
```

### 2. Correlação passiva

Em CADA request que chega ao server:
- Se há SearchSession ativa para esse agent_id:
  - Comparar conteúdo/hashes do request atual com `returned_hashes`
  - Se match → signal positivo para hashes matched
  - Se é outro `memory_search` (retry) → signal negativo para todos

### 3. Tabela de signals

```sql
CREATE TABLE IF NOT EXISTS feedback_signals (
    content_hash TEXT NOT NULL,
    signal_type TEXT NOT NULL,  -- 'referenced', 'drilldown', 'retry_failed', 'always_ignored'
    weight REAL NOT NULL,
    agent_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### 4. Scheduler: Quality Score Recalculation

Job diário (ou a cada 6h):
```
quality_score = base + signed_sigmoid(Σ pos − 2.5×Σ neg) × decay(age, half_life=14d)   # signed_sigmoid=2σ(x)−1 ∈(−1,1); 2.5 compensa o +1 reaccess mecânico do burst de re-query (implementado 4/out, ADR-0005)
```

Onde `decay(age)` = signals recentes pesam mais que antigos (half-life 14 dias).

### 5. Impacto no retrieval

- `memory_search` com `scoring='composite'`: quality_score entra no ranking
- `get_bootstrap_profile`: filtra memórias com quality < 0.3
- `memory_consolidate`: candidates para archive = quality < 0.2 + stale > 30d

## Acceptance Criteria

- [ ] Após 2 semanas: quality score médio sobe de 0.5 → 0.65+ (conservador)
- [ ] Distribuição bimodal emerge (úteis >0.7, noise <0.3)
- [ ] Bootstrap top-10: ≥8 entries acionáveis (sem session/checkpoint noise)
- [ ] Zero dependência de disciplina do agente (não precisa chamar nada)
- [ ] Overhead: <5ms por request (in-memory buffer, não disk I/O no hot path)

## Métricas de Validação

| Métrica | Antes | Meta |
|---------|-------|------|
| Quality score médio | 0.5 (flat) | 0.65+ |
| Bootstrap noise | ~30% lixo | <10% |
| Memórias com signal ≠0 | 7 (0.04%) | >500 (3%+) |
| Overhead por request | 0ms | <5ms |

## Riscos

- **Falso positivo**: memória retornada e agente faz store similar por coincidência
  - Mitigação: threshold de similaridade alto (>0.85) para considerar "referenciou"
- **Session tracking**: precisa de agent_id consistente (já temos via MCP)
  - Mitigação: se agent_id ausente, não trackear (graceful degradation)

## Dependências

Nenhuma. Pode rodar independente de #116.

## Referências upstream GH (atualizado 6/out)

- **#1286** (discussion, OPEN) — RFC trilogia fact-extraction / gap-detection / feedback-loop. Henry validou a direção. A RFC-MM-01 É a camada de feedback da trilogia.
- **#1312** (discussion, OPEN) — Design: separar computed quality_score de human rating. Implementado via modelo split (#1349 MERGED: `computed_quality` + `user_rating` → `effective_quality`).
- **#1100** (issue, CLOSED) / **#1278** (PR, MERGED) / **#1297** (PR, MERGED) — agent_id: fases 1-2. O agent_id na telemetria (retrieve/feedback/injection `usage_events`) é o elo faltante que esta RFC precisa para separar buckets por agente (ADR-0006: sem ele, reaccess×retry contamina cross-sessão).
- **ADR-0006** (fork, Accepted) — passive quality recompute ships dormant, persistence blocked until agent_id reaches retrieve(). O resultado direto do shadow dry-run desta RFC.

## Estimativa

3-4 dias implementação + 2 semanas observação de convergência.
