# Pilha de PRs — mcp-memory-service fork (runbook)

**Criado:** 03/set/2026 · **Atualizado:** 30/set/2026 · **Estratégia:** stacked branches (breadcrumb) · **Upstream base:** `upstream/main` (GitHub, v11.14.0+)

> 📍 **SNAPSHOT 30/set (DNBSCDC289) — arco harvest multi-formato + portabilidade:** dois PRs abertos e verdes, aguardando review do Henry. **PR #1378** (discover+id+resolve sessões Kiro workspace + path guard) = **CLEAN** (14 checks verdes, Greptile SUCCESS, 0 threads, desbloqueado). **PR #1379** (parser SQLite conversations_v2 + dimensão de idioma no Phase 0) = BLOCKED só por REVIEW_REQUIRED (verde, Greptile SUCCESS, 0 threads). Henry aprovou #1376 como 1º a mergear. Issues: #1376 (discovery) + #1377 (SQLite) abertas e amarradas ao arco. **Discussion #1364 (portabilidade):** Henry ACEITOU o modelo de 5 camadas (reconheceu que Claude Code tb tem gap camada 4 preferência + 5 toolkit). 3 compromissos HONRADOS: (1) RFC design-extraction **v0.4** (idioma reenquadrado = honrar locale via config/locale.py + patterns per-locale, NÃO fração de corpus — correção do Henry); (2) **wiki Memory-Portability-Map** criada (5 camadas × Kiro/OpenClaw/OpenCode/Hermes/Claude, 2 regras do Henry: mapa-de-trabalho + célula linka/data); (3) **issue #1390** conversor mem0 (4 pontos RFC). RFC nova **rfc-harvest-source-identity v0.1** (camada de descoberta+identificação de fonte por agente — reenquadra o "SQLite unreachable" como design, não wire-up). Doc CdIA INVENTARIO §2.5 (metadados identidade CLI/IDE/Crew). **ATENÇÃO issues novas do Henry (nossa área rating/quality):** #retention_periods keys mismatch + quality ~no effect on decay (30/set); MCP_DECAY_ENABLED no effect (29/set) — AVALIAR. Commits fork: I0-lang a44d968b, RFC v0.4 6b16370b, source-identity 3b8ccaa1. main fork em dia com upstream.

> 📍 **SNAPSHOT 28/set (DNBSCDC289):** **PR #1365 ABERTO** (fix #1363 health checkers off-lock — rotear via _run_in_thread, padrão #1344): CI 14/14 verde + Greptile pass, MERGEABLE, aguarda Henry. Feito por pipeline TDD (dev-tests G3→dev-python G4→reviewer G5 APROVADO). #1225 FECHADO pelo Henry com base no nosso comentário de produção. Discussion #1364 (arco portabilidade) aberta. **#1349 (quality split #1312) MERGEADO pelo Henry** (28/set 03:07, upstream 97e699e0) — arco rating/quality-model ENTREGUE. main do fork mergeada com upstream (7 commits), **ahead 62 / behind 0**, pushada github (98461cf9), backup/main-pre-1349merge-20260928. Suíte quality 6/6 verde. **FILA HENRY VAZIA.** Próximo alvo: H1 #1225 (avaliar) ou D3 (query-intent). Worktree ~/git/mcp-memory-service-pr1349 pode ser removido (mergeado).

> 📍 **SNAPSHOT 27/set NOITE:** pilha quase esvaziada. **#1348 MERGED** (versioned/superseded). **#1350 MERGED** (harvest coverage instrument — fix per-block counting + deep-copy). **#1349 READY, aguarda Henry** (quality split — fix final: boost retention-only, não reescreve quality_score; commit fc88bebf, CI 14/14, 395 testes verdes). **RFC #1345 v0.3** (4 invariantes do @ducanhnguyen223, branch doc/rfc-delta-sync-invariants). RFC #1346 sem novos comentários. ⚠️ **github/main behind 60 do upstream/main** — precisa merge do upstream na main do fork (linha fork-only) numa próxima sessão. Worktrees ativos: ~/git/mcp-memory-service-pr1349 (branch feat/quality-model-split), ~/git/mcp-memory-service-rfc (doc/rfc-delta-sync-invariants), ~/git/mcp-memory-service-pr1350 (mergeado, pode remover). Fila Henry: só #1349 + review RFCs.


> ⚠️ **NOTA 25/set:** este runbook acumula camadas de 03→15/set (seções §Ambiente v11.5.5, §Atualização do SERVIÇO v11.11.0 estão OBSOLETAS — main já é v11.14.0). O worktree `~/git/mcp-memory-service-dev` **não existe mais** nesta máquina (recriar se retomar pilha de PRs). Fila upstream VAZIA. Estado corrente e roadmap: ver `EPICOS-roadmap.md` (snapshot 25/set) e AGENTS.md §Estado da main.

> Runbook para retomar o transporte de features do fork → upstream.
> ✅ MIGRAÇÃO CONCLUÍDA (05/set): **GitHub é a ORIGEM** (CI, releases, wiki, Discussions).
> Codeberg CONGELADO (read-only, sem Actions). PRs e RFCs vão para o **GitHub**.
> Topologia: https://mcpmemory.services/deployment/ — sinal verde para abrir PRs.
> 📍 **Roadmap de épicos (visão total):** `EPICOS-roadmap.md` (26 épicos, árvore, esforço/dificuldade).

## 📋 Estado dos RFCs #1008 / #1047 / #1050 (avaliado 15/set vs upstream v11.12.0)

Os 3 foram fechados `not_planned` no GitHub por **bookkeeping de migração** (Henry, 22/ago: *"It did not stall, it moved"*), NÃO por rejeição. Dupla migração GH→CB (mai)→GH (set) deixou rastro órfão no Codeberg congelado (#55/#56/#121/#250). Verificado no CÓDIGO do upstream v11.12.0 o que realmente shippou:

| RFC / seção | upstream v11.12.0 | Trabalho? |
|-------------|-------------------|-----------|
| #1008 composite #55 | ✅ `scoring/composite.py` | — |
| #1008 two-phase #56/#61 | ✅ `handlers/graph.py` (memory_explore/detail, do PR #78) | — |
| #1008 multi-store #57 | ✅ `storage/base.py` partition | — |
| #1008 NLI 3-camadas | ✅ `reasoning/nli.py` + `nli_patterns/` | — |
| #1047 §1 observation store | ✅ (test_observation_store) | — |
| #1047 §2 belief store | ✅ `belief_service.py` + migration 012 | — |
| #1047 §3 autolearn/autodream | ✅ `DreamInspiredConsolidator` (consolidator.py) | — |
| #1047 §4 bootstrap profile | ✅ `handle_get_bootstrap_profile` (server_impl 2417) | — |
| #1047 §5 death rattle | ✅ `handle_commit_session_legacy` (server_impl 2144) | — |
| #1047 §7 MCP tools | ✅ commit_session_legacy, get_bootstrap_profile (registry) | — |
| #1050 harvest background | ✅ `_schedule_harvest_job` (nosso #1241, MERGED) | — |
| #1047 §6 anti-halluc | ⚠️ parcial — sem `abstain`/insufficient-evidence explícito no retrieve | avaliar (menor) |
| **Trilogia RFC-MM** (fact-extraction / gap-detection / feedback-loop) | ❌ **AUSENTE** (migrations 013/014/015, tools memory_facts/memory_gaps) | **SIM — único trabalho real (Onda 2)** |

**Veredito:** ~95% dos 3 RFCs já está no upstream. Sobra: (1) **Trilogia RFC-MM** = Onda 2 (ver §Atualização do SERVIÇO; código em `2e1978d5`, precisa OK do Henry #67 e reescrita sobre v11.12.0); (2) §6 anti-halluc parcial (menor, avaliar se vale). `memory_context` (#120) morto (não existe em nenhum lado). Memória-âncora: `9b4b555e`.


## 🏗️ DECISÃO 14/set — Reorganização do fork (EXECUTAR à noite com sirdata)

Modelo novo (substitui o "irmãs do upstream" descrito em §Atualização do SERVIÇO):
```
upstream/main ──→ pr/<feat> [→ pr/<feat-empilhada>] ──(Henry mergeia)──→ upstream/main
                                              │ (merge periódico do upstream)
                                              ▼
                                          fork/main  ← LINHA VIVA (serviço roda daqui)
```
- **fork/main = upstream/main + camada nossa** (docs/rfc, docs, specs, feats fork-only). Serviço roda daqui.
- **pr/<feat> sai do upstream/main** (PR limpo). Feat aprovada volta ao fork/main via **MERGE do upstream** (opção a), NUNCA cherry-pick (evita duplicata).
- **rfc/docs/specs habitam SÓ no fork/main** — fim do espalhamento.
- **Execução:** promover `service`→`fork/main`; `main` legado (15820dda) → `backup/main-legacy-v11.5`; consolidar 17 RFCs (7 locais + 10 github/docs/rfc-mnemosyne-agent-id + harvest-provenance/agent-id do sirdata; commit sirdata 25d94331 ainda NÃO no GitHub); push fork/main. Detalhe em AGENTS.md §DECISÃO. NÃO executar sem alinhar com o sirdata.

## Ambiente (isolado do serviço)

- `~/git/mcp-memory-service/` → branch `main` = **v11.5.5** (fork), CASA com o serviço systemd em produção (PID vivo, editable venv). **NÃO mexer.**
- `~/git/mcp-memory-service-dev/` → worktree, onde a pilha vive. Base = `upstream/main` (v11.11.0, GitHub). Pilha precisa REBASE sobre v11.11.0 (+66 commits desde v11.10.0).
- `backup/main-fork-2026-09-02` → rede de segurança dos 29 commits originais do fork.
- `wip/onboarding-particionamento-doc` (`98fff3d4`) → edição do onboarding (regra de particionar). Entra junto com a feature #5 (store→NER). **Era um stash volátil, agora é branch durável.**
- Remotes: `upstream`=**GitHub** doobidoo (ORIGEM, fetch-only) · `upstream-cb`=Codeberg (congelado, fetch-only) · `github`=fork filhocf GitHub (push aqui) · `codeberg`=fork CB (opcional). Push só nos forks.

## Estado da pilha (breadcrumb)
**Estado em 15/set 11:45 (verificado no GitHub):**

> Reorg do fork CONCLUÍDA (15/set): `github/main` = LINHA VIVA = upstream v11.12.0 + camada fork-only + 19 RFCs. Serviço roda dela. Gestão viva: cada PR nosso mergeado no upstream → `git merge upstream/main` na main (substitui fork-only pela oficial). Memória ea1d1e35.

> **Atualização 23/set (sirdata):** agent_id **Fase 2** implementada e na linha viva. PR **#1297** ABERTO no upstream (filtro opt-in agent_id em search/list + header X-Agent-ID no /mcp; unificado metadata.agent_id OR tag agent:<id>; sqlite-only; Greptile 3 P1 resolvidos; CI verde). fork/main mesclado: `git merge upstream/main` (drift #1288/#1291/#1295) + `git merge feat/agent-id-phase2` → HEAD `bdc4d215`, agora **v11.13.0 + Fase 1 + Fase 2**. Serviço :3202 de pé, suíte só com as 8 ambientais CUDA. Backup: `backup/main-pre-fase2-20260923`. **DESTRAVA o delta-sync** (agent_id confiável via header per-request = R6 da RFC delta-sync). PRÓXIMO: atualizar VPS (v11.3.3 → fork/main atual) para praticar o delta-sync caseiro (Caminho A + pé no B).

> **Atualização 24/set (sirdata):** PR **#1297 MERGEADO** pelo Henry (05:38Z) — Fase 2 agent_id oficial no upstream v11.13.0. Fila upstream **VAZIA** (0 PRs abertos nossos). **Canal hub VPS FEITO** (fora da pilha, é infra): defesa 2 camadas nginx `location /memory/` (auth_basic+htpasswd) + API key nativa do serviço (`MCP_API_KEY`), E2E validado de sirdata. Doc: `SPEC-hub-memoria-centralizada.md §12`. GOTCHA registrado: com auth_basic no nginx, cliente usa **X-API-Key** (NÃO Bearer — auth_basic ocupa o header Authorization).

### 🔍 #1301 — OAuth 2.1: API-Key auth broken (Henry pediu OPINIÃO 24/set)

**Escopo:** `web/oauth/` = web layer, **FORA do meu mandato de merge** (mandato = quality/ + handlers/ + harvest). Henry pediu OPINIÃO, não merge.

**Análise (li `web/oauth/middleware.py:get_current_user` + `web/api/health.py`):**
- O **dual-auth que Henry propõe como solução JÁ EXISTE**. Ordem em `get_current_user`: (1) Bearer OAuth se `OAUTH_ENABLED` → **fallback API-Key** (L346-348); (2) `X-API-Key` header **independente de OAuth** (L372-374); (3) `api_key` query (L380-382); (4) anonymous. API-Key **não** depende de OAuth ligado.
- `web/api/health.py`: `/health` puro = **público** (L64, sem Depends); `/health/detailed` (L75-78), `/server/status`, `/health/sync-status` = **GATED** (`Depends(require_read_access)`). Correto por design.
- **Por que quebra pra ele (2 hipóteses):** (A, provável) `MCP_API_KEY` ausente no ambiente dele OU MCPlex/Web-UI manda key via `Authorization: Bearer` (com OAuth ligado, valida como JWT→falha; fallback API-Key só salva se `API_KEY` existir). (B) ele testou endpoint gated esperando ser público.
- **Evidência empírica nossa (hoje):** canal VPS 2-camadas confirmou que `X-API-Key` funciona independente de OAuth (é o fallback L372). Reforça hipótese A.
- **Impacto no roadmap:** nosso delta-sync (D7) usa X-API-Key camada 2 — o código mostra que OAuth **não** desliga API-Key → nosso canal está seguro. Vizinhos temáticos: #1117 (SSE auth), #1231 (disable auth).
- **Opinião a dar:** o design dual-auth existe; provável má-config/via-do-cliente, não bug estrutural. Pedir: `MCP_API_KEY` está setado? qual header o MCPlex manda? qual endpoint exato deu 401? Sugerir doc clarificando (X-API-Key é a via recomendada com OAuth ligado) + eventual melhoria de mensagem de erro. NÃO é redesign.

MERGEADOS no upstream (drenados):
```
✅ #1215 NLI cascade · ✅ #1234 backoff · ✅ #1240 last_accessed · ✅ #1241 scheduled harvest
✅ #1242 ONNX (+#1245 docs) · ✅ #1244 fix lifecycle (Henry) · ✅ #1248 ProtectMain (Henry)
✅ #1243 harvest PROVENANCE (e8960ebf, 15/set 13:02Z) — Henry aprovou "well built", mergeou.
   2 follow-ups não-bloqueantes na review → foram para o #1252 (mesmo harvester.py).
```

ABERTOS — board VERDE, aguardando review do Henry (mergeable_state=blocked = precisa 1 approval):
```
🟢 #1250 fix(ci) release-bump exemption [pr/release-bump-exemption @ d0faa684] — closes #1247.
   Predicado is_release_bump.py (espelha #1147 cleanup-only) + 2 gates + teste. Rebaseado sobre upstream.
🟢 #1252 feat(harvest) verify_session_coverage (R11/R12) [pr/verify-session-coverage @ a88eeede] — split 1 do #1243.
   Método + 4 unit + E2E real (MCP_E2E_LLM opt-in) + doc. ENGATOU os 2 follow-ups do #1243:
   evolve provenance (harvest:method no _try_evolve) + comment do HARVEST_PIPELINE_VERSION. Doc no mesmo commit.
```

FILA — não publicados (1-PR-por-vez, abrir quando a fila liberar):
```
PRONTOS (branch com código testado):
  ⏳ feat/nli-observability → #1235 NLI reuse+observabilidade. G5, 33 testes, E2E real. RFC-nli na main.
  ⏳ feat/agent-id → #1100 F1 agent_id. Draft pronto. Ortogonal.

ANOTADO (código no backup, branch a montar — DEPOIS que #1252 mergear, mesmo harvester.py):
  📋 re-harvest safety → item c5a86779. Agora ENXUTO (os 2 follow-ups já saíram p/ #1252). Resta:
     (1) remover scripts/r10_mass_reharvest.py; (2) expor/internalizar force_reharvest no schema
     memory_harvest; (3) sessions_to_track found==0 vs falha; mover p/ harvest/; sem CHANGELOG. Doc junto.
```

Os 3 assuntos do #1243 ORIGINAL → destinos FINAIS: provenance = #1243 ✅ MERGED; verify_session_coverage
= #1252 🟢 aberto (+ os 2 follow-ups); re-harvest = c5a86779 (fila, pós-#1252).

FLUXO (em vigor): PR sai de `upstream/main` limpo. Feat mergeada volta à `main` via `git merge upstream/main`
(NÃO cherry-pick). E2E real obrigatório antes de PR. Doc no MESMO commit (anti-drift). >1 arquivo → gate.

**Histórico (pilha original v11.10.0 — já drenada):**
```
 └─#1 feat/nli-cascade ✅ (#1215)  └─ harvest-104 ✅ (#1234/#1240)  └─ scheduled-harvest ✅ (#1241)
```

## Ordem e racional

| # | Branch | Commits fonte | Natureza | PR alvo |
|---|--------|---------------|----------|---------|
| 1 | feat/nli-cascade | `ff28cac4` (só NLI, sem o memory_context acoplado) | isolado (nli.py) | #116 |
| 2 | feat/harvest-104 | `53584bf6` + `ad17ff34` | colidem em harvester.py — juntos | #104 |
| ~~3~~ | ~~feat/kiro-ide-parser~~ | `d017a1d4` | ⏭️ PULADA — defasada (formatos mudaram). Vira o **parser multi-formato** do ARC de ingestão retroativa (CLI v3 + IDE payload + session.json + crew) | — |
| 4 | fixes-pequenos | `cd86a4cb` (BeliefService bootstrap), `7d4c8dec` (harvest fallback path) | server_impl.py | fixes diretos |
| 5 | feat/store-ner | reescrever `a5ba6c72` + `f1ed2596` + `wip/onboarding-particionamento-doc` | **reescrita** (não cherry-pick) | #54 / spec |

Racional da ordem: menos dependência primeiro + isolamento de arquivos + probabilidade de aceite. NLI primeiro (isolado, Henry já quer #116). Store→NER por último (é reescrita, é o que Claudio mais usa localmente → fica na ponta).

## Protocolo de saúde (regressão) — a cada branch nova

1. Implementar a feature.
2. Rodar testes DA feature: `.venv/bin/python -m pytest tests/test_<feature>.py -q`
3. Regressão da área vs baseline: `pytest tests/ -q -k "harvest or nli or reasoning or belief"` → deve dar ≥336 passed, 0 falhas.
4. Só então criar a próxima branch em cima.
- Interpretador: usar `~/git/mcp-memory-service/.venv/bin/python` (mesmo do serviço).

## ⭐ Disciplina de transporte (regra do Claudio, 03/set)

1. **SEMPRE VERIFICAR o upstream antes de transportar** — não assumir que falta, não assumir que já tem. Checar `arquivo:linha`. (Evita "submeter fix que upstream já tem".)
2. **REESCREVER, não cherry-pick cru** — o upstream andou muito (v11.5.5→v11.10.0). Cherry-pick só quando aplica limpo; senão, reescrever a feature sobre o código atual (ex: NLI adaptado ao `_call_llm`, store→NER como DomainExtractor).
3. **Seguir o GATE** (dev-workflow): G0 arch investiga → G3 testes RED → G4 implementa GREEN → G5 review. TDD, não improviso.

## Notas de reescrita — feature #5 (store→NER), a mais delicada

- **NÃO cherry-pick cru** de `a5ba6c72` (modificava assinatura de extract_entities — incompatível com upstream).
- Criar `StoreTermsExtractor(DomainExtractor)` que lê `store_terms.json` (`{store:{locale,terms[]}}`) e satisfaz o Protocol de `reasoning/entities.py:22`.
- Propagar `store` **via metadata** (os 3 callers já têm o store em mãos: memory_service.py:771, graph.py:159, quality.py:568) — sem alterar assinatura pública.
- Registrar via `MCP_ENTITY_EXTRACTOR_MODULES`. É o "plugin zero" do #54 (spec `specs/multi-store-domain-ner-spec.md`).
- `bde5bf43` (fix NER min 3 chars) precisa readaptação ao YAML novo — tratar aqui, não transportar direto.

## FORA da pilha inicial

- **Trilogia RFC-MM** (`2e1978d5`: feedback-loop/fact-extraction/gap-detection) — grande, depende de OK do Henry (#67). Pilha própria ou PR isolado depois.
- 13 commits FORK-ONLY — não transportar (bootstrap fork-only, docs T'Pol/RFC, cleanups, índice codebase-memory).
- Confirmar duplicidade antes de PR: `775fc41d` (memory_context vs #120), `53dc9559` (temporal decay vs #123).

## Quando o Henry migrar (fluxo de PR)

1. ✅ GitHub confirmado como origem (05/set). fetch `upstream` (=GitHub).
2. Push `feat/nli-cascade` → PR #116 no GitHub (base: upstream main).
3. Após merge do #1 → rebase da cadeia sobre o novo main → PR #2 → e assim por diante.
4. Cada rebase encolhe (a feature anterior já entrou).

## 🚀 Atualização do SERVIÇO — v11.5.5 → v11.11.0 + fork feats (branch `service`)

> Diferente da pilha de PRs (que é CONTRIBUIÇÃO upstream). Isto é o SERVIÇO que
> RODA localmente e usa memória. Objetivo: rodar "v11.11.0 + nossas feats" com venv leve.

### Desenho: branch `service` (irmã do upstream, NUNCA vira PR)

```
upstream/main (Henry, v11.11.0) ──┬── service     ← NOSSA linha. Serviço roda daqui.
                                   │                 = v11.11.0 + baldes b+c + AGENTS nosso
                                   └── feat/NNNN    ← PRs limpos (saem do upstream/main, NÃO da service)
```
- `service` e `feat/NNNN` são IRMÃS do upstream, não `main→service→feat` (senão o feat carregaria
  nossos AGENTS/plugins e vazaria no PR do Henry).
- Quando o Henry mergeia uma feat → ela entra no upstream → no próximo rebase da `service`, some
  da nossa dívida (vira upstream). A `service` encolhe sozinha.
- Casa física: **repo principal `~/git/mcp-memory-service`** vira a casa da `service` (Opção 1).
  venv + systemd atuais já apontam pra cá — não muda path. O `main` v11.5.5 fica como rollback.

### Inventário REAL de absorção (verificado 11/set na branch service vs v11.11.0)

JÁ ABSORVIDO pelo upstream (grátis, NÃO trazer):
- harvest rewrite_batch (#1185 mergeado) · Kiro IDE parser (parser.py) · bootstrap noise/specificity
  filters (server_impl.py) · NER multilingual + locale + ner_patterns + nli_patterns · temporal decay
  (v11.11 tem consolidation/decay.py dedicado, melhor que nosso patch em retrieve.py — descartar o nosso).

FALTA (não absorvido) + VEREDICTO de uso (quem usa é o agente):
1. **NLI cascade** (backend LLM em nli.py) — v11.11 só tem heuristic. USO SIM. = PR #1215. Aplicar o mesmo patch no serviço.
2. **Trilogia RFC-MM** (facts/gaps/feedback) — módulos+handlers+tools+migrations 013/014/015 FALTAM.
   USO INDIRETO mas valioso: roda em BACKGROUND via scheduler.py (fact_extraction 6h, feedback_recalc 6h,
   gap_detection automático). Enriquece a memória consultada. Maior massa, MAIOR conflito (scheduler/consolidation mudaram muito).
3. **Store-NER** (data/store_terms.json + patch entities.py) — FALTA. USO SIM (termos MIR/RER). Reescrever.

### Plano em 2 ONDAS (serviço sobe cedo e seguro)
- **Onda 1 (hoje):** NLI cascade + Store-NER (isolados, uso direto). Serviço → v11.11 + essas 2.
- **Onda 2 (depois):** Trilogia RFC-MM (massa maior, conflitos scheduler/consolidation; como roda em
  background, serviço funciona sem ela no intervalo).

### Os 3 baldes (auditoria 11/set dos 39 commits fork sobre v11.5.5)

- **(a) já-no-upstream** → grátis no v11.11.0, não transportar. Ex.: harvest rewrite_batch (#1185 mergeado).
- **(b) extensões/plugins** (arquivos NOVOS, Added, zero conflito) — copiar + ativar por env:
  `extraction/` (facts, multilingual, ner_patterns), `feedback/tracker.py`, `config/locale.py`,
  `reasoning/nli_patterns/`, `server/handlers/facts.py` + `gaps.py`, migrations 013/014/015,
  YAMLs pt_BR/en, `data/store_terms.json`. Ativar: `MCP_ENTITY_EXTRACTOR_MODULES`, `MCP_NLI_BACKEND=cascade`.
- **(c) patches de core** (11 arquivos Modified que colidem com upstream) — reaplicar 1 a 1 + testar:
  `nli.py`, `entities.py`, `harvester.py`, `belief_service.py`, `scheduler.py`,
  `handlers/{memory,graph,consolidation}.py`, `server_impl.py`, `services/memory_service.py`,
  `storage/mixins/retrieve.py`, `tools/registry.py`. (Vários migram p/ (a) conforme viram PR.)

### venv ONNX-only (decisão §11 torch-optional, commit feat/s11-torch-optional)

- O venv atual tem 5,0G: nvidia 2,7G + torch 1,1G + triton 690M = **~4,5G de gordura de GPU** por engano.
- Decisão: **ONNX-first** (onnxruntime 52M) — sem torch, sem CUDA. Serviço NÃO usa GPU.
- venv da `service` = instalar SEM o extra ml pesado. Alvo ~500M em vez de 5G.
- Limpar torch/nvidia/triton libera ~4,5G de disco.

### Sequência de migração (segura, rollback trivial)

1. `git branch service upstream/main` (v11.11.0) — NÃO mexer no main que roda.
2. Balde (b): copiar arquivos novos + ativar por config.
3. Balde (c): reaplicar 11 patches de core (cherry-pick/reescrita + resolver conflito), testar cada.
4. venv ONNX-only: `uv sync` sem ml pesado; validar embeddings via onnxruntime + sqlite-vec.
5. Rodar testes do fork (test_domain_ner, test_nli_llm, test_belief_pipeline_e2e, test_harvest_*).
6. **Backup do banco** (VACUUM INTO) + migrar (013/014/015 fork + novas upstream).
7. Virar: `git checkout service` no principal + reinstall editable + `systemctl --user restart memory-service`.
8. Validar serviço vivo (memory_search). **Rollback = `git checkout main` (v11.5.5) + restart.**
9. AGENTS.md "START HERE" versionado na `service` (aponta skill + este runbook + regras Henry + nosso SDD).

### Dois modos de trabalho (NÃO confundir)
- **DESENVOLVER nossas feats** → nosso método SDD/G0-G6 (DEVELOPMENT-STANDARDS.md do CdIA §0).
- **TRANSPORTAR para upstream/PR** → método do Henry (board verde, tests-prove-fix, squash+#PR,
  1 review dele, 1 PR/vez). Ver skill `memory-service-maintainer`.

## Referências

- Reconciliação completa: `RECONCILIACAO-v11.10.0.md`
- Rastreador: `REFERENCE-MEMORY-PIPELINE.md` §12
- Spec store→NER: `specs/multi-store-domain-ner-spec.md`
- Memórias: tags `mcp-memory-service,pilha` (hashes dos commits + conflitos resolvidos)
