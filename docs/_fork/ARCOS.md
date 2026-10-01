# ARCOS — mapa de trabalho (agente)

> Doc DENSO para carga rápida do agente. Onde estamos, por arco, cruzando RFC ↔ estado ↔ próximo passo.
> Regra: mudou → atualiza AQUI (e no ESTADO.md a árvore). Atualizado: 2026-10-01.
> Fonte de verdade dos arcos. RFCs em `docs/rfc/{planned,implemented}/`. Estado operacional em `pilha-prs-runbook.md`.

## Snapshot
- **main fork:** sincronizada com upstream (0 atrás, 116+ à frente). **1 PR nosso aberto: #1404.**
- **Mergeados pelo upstream (1/out):** #1391 (decay flag, timkjr — fecha furo lateral do arco rating), #1395 (scope by store), #1398/#1394 (log-sanit).
- **PR nosso #1404** (fix #1352 supersession, área storage): aberto, CI re-rodando pós-refino do Greptile. NÃO self-merge.
- **PRs de terceiro (Harbor404) na nossa vizinhança — comentados:** #1401 (mem0, fecha nosso #1390 — elogiado + pedimos ownership de sync/converters), #1402 (rate-limit, fecha #1096 — apontamos bug agent_id filtro-vs-identidade). #1403 (metrics, draft web, ignorado).
- **Foco:** arco ingestão multi-agente (RFC #1393 aguarda Henry) + fechamento #1352.

## Arcos

| Arco | Estado | RFCs (docs/rfc/) | Próximo passo |
|------|--------|------------------|---------------|
| **Ingestão multi-agente** (NOVO guarda-chuva) | 🔴 design | planned/rfc-ingestao-multi-agente v0.3 — discussion #1393 (evidência a postar) | escrever RFC guarda-chuva ✅ discussion #1393 postada → aguarda Henry |
| ├ Camada 1: registro/descoberta de fontes N | 🔴 design | implemented/rfc-harvest-source-identity (ABSORVIDA) | declarativo + auto-descoberta assistida |
| ├ Camada 2: perfil de parsing por agente (YAML) | 🔴 design | implemented/rfc-harvest-kiro-sessions (ABSORVIDA) | spec-fase0 escrita; triage.py consolidado (193 testes); aguarda aval #1393 |
| ├ Camada 3: extração/qualidade sinal-ruído+LLM | 🟡 parcial | implemented/rfc-harvest-design-extraction (ABSORVIDA) | heurísticas declarativas 1º, LLM depois |
| │  ├ I0 coverage instrument | ✅ #1350 merged | — | — |
| │  ├ I0-lang idioma | ✅ #1379 merged | — | — |
| │  ├ IA discovery / IB SQLite | ✅ #1378/#1379 merged | — | — |
| │  └ I1 ToolResults CLI {kind} | 🟢 fork (78e29b05) | — | consolidar em PR upstream quando arco amadurecer |
| ** Rating / quality-model** | ✅ FECHADO | implemented/rfc-quality-model | — #1349+#1368+#1391(decay, mergeado 1/out) fecharam. #1352 (supersession orphan) → PR #1404 nosso, área storage |
| **Portabilidade** (bring your memory ⊕ use in any agent) | 🟡 design aceito | planned/rfc-memory-portability, planned/rfc-importers | wiki Memory-Portability-Map viva; conversor mem0 (#1390); parte absorvida pela ingestão multi-agente |
| **Hub memória multi-agente** | 🟡 parcial | planned/rfc-hub-memoria-centralizada, planned/rfc-delta-sync, planned/rfc-sync-multi-agente, implemented/rfc-agent-id-multi-agent | agent_id F1/F2 mergeados; falta F3-F8 (estrela, consolidação nas pontas, NLI cross-agent) |

## Sub-arcos ativos / decisões abertas
- **Redação de segredos** (todo #5): NÃO no store local (mesmo disco). No PONTO DE SAÍDA (sync hub / LLM). Ação futura.
- **RFC guarda-chuva ingestão multi-agente:** a redigir → levar à discussion (Henry decide design antes do código) → materializar specs por camada.
- **1º passo executável (aceito pelo Henry):** extrair regras hardcoded de UM agente (Kiro) para `harvest/agents/kiro.yaml` (refactor dado→config, golden test de cobertura byte-idêntica). Não misturar com heurísticas/LLM.

## Issues/PRs upstream vivas
- #1390 (tracking conversor mem0) — aberta. #1345 (delta-sync, colab ducanhnguyen223) / #1346 (design-extraction) — RFCs abertas.

## Índice reverso RFC → arco → status
Ver `docs/rfc/_index.md` para a lista completa. Absorvidas pela ingestão multi-agente: harvest-source-identity (C1), harvest-kiro-sessions (C2), harvest-design-extraction (C3).

## Docs irmãos (navegação)
- **ESTADO.md** — versão legível deste mapa (para o Claudio).
- **roadmap.md** — épicos com árvore/esforço. **pilha-prs-runbook.md** — estado operacional dos PRs.
- **reference-pipeline.md** — arquitetura do pipeline de memória.
- **../rfc/_index.md** — índice de todas as RFCs (planned/implemented).
