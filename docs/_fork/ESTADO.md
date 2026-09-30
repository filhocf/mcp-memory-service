# ESTADO — mcp-memory-service (Claudio)

> Para você abrir e entender onde estamos sem reconstruir contexto.
> Árvore primeiro (visão), notas depois (detalhe). Atualizado: 2026-09-30.

```
mcp-memory-service (fork filhocf)
│
├─ ✅ RATING/QUALITY ......... FECHADO
│    #1349 mergeado + #1368 (retention) desmascarou o decay
│    → a qualidade das memórias agora afeta o esquecimento de fato
│
├─ 🟡 INGESTÃO MULTI-AGENTE .. REDESENHO EM CURSO (o foco agora)
│    │  "1 serviço de memória, N agentes/clientes na mesma máquina"
│    ├─ Camada 1: descobrir de QUEM e de ONDE colher (N fontes)
│    ├─ Camada 2: perfil por agente em YAML plugável (não hardcoded)
│    └─ Camada 3: separar sinal (raciocínio) de ruído (log/json)
│         ✅ já feito: coverage, idioma, discovery, SQLite, ToolResults
│         🔴 falta: RFC guarda-chuva → discussion → specs por camada
│
├─ 🟡 PORTABILIDADE .......... design aceito pelo Henry (5 camadas)
│    wiki Memory-Portability-Map no ar · conversor mem0 (#1390)
│    parte absorvida pela ingestão multi-agente
│
└─ 🟡 HUB MULTI-AGENTE ....... agent_id feito; falta a malha (estrela)
     sincronizar os N agentes num hub central, sem ruído replicado
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
