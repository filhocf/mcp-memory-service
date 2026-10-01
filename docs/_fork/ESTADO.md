# ESTADO — mcp-memory-service (Claudio)

> Para você abrir e entender onde estamos sem reconstruir contexto.
> Árvore primeiro (visão), notas depois (detalhe). Atualizado: 2026-10-01.

```
mcp-memory-service (fork = linha viva · 0 atrás do upstream · 1/out)
│  Legenda: ✅ MERGED/feito · 🟢 feito fork-only · 🟡 parcial/design · 🔴 a fazer
│
├─ ✅ ARCO RATING / QUALITY ............................. FECHADO
│   ├─ quality-model (computed vs user_rating) ......... ✅ MERGED PR #1349
│   ├─ retention_periods (ontologia, upstream) ......... ✅ MERGED PR #1368 — desmascarou o decay
│   ├─ MCP_DECAY_ENABLED (timkjr) ...................... ✅ MERGED PR #1391 — furo lateral fechado
│   └─ supersession orphan (fix coluna + list_orphans) . 🟢 PR #1404 ABERTO (nosso)
│
├─ 🟡 ARCO INGESTÃO MULTI-AGENTE ....... REDESENHO (foco) · RFC #1393 na discussion
│   │   "1 serviço, N agentes/clientes · regras por agente, plugáveis (YAML)"
│   │
│   ├─ Peças JÁ FEITAS (encaixam nas camadas):
│   │   ├─ I0 coverage instrument ......................... ✅ MERGED PR #1350
│   │   ├─ I0-lang idioma no Phase 0 ...................... ✅ MERGED PR #1379 (split extracted/dropped)
│   │   ├─ IA discovery workspace ......................... ✅ MERGED PR #1378 (find_sessions+resolve+guard)
│   │   ├─ IB parser SQLite/Crew .......................... ✅ MERGED PR #1379 (conversations_v2 read-only)
│   │   └─ I1 ToolResults CLI {kind} (78e29b05) ........... 🟢 FORK (msg+bloco; thinking=redacted, só contado)
│   │
│   ├─ C1 registro/descoberta de N fontes .............. 🔴 design (absorve source-identity)
│   │      declarativo + auto-descoberta assistida · lê sidecar identidade (agent_id.name/workspacePaths)
│   ├─ C2 perfil de parsing por agente (YAML) .......... 🔴 design (absorve kiro-sessions)
│   │      padrão patterns-por-locale · hooks p/ navegação irredutível · add agente = escrever YAML
│   ├─ C3 extração/qualidade sinal-ruído ............... 🟡 design (absorve design-extraction)
│   │      heurísticas O(n) 1º (95% prosa / 4% json medido) → LLM só gated · honra locale
│   │
│   ├─ triage.py (score valor, 2 eixos, 193 testes) ... 🟢 PRONTO mas NÃO PLUGADO no harvester
│   └─ ⚠️ FASE 0 (fecha a dor, NÃO depende do Henry): plugar triage + Kiro→YAML + colher 11 OURO curados
│
├─ 🟡 ARCO PORTABILIDADE ............... design aceito pelo Henry (5 camadas)
│   ├─ discussion #1364 (5 camadas) ................... ✅ Henry aceitou o modelo
│   ├─ wiki Memory-Portability-Map ...................... ✅ no ar (mapa por harness)
│   ├─ "bring your memory": conversor mem0 .............. 🟡 PR #1401 (Harbor404, fecha nosso #1390)
│   └─ "use in any agent" ............................... → é o arco ingestão multi-agente (acima)
│
└─ 🟡 ARCO HUB MULTI-AGENTE ............ agent_id feito; falta a malha
    ├─ agent_id F1/F2 (autoria no store) .............. ✅ MERGED PR #1278/#1297
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
- **Redesenho da ingestão multi-agente:** RFC guarda-chuva escrita (`docs/rfc/planned/rfc-ingestao-multi-agente.md`) e levada à **discussion #1393** — aguardando o Henry avaliar o formato em camadas + o 1º incremento (Kiro→YAML).
- **Docs reorganizados:** RFCs no fork em `planned/`(22)/`implemented/`(23, verificadas por código); acompanhamento em `docs/_fork/`; estudos ficam no CdIA.

## A DOR (o que falta de verdade, em 1 frase)
A colheita do Kiro **lê os formatos** (feito) mas **NÃO filtra valor**: hoje colheria "hello v3", testes e dumps junto com o conhecimento. A triagem que resolve isso (`harvest/triage.py` — score calibrável, 2 eixos, 11 testes verdes) **já existe no código mas NÃO está plugada no harvester**. Fechar a dor = plugar a triagem + colher o acervo bom.

## FASE 0 — tarefas concretas (fecha a dor; NÃO depende do Henry — refactor seguro)
- [x] **T1. Plugar `triage.py` no harvester** ✅ FEITO (c1d52109, opt-in MCP_HARVEST_TRIAGE, sync+async, 194 testes) — antes de colher/gravar, descartar sessões `teste`/`vazia`/`truncada`/`dump` (score < limiar). Hoje o `find_sessions` colhe tudo que o parser reconhece.
- [ ] **T2. Extrair regras do Kiro → `harvest/agents/kiro.yaml`** — maps hardcoded (KIRO_KIND_MAP, markers, cutoff, globs) viram YAML declarativo (camada C2). Refactor dado→config.
- [ ] **T3. Golden test** — `coverage_report()` byte-idêntico antes/depois (prova que não quebrou os 3 formatos já suportados).
- [ ] **T4. COLHER o acervo curado** — AÇÃO DEDICADA (demora/LLM): rodar harvest_and_store use_llm no acervo. Dry-run deu 11 sessões/23 cand heurístico; LLM refina o resíduo intra-sessão. Decisão Claudio: colher via LLM (não heurístico cru). — rodar o harvest com triagem nos 11 OURO+CONVERSA já triados (`~/local-data/kiro-harvest-curado/`). **É aqui que a dor morre:** conhecimento real do Kiro entra na memória, sem o lixo. dry-run 1º.
- Peça pronta: `src/mcp_memory_service/harvest/triage.py` + `tests/harvest/test_triage.py` (193 verdes). Fixture: `~/local-data/kiro-harvest-curado-v2/curated/{uuid}/messages.jsonl` (11 sessões, layout 2-níveis que o find_sessions acha).

## Depende do Henry (paralelo, não bloqueia a Fase 0)
1. **Discussion #1393** — Henry avaliar o formato em camadas + Kiro→YAML como 1º incremento (RFC ingestão). Não respondeu ainda.
2. **PR #1404** (fix #1352) — CI/Greptile + merge do Henry.
3. Se #1393 ok → materializar specs das outras camadas (C1 multi-fonte, C3 LLM-extractor).

## Decisões abertas (esperando você)
- **Escopo da Fase 0:** (a) fork-only — plugar triagem + colher os 11 OURO (fecha a dor HOJE); ou (b) + `kiro.yaml` + golden test visando PR upstream (generaliza, mais trabalho). A dor fecha com (a); (b) é (a) empacotada p/ o Henry.

## Onde está o quê
- **RFCs:** `docs/rfc/planned/` (futuro) e `docs/rfc/implemented/` (feito). Índice: `docs/rfc/_index.md`.
- **Acompanhamento (fork-only):** `docs/_fork/` — roadmap, pilha de PRs, este ESTADO.md, ARCOS.md (versão densa p/ o agente).
- **Estudos/pesquisas/guias:** ficam no CdIA (`conhecimentos-de-ia/ferramentas/mcp/memory-service/estudos|guias`).
