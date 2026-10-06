# Radar de terceiros — mcp-memory-service

> **Por quê:** estamos ganhando espaço no projeto (co-maintainer de quality/handlers/harvest).
> Precisamos vigiar o que TERCEIROS fazem — especialmente na nossa área ou que cruze
> nossos arcos. PR de terceiro que toca storage/harvest pode conflitar com a linha viva,
> duplicar trabalho nosso, ou abrir oportunidade de review/colaboração.
> **Mantido pelo ritual `memory-service-context`** (passo 2). Regra: mexeu → atualiza aqui.
> Atualizado: 2026-10-06.

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
