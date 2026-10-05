# RFC-MM-03: Gap Detection Proativa

**Data:** 2026-07-20 · **Revisada:** 2026-10-05 (EARS + reconciliação com código da trilogia)
**Status:** Draft (implementado na branch `validacao/prototipo-trilogia-2e1978d5`, pendente de reconciliação de migration para PR)
**Autor:** Claudio / Zero · **Arco:** learning-loop (filha independente — o que FALTA no banco)

> Classificação por EVIDÊNCIA de código (AGENTS): a feature JÁ EXISTE na branch da trilogia
> (`handlers/gaps.py`, migration `memory_gaps`, 23 testes em `test_gap_detection.py`). Esta spec
> documenta o que foi implementado + crava os EARS que faltavam, para virar PR limpo.

## 1. Problema (a dor, do ponto de vista do cliente/agente)

Quando eu (agente) busco algo no banco e a melhor correspondência vem com score baixo
(`< 0.3`), isso é um sinal forte — **o conhecimento que eu precisava não está lá, ou está
com wording que não casa** — e hoje esse sinal **se perde**. Ingiro documentos por instinto,
não por demanda real medida. O resultado: continuo buscando o que o banco não tem, sessão
após sessão, sem que o sistema aprenda onde estão seus próprios buracos.

Gap-detection fecha isso: registra as buscas que falharam, agrupa as recorrentes, e me dá um
mapa priorizado do que ingerir. É o L4 do learning-loop na direção do **negative signal barato**
(a RFC learning-loop §11 prioriza sinal negativo: contradição e falha de busca são fortes e baratos).

## 2. Princípio

**Observar a falha, não pedir declaração.** O serviço já vê o top-score de cada busca. Se o
melhor resultado é fraco, isso é um gap — registre, sem depender de o agente lembrar de reportar.

## 3. Solução (o que o código faz)

- Tabela `memory_gaps` (query, normalized_query, max_score, agent_id, created_at, resolved_at).
- Hook no handler de `memory_search`: se `top_score < threshold` (default 0.3), chama `record_gap`.
- Normalização de query (lowercase, strip stopwords EN+PT-BR, remove tokens curtos) para agrupar
  variações da mesma busca.
- Dedup por `normalized_query` numa janela de 24h: mesma busca falha de novo → atualiza
  `max_score` (mantém o maior, mais perto do threshold), não cria linha nova.
- Tool `memory_gaps` com ações `list` / `resolve` / `stats`.
- Best-effort: falha ao registrar gap NUNCA quebra a busca (try/except não-fatal).

## 4. Requisitos (EARS)

- **M3.1** — WHEN `memory_search` retorna com `top_score < MCP_GAP_THRESHOLD` (default 0.3),
  THE serviço SHALL registrar um gap com a query, sua forma normalizada, o `max_score` e o `agent_id`.
- **M3.2** — THE normalização SHALL rebaixar para minúsculas, remover stopwords (EN+PT-BR) e
  tokens com menos de 3 caracteres, produzindo uma forma canônica estável para agrupamento.
- **M3.3** — WHEN uma query cuja forma normalizada já tem um gap NÃO-resolvido criado nas últimas
  24h chega, THE serviço SHALL atualizar o `max_score` desse gap (mantendo o maior) em vez de
  inserir um novo registro.
- **M3.4** — WHERE a forma normalizada da query é vazia (só stopwords/tokens curtos), THE serviço
  SHALL ignorar o registro (não cria gap).
- **M3.5** — WHEN `memory_gaps(action="list")` é chamado, THE serviço SHALL retornar os gaps
  NÃO-resolvidos ordenados por recência, respeitando um `limit`.
- **M3.6** — WHEN `memory_gaps(action="resolve")` é chamado com `gap_id` OU `normalized_query`,
  THE serviço SHALL marcar o(s) gap(s) correspondente(s) como resolvido(s) (`resolved_at`).
- **M3.7** — WHEN `memory_gaps(action="stats")` é chamado, THE serviço SHALL retornar contagens
  agregadas (total, resolvidos, não-resolvidos) para medir a saúde do acervo.
- **M3.8** — IF o registro de um gap falhar por qualquer motivo, THEN THE serviço SHALL logar o
  erro e seguir, sem afetar o resultado da busca (não-fatal).
- **M3.9** — WHERE a tabela `memory_gaps` não existe, THE migration SHALL criá-la de forma
  idempotente (CREATE IF NOT EXISTS) com índices em normalized_query, resolved_at e created_at.

## 5. Acceptance Criteria

- [ ] ≥10 gaps reais detectados em 1 semana de uso normal (medir no banco vivo).
- [ ] ≥80% são gaps genuínos (query legítima + banco realmente não tem), falso-positivo <20%.
- [ ] Dedup funciona: a mesma busca falhada 5× em 1h gera 1 gap (não 5).
- [ ] `list`/`resolve`/`stats` operam conforme M3.5-M3.7.
- [ ] Overhead no hot-path da busca: desprezível (INSERT best-effort fora do caminho de resposta).
- [ ] Zero quebra de busca quando o registro falha (M3.8).

## 6. Estado de implementação (branch trilogia) — CORROBORADO via git grep 05/out

| Peça | Arquivo (branch validacao) | Estado |
|------|----------------------------|--------|
| Tabela + índices | `storage/migrations/013_add_memory_gaps.sql` | ✅ implementado (⚠️ renumerar) |
| record_gap + normalize + dedup 24h | `server/handlers/gaps.py` (L51-108) | ✅ lógica + 23 testes |
| tool list/resolve/stats | `server/handlers/gaps.py` (L110-...) | ✅ lógica |
| **hook no memory_search (M3.1)** | — | ❌ **NÃO WIRED** — `record_gap` tem 0 chamadas fora do próprio gaps.py; nada registra gap no fluxo real de busca |
| **tool memory_gaps no registry/routing** | — | ❌ **NÃO EXPOSTA** — ausente de tools/registry.py e routing.py |

**Achado (corroborado):** o núcleo (tabela+lógica+testes de unidade) está pronto, mas a feature está
**DESPLUGADA** — o mesmo padrão das peças órfãs do L4. Testes de unidade passam porque chamam
`record_gap`/`handle_memory_gaps` direto; em produção, nada chama. Para a feature VIVER falta o
WIRING (ver §7).

## 7. Pendências para virar PR (ordem corrigida pós-corroboração)

1. **WIRING (o que falta de verdade):** (a) chamar `record_gap` no handler de `memory_search`
   quando `top_score < threshold` (M3.1) — hoje 0 callers; (b) expor a tool `memory_gaps` no
   registry + routing (M3.5-M3.7). Sem isso a feature é letra-morta (igual ao L4 pré-wiring).
2. **Colisão de migration:** renumerar `013_add_memory_gaps` (colide com upstream) para o próximo
   livre (migration_registry MAX = 14 → 015+). Lição 6ae9216.
3. **EARS → testes:** os 23 testes cobrem lógica de unidade (normalização/dedup/actions); ADICIONAR
   teste de integração que prove M3.1 no fluxo real de busca (hoje inexistente).
4. **Env:** documentar `MCP_GAP_THRESHOLD` (default 0.3).

## 8. Dependências

Nenhuma (roda independente; não depende do #116 nem do Henry para implementar fork-only).

## 9. Relação com o arco

Filha independente do **learning-loop**. É o braço "o que FALTA" — complementa a telemetria
(usage_events, o que foi USADO) com o negativo (o que foi BUSCADO e não achado). Juntas dão o
quadro: o que ajuda, o que falta. Alimenta decisão de ingestão (fecha com o arco ingestão).
