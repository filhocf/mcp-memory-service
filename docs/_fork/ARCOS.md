# ARCOS — mapa de trabalho (agente)

> Doc DENSO para carga rápida do agente. Onde estamos, por arco, cruzando RFC ↔ estado ↔ próximo passo.
> Regra: mudou → atualiza AQUI (e no ESTADO.md a árvore). Atualizado: 2026-09-30.
> Fonte de verdade dos arcos. RFCs em `docs/rfc/{planned,implemented}/`. Estado operacional em `pilha-prs-runbook.md`.

## Snapshot
- **main fork:** sincronizada com upstream (0 atrás). Fila Henry: 0 PRs nossos abertos.
- **PRs mergeados hoje (30/set):** #1378 (discovery workspace), #1379 (SQLite+idioma). #1368 (retention — fecha rating).
- **Foco atual:** REDESENHO → arco de ingestão multi-agente (3 camadas). Ver abaixo.

## Arcos

| Arco | Estado | RFCs (docs/rfc/) | Próximo passo |
|------|--------|------------------|---------------|
| **Ingestão multi-agente** (NOVO guarda-chuva) | 🔴 design | planned/rfc-ingestao-multi-agente v0.1 — discussion #1393 aberta | escrever RFC guarda-chuva ✅ discussion #1393 postada → aguarda Henry |
| ├ Camada 1: registro/descoberta de fontes N | 🔴 design | implemented/rfc-harvest-source-identity (ABSORVIDA) | declarativo + auto-descoberta assistida |
| ├ Camada 2: perfil de parsing por agente (YAML) | 🔴 design | implemented/rfc-harvest-kiro-sessions (ABSORVIDA) | 1º passo: extrair Kiro→YAML (golden test) |
| ├ Camada 3: extração/qualidade sinal-ruído+LLM | 🟡 parcial | implemented/rfc-harvest-design-extraction (ABSORVIDA) | heurísticas declarativas 1º, LLM depois |
| │  ├ I0 coverage instrument | ✅ #1350 merged | — | — |
| │  ├ I0-lang idioma | ✅ #1379 merged | — | — |
| │  ├ IA discovery / IB SQLite | ✅ #1378/#1379 merged | — | — |
| │  └ I1 ToolResults CLI {kind} | 🟢 fork (78e29b05) | — | consolidar em PR upstream quando arco amadurecer |
| **Rating / quality-model** | ✅ FECHADO | implemented/rfc-quality-model | — (#1349 mergeado; #1368 desmascarou o decay) |
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
