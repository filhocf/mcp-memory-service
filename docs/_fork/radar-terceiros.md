# Radar de terceiros — mcp-memory-service

> **Por quê:** estamos ganhando espaço no projeto (co-maintainer de quality/handlers/harvest).
> Precisamos vigiar o que TERCEIROS fazem — especialmente na nossa área ou que cruze
> nossos arcos. PR de terceiro que toca storage/harvest pode conflitar com a linha viva,
> duplicar trabalho nosso, ou abrir oportunidade de review/colaboração.
> **Mantido pelo ritual `memory-service-context`** (passo 2). Regra: mexeu → atualiza aqui.
> Atualizado: 2026-10-31.

## Snapshot 31/out — PRs/issues abertos cruzando nossa área

| # | Autor | Área | Status p/ nós |
|---|-------|------|---------------|
| **#1726** | juliasadler | `memory_search` point-in-time `as_of` + status flags (fixes #1724) | 🟡 **pedem review do filhocf.** +754/−42, hot path. Parecer (seven): PEDIR MUDANÇAS — opt-in OK (as_of=None preserva default, não regride nosso uso), mas as_of é ignorado em exact/tag/time/RRF sem erro + risco em `_do_update` (superseded_at sem guard). Não urgente p/ nós. Pendente: redigir review no GH (gate externo). |
| #1724 | juliasadler | issue-mãe do as_of | 🟡 acompanhar junto do #1726 |
| **#1714** | ducanhnguyen223 | `fix(security): confine graph/resource reads to stores` (+1988/−374, 43 arq) | 🟡 **draft.** Store boundary em entity graph/profiles/detail/traversal. Toca storage pesado — vigiar vs linha viva. Relacionado à issue #1683. |
| #1683 | — | forçar store na camada de storage p/ ops por hash/id | 🟡 issue-base do #1714, nossa área |
| **#1716** | ducanhnguyen223 | `contextualCapture` opt-in p/ hooks Codex (+281/−12) | 🟡 **draft.** Captura source-linked pareando reply+assistant. **Pode sobrepor nosso arco de captura/harvest.** issue-mãe #1664. |
| #1664 | — | Proposal: opt-in source-linked contextual capture (Codex) | 🟡 radar captura |
| #1722 | — | Feature: reconstruir entity graph de memórias existentes | 🟡 toca entities/consolidation |
| #1460 | — | Auto-supersede em contradicts edges: review band + judgment real | 🟡 **cruza nosso arco belief/NLI** (síntese de belief F2) |
| #1715 | ducanhnguyen223 | fix dark-mode flash dashboard (+44) | ⚪ cosmético, fora de área |

> **Absorvido pelo upstream no sync 31/out** (11 commits, nossa main agora 492 à frente / 0 atrás): #1725 harvest GPT-5 params, #1701 rerank per-stage timing (honra MCP_QUALITY_LOCAL_DEVICE — toca nosso reranker), #1717 OAuth, #1713 entities-por-tag, #1718 Milvus lazy, #1712/#1706 Milvus graph edges, #1710 CI prove-fix, #1720 multi-store test, #1719 quality log. Além do NOSSO #1721 (delta-sync compaction) mergeado por doobidoo 30/out.

---

## Legenda
- 🟢 complementar (não conflita, bom pro projeto) · 🟡 cruza nossa área (vigiar) · 🔴 conflita/duplica (agir)

## Contribuidores ativos (quem mais mexe além de nós + Henry)

| Autor | O que faz | Relação com nossos arcos |
|-------|-----------|--------------------------|
| **Harbor404** | 4 feats paralelas (abaixo) | mem0 fecha NOSSA issue #1390 (portabilidade); rate-limit = nosso #1096 (hub) |
| **mrhard9090** | varredura seg #1146 (storage/api) | 🟡 toca storage/mixins (nossa área) — vigiar conflito com linha viva |
| **rubenmarcus** | versioned metadata #1412 | 🟡 storage/versioned — vizinho do nosso #1352/#1404 |
| **timkjr** | bugs rating/supersession (#1352→nosso #1404, #1355 retention) | fonte dos bugs que fecharam nosso arco rating |
| **ducanhnguyen223** | colab delta-sync (#1345 v0.4) | 🟢 nosso arco hub — colaboração ativa |

## PRs de terceiros ABERTOS (snapshot 6/out)

| PR | Autor | Área | Status p/ nós |
|----|-------|------|---------------|
| #1402 | Harbor404 | rate-limit per-agent (`server_impl`+`web/api/mcp`+util novo) | 🟡 = nosso #1096; agent_id (nosso) destravou keying. Sliding-window process-local, default unlimited (opt-in `MCP_RATE_LIMIT_PER_MINUTE`). Toca server_impl — vigiar vs linha viva |
| #1401 | Harbor404 | mem0 export converter (`sync/converters/mem0.py`) | 🟡 **Fixes #1390** (NOSSA issue de portabilidade). +944/0, só add. Se mergear → nosso tracking #1390 vira done |

> **Resto da fila de 3/out foi ABSORVIDA pelo Henry (merges 6/out):** #1442/#1441/#1439 (mrhard9090 campanha seg #1146) MERGED · #1412 (rubenmarcus versioned) MERGED · #1400 (pymilvus 3.x) MERGED · #1403 (Prometheus terceiro) CLOSED — nosso #1456 venceu. Todos já na linha viva via sync 6/out. Nenhum conflito com purge_deleted #1352 (delete.py mergeado limpo).

## Issues de terceiros na nossa área

| Issue | Autor | Nota |
|-------|-------|------|
| #1095 | doobidoo | Hermes state.db adapter (auto-harvest) — cruza arco ingestão + portabilidade G2 |
| #1355 | timkjr | retention keyed por nomes legados — pode mascarar nosso #1349 (arco rating). Avaliar. |

## O que exige AÇÃO nossa agora
- **#1401** (Harbor404, mem0): continua OPEN e tem `Fixes #1390`. Se Henry mergear, fechar nossa issue #1390 (tracking) como "resolvido por terceiro". Vigiar — é cortês comentar reconhecendo (fecha trabalho que era nosso tracking).
- **#1402** (Harbor404, rate-limit per-agent): toca `server_impl.py` (dispatcher) — quando mergear, próximo `git merge upstream/main` entra na linha viva; conferir que não briga com nosso wiring de telemetria no `call_tool`. É o nosso #1096.

## Oportunidade estratégica
A campanha #1146 é contribuição fácil e bem-vista. Pegar 1-2 arquivos restantes na
nossa área (handlers/) seria ganhar espaço — mas só se não atrapalhar o foco (learning-loop/Fase 0).
