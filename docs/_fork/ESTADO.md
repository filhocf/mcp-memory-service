# ESTADO — mcp-memory-service (Claudio)

> Para você abrir e entender onde estamos sem reconstruir contexto.
> Árvore primeiro (visão), notas depois (detalhe). Atualizado: 2026-09-30.

```
mcp-memory-service (fork = linha viva · 0 atrás do upstream · 30/set)
│  Legenda: ✅ feito/mergeado · 🟢 feito fork-only · 🟡 parcial/design · 🔴 a fazer
│
├─ ✅ ARCO RATING / QUALITY ............................. FECHADO
│   ├─ #1312 quality-model → PR #1349 ................... ✅ MERGEADO (computed vs user_rating)
│   ├─ #1368 retention_periods (ontologia) ............. ✅ upstream — desmascarou o decay
│   └─ efeito: qualidade agora influencia esquecimento .. ✅ verificado (antes r=-0.006)
│
├─ 🟡 ARCO INGESTÃO MULTI-AGENTE ....... REDESENHO (foco) · RFC #1393 na discussion
│   │   "1 serviço, N agentes/clientes · regras por agente, plugáveis (YAML)"
│   │
│   ├─ Peças JÁ FEITAS (encaixam nas camadas):
│   │   ├─ I0 coverage instrument (#1350) .............. ✅ MERGED
│   │   ├─ I0-lang idioma no Phase 0 (#1379) ........... ✅ MERGED (split extracted/dropped)
│   │   ├─ IA discovery workspace (#1378) ............. ✅ MERGED (find_sessions+id+resolve+guard)
│   │   ├─ IB parser SQLite/Crew (#1379) .............. ✅ MERGED (conversations_v2 read-only)
│   │   └─ I1 ToolResults CLI {kind} (78e29b05) ....... 🟢 FORK (msg+bloco; thinking=redacted, só contado)
│   │
│   ├─ C1 registro/descoberta de N fontes .............. 🔴 design (absorve source-identity)
│   │      declarativo + auto-descoberta assistida · lê sidecar identidade (agent_id.name/workspacePaths)
│   ├─ C2 perfil de parsing por agente (YAML) .......... 🔴 design (absorve kiro-sessions)
│   │      padrão patterns-por-locale · hooks p/ navegação irredutível · add agente = escrever YAML
│   ├─ C3 extração/qualidade sinal-ruído ............... 🟡 design (absorve design-extraction)
│   │      heurísticas O(n) 1º (95% prosa / 4% json medido) → LLM só gated · honra locale
│   │
│   ├─ 1º passo (aceito p/ Henry): Kiro→YAML golden test  🔴 aguarda OK da discussion #1393
│   └─ ⚠️ GATE: discussion → specs por camada → Fase 0 (refactor dado→config, cobertura byte-idêntica)
│
├─ 🟡 ARCO PORTABILIDADE ............... design aceito pelo Henry (5 camadas)
│   ├─ discussion #1364 (5 camadas) ................... ✅ Henry aceitou o modelo
│   ├─ wiki Memory-Portability-Map ..................... ✅ no ar (mapa por harness)
│   ├─ "bring your memory": conversor mem0 (#1390) ..... 🔴 tracking aberto (1º de N)
│   └─ "use in any agent" ............................. → é o arco ingestão multi-agente (acima)
│
└─ 🟡 ARCO HUB MULTI-AGENTE ............ agent_id feito; falta a malha
    ├─ agent_id F1/F2 (#1278/#1297) ................... ✅ MERGED (autoria no store)
    ├─ SPEC-hub F0-F8 ................................. 🟡 spec pronta
    ├─ delta-sync (#1345) ............................. 🟡 RFC v0.3 (colab ducanhnguyen223 na v0.4)
    └─ F3-F8: estrela, consolidação nas pontas, NLI cross-agent  🔴 a fazer
```

## Onde estamos, em uma frase
Fechamos o arco de rating; descobrimos que os 3 arcos de harvest/identidade/portabilidade são **o mesmo problema** — colher bem de N agentes exige regras por agente **plugáveis (YAML)**, não hardcoded. Estamos redesenhando isso como um arco só (ingestão multi-agente) antes de escrever mais código.

## Feito recentemente (30/set)
- **Rating fechado:** o bug do retention (quase tudo caía em 30 dias) foi corrigido no upstream (#1368); trouxemos para a nossa main. Agora o nosso quality-split (#1349) tem efeito real no esquecimento.
- **Harvest:** os 2 PRs (discovery de sessões workspace + parser SQLite/Crew) foram **mergeados pelo Henry**. O parser passou a colher ToolResults do CLI (antes descartados).
- **Descoberta importante:** o "thinking" do Kiro é criptografado no disco (irrecuperável); o formato "{kind}" que o código chama de "legado" é na verdade o **atual** do CLI.
- **Portabilidade:** Henry aceitou nosso modelo de 5 camadas; wiki no ar; issue do conversor mem0 aberta.

## Em andamento
- **Redesenho da ingestão multi-agente** (o insight que você teve: importador precisa de regras por agente, plugáveis, e lidar com N agentes na mesma máquina — declarativo com auto-descoberta assistida). Próximo: escrever a RFC guarda-chuva e levar à discussion.
- **Reorganização dos docs** (esta, agora): RFCs no fork em planned/implemented; acompanhamento em docs/_fork/; estudos ficam no CdIA.

## Próximo passo
1. Escrever a RFC guarda-chuva de ingestão multi-agente (3 camadas + as 2 portas: colher local ⊕ importar externo).
2. Levar à discussion (Henry decide o design antes do código).
3. 1º passo de código pequeno: extrair as regras do Kiro para um YAML (refactor seguro, golden test).

## Decisões abertas (esperando você)
- Nada bloqueando agora. O redesenho está em fase de design (RFC), sua área de decisão.

## Onde está o quê
- **RFCs:** `docs/rfc/planned/` (futuro) e `docs/rfc/implemented/` (feito). Índice: `docs/rfc/_index.md`.
- **Acompanhamento (fork-only):** `docs/_fork/` — roadmap, pilha de PRs, este ESTADO.md, ARCOS.md (versão densa p/ o agente).
- **Estudos/pesquisas/guias:** ficam no CdIA (`conhecimentos-de-ia/ferramentas/mcp/memory-service/estudos|guias`).
