# ESTADO — mcp-memory-service (Claudio)

> Para você abrir e entender onde estamos sem reconstruir contexto.
> Árvore primeiro (visão), notas depois (detalhe). Atualizado: 2026-10-01.

```
mcp-memory-service (fork = linha viva · 0 atrás do upstream · 2/out)
│  Legenda: ✅ MERGED/feito · 🟢 feito fork-only · 🟡 parcial/design · 🔴 a fazer
│
├─ ✅ ARCO RATING / QUALITY ............................. FECHADO
│   ├─ quality-model (computed vs user_rating) ......... ✅ MERGED PR #1349
│   ├─ retention_periods (ontologia, upstream) ......... ✅ MERGED PR #1368 — desmascarou o decay
│   ├─ MCP_DECAY_ENABLED (timkjr) ...................... ✅ MERGED PR #1391 — furo lateral fechado
│   └─ supersession orphan (fix coluna + list_orphans) . ✅ MERGED PR #1404 (nosso #1352)
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

## ◄ RE-ENQUADRAMENTO (02/out): o NORTE é APRENDER, não colher
> Pergunta do Claudio: "de que adianta colher memórias se não vira CONHECIMENTO? Como me fazer APRENDER?"
> Nova RFC guarda-chuva: **`docs/rfc/planned/rfc-learning-loop.md`** (do colhedor ao aprendiz).

O produto NÃO é "mais memórias colhidas" — é o **ciclo de aprendizado fechado**:
```
colher(limpo) → DESTILAR[L2] → VALIDAR/feedback[L4] → INJETAR proativo[L3] → agir melhor → recalibra ⟲
```
- **L1 Memória** ✅ · **L2 Destilação** 🟡 ruidosa (beliefs conf≤0.64) · **L3 Injeção** 🟡 só pull · **L4 Feedback** 🔴 zero.
- **Colher (Fase 0) é PRÉ-REQUISITO, não o objetivo** — enche o reservatório limpo. O motor é destilar+validar+injetar.
- **Gargalo real = SINAL DE USO** (o serviço é cego pro agente; não sabe se a injeção ajudou). Priorizar **negative learning** (contradição = sinal forte e barato) antes do positivo.
- **É do SERVIÇO, não do agente** (agente é efêmero; serviço é o substrato persistente). Não é fine-tuning — o aprendizado vive no harness, efeito indistinguível de aprender no contexto.
- **Pesquisa JÁ EXISTE** (não reinventar): CdIA `padroes/mcp-memory-autolearn-rfc.md` (11 sistemas + 8 fases) + plano self-improvement. Reler autolearn-rfc §2.2/§2.4 antes de implementar.
- **Caminho mínimo:** (1) limpar beliefs (task dc1c7756) → (2) destilação confiável (trilogia C1) → (3) feedback-loop (C3) → (4) injeção proativa (memory_context).


## Feito recentemente (2/out)
- **Fork sincronizado + serviço resgatado:** merge upstream/main (7 commits; nosso #1404/#1352 supersession mergeado pelo Henry). Serviço systemd em 11.14.0, 11 OURO colhidas.
- **2 bugs achados e corrigidos POR GATE (reg + tuvok), não na mão:**
  - **Bug rewriter `TYPE:` leak** (real, upstream também) → issue #1417 + **PR #1418 ABERTO** (CI tests-prove-fix verde, aguarda Henry). O LLM ecoava o placeholder literal `TYPE:` para dentro do content + degenerados; `_unleak_type` + prompt `<type>:`.
  - **Bug triagem nunca ativada** (fork-only): `_apply_triage` plugado mas nenhum call-site passava a flag → feature morta. Corrigido (`harvest_config_from_env` nos 4 entry points, default OFF). NÃO vira PR de bug avulso — a triagem não existe no upstream, então entra junto no PR de FEAT.
- **11 OURO gravadas** no banco vivo via `memory_consolidate action=harvest` (in-process, integridade intacta), triagem ativada (`MCP_HARVEST_TRIAGE=1`), rewriter já corrigido → 0 vazamento.
- **Devolutiva do Henry (29/set) nos RFCs do arco** (ver "Em andamento").

## Em andamento
- **Arco ingestão multi-agente — a bola está do NOSSO lado (Henry respondeu via #1346, não via #1393).**
  A discussion #1393 (nosso guarda-chuva, 30/set) ainda só tem o nosso comentário. MAS o Henry respondeu o mesmo arco na **issue #1346 (design-extraction, 29/set)** com pedido concreto antes de qualquer extractor:
  1. **Tornar o coverage visível** — `coverage_report()` (#1350) existe mas nenhum call-site em `src/` o lê; pôr no resultado do harvest + log. "Phase 0 isn't done" até isso. **← próximo PR que ele pediu.**
  2. **Nota de compatibilidade** — quantas memórias a mais o harvest escreve (extractor + path v4 tool_result do #1366), tags `harvest:mode:*`, como desligar.
  3. **Números do kill switch** — taxa de adoção + threshold + data de revisão.
  4. **Legacy Kiro `ToolResult`** ainda dropado vs v4 mantido — unificar ou documentar o porquê.
  Ordem dele: "cheapest first", PR do ponto 1 + respostas 2/3 como update do RFC. → Em vez de "ping" na #1393, entregar o ponto 1 e aí comentar linkando.
- **#1345 delta-sync:** travado atrás do #1304 (remote_http); fica em design. ducanhnguyen223 prepara v0.4.
- **PR #1418 (rewriter):** aguarda review do Henry. 1 PR de bug pode coexistir com outros (regra 2/out: 1-por-vez só p/ feat).

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
