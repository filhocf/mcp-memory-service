# Radar de terceiros — mcp-memory-service

> **Por quê:** estamos ganhando espaço no projeto (co-maintainer de quality/handlers/harvest).
> Precisamos vigiar o que TERCEIROS fazem — especialmente na nossa área ou que cruze
> nossos arcos. PR de terceiro que toca storage/harvest pode conflitar com a linha viva,
> duplicar trabalho nosso, ou abrir oportunidade de review/colaboração.
> **Mantido pelo ritual `memory-service-context`** (passo 2). Regra: mexeu → atualiza aqui.
> Atualizado: 2026-10-03.

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

## PRs de terceiros ABERTOS (snapshot 3/out)

| PR | Autor | Área | Status p/ nós |
|----|-------|------|---------------|
| #1442 | mrhard9090 | api/client+operations (#1146) | 🟡 vigiar — campanha seg |
| #1441 | mrhard9090 | storage/mixins/store (#1146) | 🟡 nossa área — merge pode tocar linha viva |
| #1439 | mrhard9090 | storage/mixins/delete (#1146) | 🟡 **delete.py = onde fica purge_deleted do #1352** — vigiar conflito |
| #1412 | rubenmarcus | versioned metadata (fecha #1408) | 🟡 ACIONÁVEL — Henry pediu design ao Claudio no #1408; thread Greptile pendente |
| #1403 | Harbor404 | Prometheus endpoint | 🟢 = nosso #1097 (sem urgência) |
| #1402 | Harbor404 | rate-limit per-agent | 🟡 = nosso #1096; agent_id (nosso) destravou keying — pode citar nosso trabalho |
| #1401 | Harbor404 | mem0 export converter | 🟡 **fecha NOSSA issue #1390** (portabilidade) — se mergear, nosso tracking vira done |
| #1400 | Harbor404 | pymilvus 3.x | 🟢 complementar |

## Issues de terceiros na nossa área

| Issue | Autor | Nota |
|-------|-------|------|
| #1095 | doobidoo | Hermes state.db adapter (auto-harvest) — cruza arco ingestão + portabilidade G2 |
| #1355 | timkjr | retention keyed por nomes legados — pode mascarar nosso #1349 (arco rating). Avaliar. |

## O que exige AÇÃO nossa agora
- **#1412** (rubenmarcus): está no inbox acionável. Decidir se revisamos (área storage/versioned nossa).
- **#1439** (mrhard, delete.py): quando mergear, próximo `git merge upstream/main` traz mudança no delete.py — conferir que não briga com nosso purge_deleted do #1352.
- **#1401** (Harbor404, mem0): se mergear, fechar nossa issue #1390 como "resolvido por terceiro".

## Oportunidade estratégica
A campanha #1146 é contribuição fácil e bem-vista. Pegar 1-2 arquivos restantes na
nossa área (handlers/) seria ganhar espaço — mas só se não atrapalhar o foco (learning-loop/Fase 0).
