# ESTADO — mcp-memory-service (Claudio)

> Para você abrir e entender onde estamos sem reconstruir contexto.
> Árvore primeiro (visão), notas depois (detalhe). Atualizado: 2026-10-03.

```
mcp-memory-service (fork = linha viva · 0 atrás do upstream · 3/out · campanha seg #1146 absorvida)
│  Legenda: ✅ MERGED/feito · 🟢 feito fork-only · 🟡 parcial/design · 🔴 a fazer
│
├─ ✅ ARCO RATING / QUALITY ............................. FECHADO
│   ├─ quality-model (computed vs user_rating) ......... ✅ MERGED PR #1349
│   ├─ retention_periods (ontologia, upstream) ......... ✅ MERGED PR #1368 — desmascarou o decay
│   ├─ MCP_DECAY_ENABLED (timkjr) ...................... ✅ MERGED PR #1391 — furo lateral fechado
│   └─ supersession orphan (fix coluna + list_orphans) . ✅ MERGED PR #1404 (nosso #1352)
│
├─ 🟢 ARCO LEARNING LOOP ............... o NORTE (aprender, não só colher) · WorkItem 62046f1e
│   │   Meta (Claudio 3/out): o CONJUNTO destilação+injeção+feedback. "Ao final, preciso de tudo."
│   │   Modo: loop autônomo G0→G3→G4→G5→E2E por degrau; o MCP apoia a limitação do LLM.
│   │
│   ├─ D0 limpar beliefs ............................... ✅ já resolvido (noise filter existe; task dc1c7756 cancelada)
│   ├─ D1 destilação (L2) ............................... ✅ belief store já destila (240 active conf 0.87-0.98)
│   ├─ D2 feedback negativo (L4) ....................... 🟢 FORK 3/out (dc452953) · rating −1→belief cai · E2E −47,8% · opt-in MCP_BELIEF_USE_FEEDBACK
│   ├─ L1 telemetria de proveito (usage_events) ........ 🟢 FORK 3/out (cc412cfe) · migration 014 no banco VIVO · opt-out MCP_USAGE_TELEMETRY
│   ├─ L2 injeção proativa (tool memory_context) ....... 🟢 FORK 3/out (f752dd13) · injeta por TEMA · E2E banco vivo 24k · opt-out MCP_CONTEXT_INJECTION_ENABLED
│   ├─ N1 janela 1 semana — medir proveito REAL ........ 🔨 EM ANDAMENTO (até ~10/out) · get_usage_metrics no vivo · feedback_coverage sobe?
│   ├─ N2 PUSH automático (hook harness) ............... 🔴 depois de N1 · hoje é PULL; push real = startup-hook chamar memory_context
│   └─ N3 feedback positivo + sinal de uso auto ........ 🔴 depois de N1 · rating +1 reforça; belief reusado sobe sozinho
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

## 📍 ONDE ESTAMOS / PRA ONDE VAMOS (atualizado 3/out noite)

**Entregue hoje (fork main, pushado, aplicado no banco vivo):**
- 🟢 **Telemetria de proveito** (`usage_events` + `get_usage_metrics`, migration 014) — o serviço observa o próprio uso. Opt-out `MCP_USAGE_TELEMETRY`.
- 🟢 **Injeção proativa** (tool `memory_context`) — injeta beliefs por TEMA, não top-N cego. Opt-out `MCP_CONTEXT_INJECTION_ENABLED`.
- 🟢 **Metodologia de curadoria de fork** — `metodologia-fork.md` + `LEDGER-feats.md` + `ORFAOS.md` + skill `fork-curation` + ref no AGENTS.md. Nasceu de um erro real (reimplementei a trilogia que já existia).
- 🟢 **Inventário completo de material oculto** — 29 refs órfãos varridos 1-a-1. Só 3 órfãos-reais (trilogia resgatada, delta-sync §8 portado, audit macro-map). 26 refs-lixo deletados (local+remoto). Fork limpo.
- ↩️ **Revertido:** feedback síncrono (rating→belief) — LETRA MORTA (depende de rating manual que ninguém faz; a RFC-MM-01 já previa).

**Correção de rumo:** o L4 feedback é a **RFC-MM-01 do Claudio** (jul, feedback PASSIVO "zero disciplina"), que o Henry endossou na #1286 — não "modelo do Henry". A telemetria de hoje materializa ela.

**Pra onde vamos (ordem):**
1. 🔨 **Terminar a RFC-MM-01** fork-only sobre a telemetria: captar reaccess + job de recálculo de quality_score + wiring real no fluxo + acceptance (quality 0.5→0.65, bootstrap noise <10%). Arco 62046f1e.
2. **Janela 1 semana** (N1, ~10/out) medindo proveito real → decide N2 (push via hook) e N3 (feedback positivo).
3. **Trilogia** (branch `validacao/prototipo-trilogia`, 93 testes): completar spec p/ PR (doc payload window-tools #1286, EARS mm-03, changelog) → 3 PRs + responder #1286 (draft EN+PT-BR).
4. **Limpeza cross-host** (WorkItem a0d5abf2): worktrees sirdata + branches-lixo DNBSCDC289/socrates.

## 📋 BACKLOG COMPLETO — todas as RFCs/ideias (para enxergar tudo)
> Detalhe e evidência de código em `docs/rfc/_index.md` (47 RFCs: 23 implemented, 24 planned). Aqui = visão de uma linha por ideia, agrupada. Regra: toda RFC/arco/ideia nova entra AQUI no mesmo passo.

**🟢 ARCO LEARNING LOOP (o NORTE)** — ver árvore acima. RFCs: `rfc-learning-loop` (guarda-chuva).
Alimentado por (os COMOs, hoje design/0-EARS): `rfc-mm-01-feedback-loop`, `rfc-mm-02-fact-extraction`, `rfc-mm-03-gap-detection`, `rfc-fact-extraction`, `rfc-self-service-memory-intelligence`, `rfc-autolearn-autodream`, `rfc-server-side-lifecycle`.

**🟡 ARCO INGESTÃO MULTI-AGENTE** — ver árvore. RFCs: `rfc-ingestao-multi-agente` (guarda-chuva), `spec-fase0-kiro-yaml-triagem` (Fase 0 pronta), `rfc-pipeline-harvest-quality` ✅impl.

**🟡 ARCO HUB MULTI-AGENTE** — ver árvore. RFCs: `rfc-hub-memoria-centralizada` (SPEC F0-F8), `rfc-delta-sync` (#1345), `rfc-agent-id-multi-agent` ✅impl, `rfc-sync-multi-agente` ✅impl.

**🟡 ARCO PORTABILIDADE** — ver árvore. RFCs: `rfc-memory-portability` (5 camadas, #1364), `rfc-importers` (mem0/letta/zep, #1390).

**⚪ BACKLOG DE IDEIAS (sem arco ainda — ranking de prioridade a definir):**
- `rfc-query-intent` — 🟡 PAUSADA (WorkItem 9fa7e0ef, hold): teste do modelo de gerência; 4 arquivos não-commitados; valor marginal (ver ironia learning-loop). Decidir retomar/arquivar.
- `rfc-working-memory` — contexto quente auto-gerenciado (tier de memória recente). Conecta com injeção/L3.
- `rfc-ranking-upgrades` — Weibull decay + polyphonic recall (melhora recuperação).
- `rfc-memory-hygiene` — noise audit & safe cleanup (limpeza segura do acervo).
- `rfc-persona-tier` — identidade portável auto-gerada (conecta learning-loop + portabilidade).
- `rfc-skill-auto-generation` — pipeline de auto-geração de skill (padrão→skill).
- `rfc-embedding-quantization` — int8/binary vectors (performance/espaço).
- `rfc-multimodal-memory` — imagem/vídeo/áudio → texto recallável.
- `rfc-onboarding-discoverable` — guias de uso MCP agent-native (discovery protocol).
- `rfc-kiro-headless-llm-provider` — Kiro CLI headless como LLM provider (destilação sem API externa).
- `rfc-structural-improvements` — melhorias estruturais diversas.

**✅ INFRA JÁ IMPLEMENTADA (base, não precisa ação):** belief-store, nli-cascade, anti-hallucination, handler/tool-registry/routing, split-config, schema-versioning, multi-store-NER, quality-model. Detalhe no `_index.md`.

## ◄ RE-ENQUADRAMENTO (02/out): o NORTE é APRENDER, não colher
> Pergunta do Claudio: "de que adianta colher memórias se não vira CONHECIMENTO? Como me fazer APRENDER?"
> Nova RFC guarda-chuva: **`docs/rfc/planned/rfc-learning-loop.md`** (do colhedor ao aprendiz).

O produto NÃO é "mais memórias colhidas" — é o **ciclo de aprendizado fechado**:
```
colher(limpo) → DESTILAR[L2] → VALIDAR/feedback[L4] → INJETAR proativo[L3] → agir melhor → recalibra ⟲
```
- **L1 Memória** ✅ · **L2 Destilação** ✅ (beliefs active conf 0.87-0.98, noise filter ativo) · **L3 Injeção** 🟡 por-tema (memory_context, one-shot) · **L4 Feedback** 🟡 1º passo fechado (negative-use).
- **Colher (Fase 0) é PRÉ-REQUISITO, não o objetivo** — enche o reservatório limpo. O motor é destilar+validar+injetar.
- **Gargalo real = SINAL DE USO** (o serviço é cego pro agente; não sabe se a injeção ajudou). Priorizar **negative learning** (contradição = sinal forte e barato) antes do positivo.
- **É do SERVIÇO, não do agente** (agente é efêmero; serviço é o substrato persistente). Não é fine-tuning — o aprendizado vive no harness, efeito indistinguível de aprender no contexto.
- **Pesquisa JÁ EXISTE** (não reinventar): CdIA `padroes/mcp-memory-autolearn-rfc.md` (11 sistemas + 8 fases) + plano self-improvement. Reler autolearn-rfc §2.2/§2.4 antes de implementar.
- **Caminho mínimo:** (1) ~~limpar beliefs~~ ✅ já resolvido → (2) destilação ✅ (belief store já destila) → (3) feedback-loop ✅ **1º passo 3/out: negative-use** (rating −1 derruba confiança; E2E −47,8%) → (4) injeção proativa ✅ **3/out: tool `memory_context` por tema** (E2E banco vivo) + (5) **telemetria de proveito ✅ 3/out** (usage_events, migration 014 no vivo). **PRÓXIMO: janela 1 semana medindo proveito real (N1), depois push automático (N2) e feedback positivo/automático (N3).**


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
- **Radar de terceiros:** `docs/_fork/radar-terceiros.md` (PRs/issues de terceiros na nossa área)
- **Acompanhamento (fork-only):** `docs/_fork/` — roadmap, pilha de PRs, este ESTADO.md, ARCOS.md (versão densa p/ o agente).
- **Metodologia de fork:** `docs/_fork/metodologia-fork.md` (3 rituais) + `LEDGER-feats.md` (estado de cada feat) + `ORFAOS.md` (detector de trabalho não-relandado). Consultar ANTES de sync/merge/implementar feat.
- **Estudos/pesquisas/guias:** ficam no CdIA (`conhecimentos-de-ia/ferramentas/mcp/memory-service/estudos|guias`).
