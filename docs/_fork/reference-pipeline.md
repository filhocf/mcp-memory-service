# Referência: Pipeline de Memória Agêntica — mcp-memory-service

**Data:** 2026-07-18 (sirdata)
**Propósito:** Documento de referência para qualquer sessão/arch-analyst que precise entender o sistema completo, diagnosticar problemas e propor soluções.

---

## 1. O Problema Central

O Kiro CLI é um agente efêmero — cada sessão nasce sem estado. O mcp-memory-service existe para resolver isso: dar contexto persistente entre sessões.

**Estado ideal:** Agente inicia sessão "quente" — sabe o que fez ontem, conhece decisões recentes, evita erros já cometidos, entende o contexto do usuário.

**Estado real:** Agente inicia "frio" — executa checklist burocrático de infra (portas, health, registry) sem carregar contexto acionável. Resultado: usuário precisa re-explicar contexto e corrigir o agente nas primeiras interações.

---

## 2. Arquitetura do mcp-memory-service

### 2.1 Componentes (módulos em `src/mcp_memory_service/`)

| Módulo | Função |
|--------|--------|
| `storage/` | SQLite-vec backend (embeddings + metadata + graph) |
| `embeddings/` | paraphrase-multilingual-MiniLM-L12-v2 (384 dims, CPU) |
| `harvest/` | Extrai candidatos de sessões JSONL (regex + LLM classifier) |
| `consolidation/` | APScheduler server-side: clustering, beliefs, decay, associations, forgetting |
| `bootstrap/` | Gera profile comportamental (avoidances, conventions, preferences) |
| `reasoning/` | NLI (Natural Language Inference) — detecta contradições |
| `quality/` | Ratings, maintain cycle, cleanup |
| `scoring/` | Composite scoring (temporal decay × quality × centrality) |
| `extraction/` | Entity extraction (NER), locale plugins (pt_br) |
| `ingestion/` | Ingestão bulk de documentos (PDF/MD → chunks) |

### 2.2 Tools MCP expostas ao agente

| Tool | Função | Quem chama |
|------|--------|-----------|
| `memory_store` | Salvar memória (observation, decision, reference, note) | Agente |
| `memory_search` | Busca semântica/híbrida/exact/ranked | Agente |
| `memory_context` | Retorna beliefs+mistakes+contexto dentro de token budget | Agente (startup) |
| `get_bootstrap_profile` | Profile comportamental (avoidances/conventions/preferences) | Agente (startup) |
| `memory_harvest` | Extrai learnings de sessões JSONL | Cron/scheduler (⚠️ BLOQUEADO no HTTP — GHSA-7crr-2r7w-cpfm, path-traversal) |
| `memory_consolidate` | Trigger manual de consolidation cycle **+ action `harvest` (sob demanda, com path)** | Agente |
| `memory_quality(maintain)` | Cleanup + conflicts + stale + quality analysis | Agente OU cron |
| `memory_explore` | Knowledge map por entidades | Agente |
| `memory_detail` | Detalhe de uma entidade específica | Agente |
| `mistake_note_search` | Busca erros conhecidos por similaridade | Agente (pré-tarefa) |
| `commit_session_legacy` | Encerramento estruturado de sessão | Agente (shutdown) |

### 2.3 Processos Server-Side (APScheduler interno)

Ativados por env vars, rodam DENTRO do processo systemd sem precisar do agente:

| Job | Frequência | Env var | O que faz |
|-----|-----------|---------|-----------|
| Consolidation daily | 03:00 | `MCP_SCHEDULE_DAILY=03:00` | Decay, clustering, associations, belief derivation |
| Consolidation weekly | DOM 04:00 | `MCP_SCHEDULE_WEEKLY=SUN 04:00` | Consolidação profunda (compression, forgetting) |
| Consolidation monthly | Dia 1 04:00 | `MCP_SCHEDULE_MONTHLY=01 04:00` | Arquivamento de memórias muito antigas |
| NLI on_store | A cada memory_store | `MCP_NLI_ON_STORE=true` | Detecta contradições ao salvar |
| Belief derivation | No scheduler daily | `MCP_BELIEFS_ENABLED=true` | Agrupa observations → gera beliefs com confidence |
| Entity linking | A cada memory_store | `MCP_ENTITY_LINKING_ENABLED=true` | Extrai entidades e cria links no grafo |

#### Time Horizons — Janelas de Processamento

Os horizons definem **quais memórias são processadas** e **quais fases rodam**:

| Horizon | Memórias processadas | Fases ativas | Tempo típico (17K mems) |
|---------|---------------------|--------------|------------------------|
| `daily` | Últimas 48h (cutoff_days=2) | Relevance scoring, clustering, belief derivation | <1s |
| `weekly` | TODAS (get_all_memories) | + compression | ~2min |
| `monthly` | TODAS | + forgetting (decay) | ~3min |
| `quarterly` | TODAS | + archival | ~5min |
| `yearly` | TODAS | TODAS as fases (completo) | 5-10min |
| `incremental` | Desde último run (tracker) | Scoring + clustering | <1s |

**Para catch-up de banco que nunca rodou consolidation:** usar `yearly`.
**Para manutenção rotineira:** scheduler automático (daily 03:00, weekly DOM 04:00).

Script catch-up manual: `/tmp/consolidation-catchup.sh`

### 2.4 Processos via Cron Externo

| Job | Frequência | Máquina | Script |
|-----|-----------|---------|--------|
| harvest-cron | 6h | DNBSCDC289 (24/7) | `scripts/harvest-cron.sh` |
| hot-backup | 30min | Todas | `scripts/hot-backup.sh` |
| backup-and-sync | 18h | Todas | `scripts/backup-and-sync.sh` |

### 2.5 Harvest sob demanda — `memory_consolidate action="harvest"` (fork, commit 0ccaf01e)

Preenche o gap: `memory_harvest` aceita `project_path` mas é **bloqueado no HTTP** (GHSA-7crr-2r7w-cpfm, path-traversal via cliente), e o harvest-cron só roda no ciclo de 6h com path fixo no env. A action roda **in-process** no servidor (usa o `MemoryService`/`storage` do próprio serviço → grafo, dedup e provenance **íntegros**, ao contrário de um script standalone que perde o `memory_graph`).

**Parâmetros:** `path` (dir de sessões), `sessions` (limite, default 50), `use_llm` (default true), `dry_run` (default false), `force_reharvest` (default false — reprocessa acervo já trackeado).

**Guard de segurança (obrigatório):** o `path` vem do cliente MCP, então é confinado a um allowlist. `resolve()` colapsa `../` e symlinks, depois exige que o path esteja sob um root permitido (`is_relative_to`). Roots configuráveis via env `MCP_HARVEST_ALLOWED_ROOTS` (`:`-separado); **default fechado**: `~/.kiro`, `MCP_HARVEST_SESSION_DIR`, `~/local-data`. Path fora → erro `outside allowed roots`, nunca chega ao `SessionHarvester`.

**Uso típico (curl no serviço :3202):**
```
memory_consolidate {action:"harvest", path:"/home/claudio/local-data/kiro-sqlite-export",
                    sessions:195, use_llm:true, dry_run:false, force_reharvest:true}
→ "Harvest (STORED) from <path>\nsessions: N | candidates: C | stored: S"
```

**Usado em 28/set/2026** para resgatar as 195 conversas do SQLite CLI (dez/25–jun/26) que só existiam no `data.sqlite3` — 37 memórias com grafo íntegro. Torna trivial resgatar os outros acervos (backup 2039 payload-wrapped, etc.): basta apontar o `path`. Validado por gates arch+dev-tests+reviewer (16 testes, incluindo bloqueio de path-traversal/symlink).

---

## 3. Pipeline Completo: Da Sessão ao Bootstrap

```
SESSÃO KIRO CLI
    │
    ├── [DURANTE] Agente faz memory_store (observations, decisions, checkpoints)
    │       → NLI on_store detecta contradições
    │       → Entity linking extrai entidades
    │
    ├── [ENCERRAMENTO] Agente deveria executar shutdown-hook:
    │       → commit_session_legacy (estruturado)
    │       → memory_harvest (extrai da sessão atual)
    │       → mistake_note_add (erros ≥2x)
    │       → quality ratings (≥3/sessão)
    │
    └── [SESSÃO MORRE] → JSONL permanece em disco

POST-SESSÃO (server-side, sem agente):
    │
    ├── [CRON 6h] harvest-cron.sh → processa JSONLs no disco
    │       → PatternExtractor (regex) → candidatos
    │       → LLM Classifier (Groq/DeepSeek) → tipo + confiança
    │       → Rewriter → extrai {pattern, wrong_action, correct_action}
    │       → memory_store com tags (session-harvest, learning/bug/decision/convention)
    │
    ├── [SCHEDULER DAILY 03:00] APScheduler consolidation:
    │       → SemanticClusteringEngine → agrupa memórias similares
    │       → BeliefService.derive_beliefs() → observations → beliefs com confidence
    │       → DecayEngine → reduz relevance de memórias não acessadas
    │       → AssociationEngine → cria edges no grafo
    │       → ContradictionDetection → NLI entre beliefs × novas observations
    │
    └── [PRÓXIMO STARTUP] Agente chama get_bootstrap_profile:
            → Lista mistake_notes (type=mistake, confidence>0.7) → avoidances
            → Lista observations (type=user_correction) → preferences
            → Lista observations (type=decision) + harvest (type=convention) → conventions
            → Lista beliefs (status=active, confidence>0.5) → conventions extras
            → Formatter (KiroFormatter) → markdown com ❌/✅/📌
            → Retorna ao agente como contexto comportamental
```

---

## 4. Problemas Diagnosticados

### 4.1 Bootstrap Profile — Estado v11.5.0 (testado 18/jul/2026)

**Melhorias vs v11.4.0:**
- Beliefs (🧠) agora aparecem no profile
- task_summary aceito (seção "Contexto da Tarefa")
- Noise filter parcial funciona (rejeita alguns tipos)

**Problemas remanescentes (output real do teste):**
- Duplicação: mesmas beliefs aparecem em "Convenções" E em "Crenças"
- Session dumps passam: `"Session: c66807e1... Task: Pronto..."` — commit_session_legacy vira belief
- Conteúdo hiper-específico sem valor genérico: commit hashes, DNS gateway SP, canvas Obsidian
- task_summary não filtra por relevância (retorna tudo, não prioriza por semântica da task)

**Root cause remanescente (fork-only):**
- `_is_useful()` em belief_service.py não rejeita: session-legacy, commits específicos, logs operacionais
- Bootstrap handler lista beliefs sem scoring por actionability
- Dedup entre convenções e beliefs não implementado no formatter

### 4.2 O que v11.5.0 JÁ resolveu (era P1/P2/P3 do arch)

| PR upstream | Fix | Status |
|-------------|-----|--------|
| #127 feat(bootstrap): inject beliefs + task_summary | Beliefs no profile + task contexto | ✅ Mergeado |
| #124 fix(beliefs): semantic grouping + noise filter | _group_observations semântico 0.85 | ✅ Mergeado |
| #126 fix(consolidation): restore include_embeddings | Clustering funcional | ✅ Mergeado |
| #123 feat(retrieve): conditional temporal decay | Decay opt-in | ✅ Mergeado |

### 4.3 O que FALTA (fork-only)

| Item | Onde | O que fazer |
|------|------|-------------|
| **Noise filter nas fontes 1+2** | `server_impl.py:handle_get_bootstrap_profile` | Aplicar filtro em mistake_notes e harvest memories (hoje só beliefs filtram) |
| Dedup conventions vs beliefs no formatter | `bootstrap/formatter.py` KiroFormatter | ✅ FEITO (PR #149) |
| Scoring por relevância à task_summary | `server_impl.py` | ✅ FEITO (fork-only, Fix 4 — atua só em beliefs) |
| Gate commit_session_legacy → beliefs | `belief_service.py` | ✅ FEITO (PR #149 + limpeza banco) |
| Specificity filter (git SHAs, IPs, UUIDs) | `belief_service.py:_is_noise()` | ✅ FEITO (fork-only, Fix 3) |

### 4.4 Descoberta: 3 Fontes de Dados do Bootstrap Handler

O `handle_get_bootstrap_profile` puxa dados de **3 fontes independentes**, cada uma com filtros diferentes:

```
FONTE 1: mistake_notes → seção "Regras de Evitação" (❌ NUNCA)
  Query: list_memories(memory_type="mistake")
  Filtro: metadata.confidence > 0.7 OR frustration_score >= 3 OR is_avoid_rule
  Problema: SEM noise filter. Checkpoints de sessão e handoffs passam.

FONTE 2: harvest memories → seção "Convenções" (✅ SEMPRE)
  Query: list_memories(memory_type=convention/decision/bug/learning, tags=["session-harvest","memory-distill"])
  Filtro: len(content) > 20
  Problema: SEM noise filter. Sessões inteiras armazenadas como "convention" passam.

FONTE 3: beliefs → seção "Crenças" (🧠)
  Query: BeliefService.get_beliefs(status="active", min_confidence=0.5)
  Filtro: _is_noise() + specificity patterns + task relevance scoring
  Problema: ✅ RESOLVIDO — noise filter funciona aqui.
```

**Resultado real testado (18/jul/2026):**
- Seção Crenças: LIMPA (Fix 1-4 funcionaram)
- Seção Avoidances: POLUÍDA (checkpoints, sessões inteiras como mistake_notes)
- Seção Conventions: POLUÍDA (sessões harvest sem filtro de qualidade)

### 4.5 memory_explore — FUNCIONAL (fix 21/jul/2026)

**Problema original (18/jul):** memory_explore retornava entidades genéricas (MEMORY.md, mcp.json) ou vazio. Causa: entity linking dependia apenas de store_terms.json e CUSTOM_TERMS env var — insuficiente para descobrir entidades semânticas.

**Fix aplicado (21/jul):** DomainExtractor PT-BR + EN implementados como plugins via MCP_ENTITY_EXTRACTOR_MODULES:
- `extraction/domain_pt_br.py` — PtBrDomainExtractor (quoted terms, contextual nouns, gov acronyms, CamelCase services)
- `extraction/domain_en.py` — EnDomainExtractor (quoted terms, contextual nouns, CamelCase services)
- Re-link executado: +30.067 entity links novos (89.652 total, era 70.619)
- Top entities: Roma Connect(2258), MIR(889), Dataprev(745), SICAR(488), SIGEF(305), RER(237)

**Estado:** funcional. Toda memória nova salva a partir de 21/jul tem entity links com NER PT-BR.

---

## 5. O Que Funciona (validado 19/jul/2026)

### Startup "quente" ✅
- 3 buscas contextuais (cross-machine + hostname + mistakes)
- memory_explore dos 3 temas ativos (entity map)
- Testado em sessão limpa — agente começa com contexto real

### Bootstrap profile ✅ (parcial)
- Beliefs limpas (107 ativas, session dumps removidos)
- Fontes 1+2 (avoidances/conventions) com semantic search + noise filter
- Duplicação eliminada (PR #149)
- Limitação: fontes 1+2 ainda puxam harvest memories medianos

### Entity graph ✅
- 9.214 has_entity edges (backfill feito)
- 21.791 shares_entity edges
- 35.221 related edges
- memory_explore retorna entidades com chunks relevantes
- memory_graph(connected) navega conexões
- memory_graph(suggest) recomenda relações
- Bug prune corrigido (issue #150 upstream)

### Sync multi-máquina ✅
- **restore-db-from-sync.sh** com safeguard (substituiu merge-delta em 21/jul/2026)
- Score composto: memories + graph×2 + beliefs (quem tem mais grafo ganha)
- Fluxo: stop service → export local-only → restore → reimport → rebuild embeddings → health check → rollback automático
- Idempotency marker + tombstone + SHA256 validation
- machine-status.json cross-machine
- merge-delta.py DESATIVADO (só copiava memories, ignorava grafo/beliefs)

### Onboarding guide ✅
- get_onboarding_guide("kiro") com fluxos reais validados
- Skill memory-service-usage.md com 4 fluxos + regras + anti-padrões

### Consolidation ✅
- Scheduler ativo (daily 03:00, weekly DOM 04:00)
- Catch-up weekly rodado (17K mems processadas)
- Beliefs candidates limpos (2125→1335, ruins superseded)

Testado em 18/jul/2026 (esta sessão):

```python
# Busca 1: Últimos 3 dias em QUALQUER máquina (continuidade cross-machine)
memory_search(query="sessão checkpoint FEITO", time_expr="last 3 days", limit=3)
→ Retorna checkpoints reais com FEITO/PENDENTE/DECISÕES

# Busca 2: Última atividade NESTA máquina (continuidade local)
memory_search(query="sessão {hostname} checkpoint", tags=["{hostname}"], limit=2)
→ Retorna último trabalho no host atual

# Busca 3: Erros conhecidos
mistake_note_search(query="{tema_provável}")
→ Retorna pitfalls relevantes
```

Essas 3 buscas em sequência geram mais valor que o bootstrap profile inteiro.

---

## 6. Solução Proposta (Startup "Quente")

### Fase 1 — Workaround imediato (sem mudar o server)

Reescrever startup-hook para usar buscas contextuais diretas:

```
1. Infra (silencioso): health, sync banco se count < backup, check-versions
2. Contexto (VISÍVEL ao usuário):
   a) memory_search("sessão checkpoint FEITO", time_expr="last 3 days", limit=3)
      → "Nos últimos 3 dias: X, Y, Z"
   b) memory_search("sessão {hostname} checkpoint", tags=["{hostname}"], limit=2)
      → "Nesta máquina, última vez: W"
   c) mistake_note_search("{tema}")
      → erros relevantes
   d) get_next_item (orchestrator)
3. Apresentar resumo compacto
```

### Fase 2 — Fix no server (médio prazo)

1. **Belief grouping semântico**: Substituir exact string match por clustering (threshold 0.85). Já sabemos como — é o Step 2 do fix de 20/jun que nunca implementamos.

2. **Filtro de observações no belief pipeline**: Excluir memory_type in (session, milestone, checkpoint) e content com prefixo "Association between". Reduz ruído → beliefs mais acionáveis.

3. **Bootstrap profile task-aware**: Passar `task_summary` ao formatter → filtrar avoidances/conventions por relevância semântica à task, não listar tudo.

### Fase 3 — Modelo definitivo (RFC Self-Service completo)

O RFC `rfc-self-service-memory-intelligence.md` já descreve a visão completa. O que falta implementar:
- §1: Advisory resource (notificação pós-consolidação)
- §3: Cross-session pattern detection
- §4: Behavioral suggestions derivados de patterns

---

## 7. Modelo Operacional por Máquina

| | DNBSCDC289 (24/7) | sirdata/socrates (on-demand) |
|--|-------------------|------------------------------|
| memory-service systemd | ✅ Sempre ativo | ✅ Ativo quando liga |
| Scheduler APScheduler | ✅ Dispara nos horários (03:00, DOM 04:00) | ⚠️ Só dispara se ligada no horário |
| harvest-cron 6h | ✅ Único executor | ❌ Não roda |
| hot-backup 30min | ✅ | ✅ (protege banco local) |
| Banco | Escritor durante semana (scheduler + harvest + sessões) | Escritor fim de semana/noites (sessões) |
| maintain (quality) | ✅ Deveria estar no cron | ❌ Não roda |

### 7.1 Problema de Sincronização (divergência de bancos)

Ambas as máquinas ESCREVEM no banco — não existe "banco canônico" simples:
- DNBSCDC289: scheduler gera beliefs/associations + harvest gera memórias extraídas
- sirdata: sessões de trabalho geram observations/decisions/checkpoints

**NÃO é seguro restaurar cegamente.** Se sirdata restaura do DNBSCDC289 na segunda-feira, perde memórias do fim de semana. Se DNBSCDC289 restaura do sirdata, perde consolidation weekly.

### 7.2 Lógica de Sync (restore-db-from-sync.sh — implementada 21/jul/2026)

```
Ao ligar máquina:
  1. Encontrar melhor fonte remota (hot.db de outra máquina via OneDrive)
  2. Calcular score composto: memories + graph×2 + beliefs
  3. Se remote score > local → RESTAURAR com safeguard:
     a. Stop memory-service
     b. Export memórias local-only (Python+JSON, evita FTS5 trigger)
     c. cp remote → local
     d. Reimport local-only (INSERT OR IGNORE)
     e. Rebuild embeddings faltantes (paraphrase-multilingual-MiniLM-L12-v2)
     f. Health check → start (ou rollback se falhou)
  4. Se local score >= remote → manter local (nós somos canônicos)
```

Proteções: SHA256 sidecar, tamanho mínimo 1MB, integrity check, PRE_RESTORE backup, idempotency marker por dia.

### 7.3 REMOVIDA — Merge Delta (obsoleto)

merge-delta.py está desativado desde 21/jul/2026. O restore-db traz o banco INTEIRO (grafo, beliefs, facts, associations) — não apenas memórias brutas. O merge-delta ficou inadequado porque ignorava o grafo (70K+ edges), tornando a máquina restaurada "burra" apesar de ter as memórias.

---

## 8. Caminho para Uso Pleno (Fases 1-4)

### Fase 1 — Startup Enriquecido (imediato)

**Status:** Parcialmente implementado (buscas contextuais OK, falta explore)

```
STARTUP ATUAL (funciona):
  memory_search(query="sessão checkpoint", time_expr="3 days")
  memory_search(query="sessão {hostname}", tags=["{hostname}"])
  mistake_note_search(query="{tema}")
  get_context() → orchestrator

PRÓXIMO PASSO (enriquecer):
  memory_explore(query="{tema última sessão}", max_entities=3)  → mapa do tema
  memory_search(..., scoring="composite")  → rankeado por recência+qualidade
```

### Fase 2 — Pré-Tarefa Automático (integrar no work-management)

**Status:** Não implementado. Precisa virar parte do fluxo de receber tarefa.

Ao receber tarefa significativa (>15min):
```
memory_context(task="{resumo}", budget_tokens=2000)  → brief automático
memory_graph(connected, hash={memória top do context})  → conexões ocultas
mistake_note_search(query="{tema}")  → erros conhecidos
```

3 chamadas que transformam o agente em "especialista" no tema antes de agir.

### Fase 3 — Feedback Loop (médio prazo)

**Status:** Infra existe (quality ratings) mas nunca é executado consistentemente.

- Memória que ajudou → rating +1 (automático após uso)
- Memória irrelevante → rating -1
- Composite scoring aprende → próxima busca melhor
- Meta: ≥3 ratings/sessão (hoje: ~0)

### Fase 4 — Advisory Proativo (visão final, RFC Self-Service)

**Status:** Conceitual. Requer consolidation rodando + mecanismo de notificação.

Consolidation descobre padrão → gera advisory resource → startup lê:
"Nova regra: tu esqueces de rodar testes antes de push no MIR (4 ocorrências)."

---

## 9. Mapeamento: Features × Quando Usar

| Feature | O que faz | Quando usar | Chamada |
|---------|-----------|-------------|---------|
| `memory_search` | Busca semântica por query | Qualquer busca de contexto | `memory_search(query, mode, time_expr)` |
| `memory_explore` | Mapa de entidades sobre um tema | Início de tarefa sobre tema conhecido | `memory_explore(query="{tema}", max_entities=5)` |
| `memory_graph(connected)` | Conexões que busca semântica não revela | Após achar memória relevante, expandir contexto | `memory_graph(action="connected", hash="{hash}")` |
| `memory_context` | Brief automático (beliefs+mistakes+context) num budget | Antes de implementar algo específico | `memory_context(task="{resumo}", budget_tokens=2000)` |
| `memory_detail` | Detalhe de uma entidade específica | Deep dive num conceito | `memory_detail(entity_id="{id}")` |
| `mistake_note_search` | Erros conhecidos por similaridade | Antes de QUALQUER tarefa | `mistake_note_search(query="{tema}")` |
| `get_bootstrap_profile` | Regras comportamentais estáveis | Cache 1x/dia no startup (camada 2) | `get_bootstrap_profile(agent_ids=["kiro"])` |
| Composite scoring | Relevância = semântica × recência × qualidade | Buscas onde recência importa | `memory_search(query, scoring="composite")` |
| Entity linking | Extrai entidades automaticamente | Infra (on_store) — alimenta explore/graph | Automático |
| Consolidation | Clustering, beliefs, decay, associations | Server-side scheduler (daily/weekly) | Automático |

---

## 10. Onboarding: Do Zero ao Raciocínio

Documentação necessária para um Kiro iniciado do zero aprender a usar o memory-service:

### Nível 0 — Instalação (infra)
- Instalar memory-service (systemd, porta 3202)
- Configurar env vars (embedding model, stores, scheduler)
- Banco SQLite-vec criado automaticamente no primeiro start

### Nível 1 — Armazenar (write path)
- `memory_store` com tags + tipo (observation/decision/reference/note)
- Convenção de tags: projeto, hostname, tipo
- Checkpoint periódico (a cada 45min ou milestone)
- `mistake_note_add` quando errar ≥2x

### Nível 2 — Buscar (read path)
- `memory_search` semântico para contexto geral
- `mistake_note_search` antes de tarefa (erros conhecidos)
- `memory_search` com time_expr para recência
- Tags como filtro (hostname, projeto)

### Nível 3 — Navegar (knowledge graph)
- `memory_explore` para mapa de entidades
- `memory_graph(connected)` para expandir contexto
- `memory_detail` para deep dive
- Composite scoring para ranking inteligente

### Nível 4 — Contextualizar (task-aware)
- `memory_context(task, budget)` para brief automático
- `get_bootstrap_profile(task_summary)` para regras comportamentais
- Integração no startup-hook (buscas contextuais)
- Integração no work-management (pré-tarefa)

### Nível 5 — Aprender (feedback loop)
- Quality ratings após usar memória (ajudou? +1 / lixo? -1)
- Harvest automático (extrai learnings de sessões)
- Consolidation (agrupa, comprime, gera beliefs)
- Distill (insights de alto nível)

### Nível 6 — Raciocinar (inteligência ativa)
- Beliefs derivados automaticamente (padrões comportamentais)
- Contradiction detection (NLI detecta inconsistências)
- Advisory proativo (pós-consolidation notifica mudanças)
- Auto-regulação (decay remove irrelevante, promote premia útil)

---

## 11. Fontes de Referência

| Documento | Path |
|-----------|------|
| RFC Self-Service Memory Intelligence | `~/git/mcp-memory-service/docs/rfc/rfc-self-service-memory-intelligence.md` |
| RFC Server-Side Lifecycle | `../rfc/planned/rfc-server-side-lifecycle.md` |
| Pipeline Harvest Quality Fix | `~/git/mcp-memory-service/docs/rfc/pipeline-harvest-quality.md` |
| RFC Harvest Provenance & Safe Re-harvest | `~/git/mcp-memory-service/docs/rfc/RFC-harvest-provenance.md` (main, EARS R1-R16; feat/harvest-provenance empilha sobre pr/scheduled-harvest) |
| Plano Autolearn/Autodream | `~/git/mcp-memory-service/docs/rfc/plano-autolearn-autodream.md` |
| Belief Store Spec (§2) | `../rfc/implemented/rfc-s2-belief-store.md` |
| Anti-Hallucination Spec (§6) | `../rfc/implemented/rfc-s6-anti-hallucination.md` |
| Bootstrap formatter code | `src/mcp_memory_service/bootstrap/formatter.py` |
| Consolidation scheduler code | `src/mcp_memory_service/consolidation/scheduler.py` |
| Belief service code | `src/mcp_memory_service/consolidation/belief_service.py` |
| Harvest pipeline code | `src/mcp_memory_service/harvest/harvester.py` |
| Bootstrap profile handler | `src/mcp_memory_service/server_impl.py:2429` |
| Env config (todas máquinas) | `~/dtp/ai-configs/services/env/memory-service.env` |

---


## 12. Acompanhamento Upstream (GitHub doobidoo/mcp-memory-service)

**Atualizado:** 09/out/2026 | **Upstream:** v11.15.0 (GitHub líder — dev, CI, issues, PRs, releases) | **Codeberg: MORTO** (aposentado; não é mais remote nem espelho). Reconciliações históricas: `reconciliacao-v11.10.0.md` (snapshot de set, Codeberg-era — NÃO é estado atual).

### ⚡ Reconciliação v11.15.0 (09/out/2026)

**Hospedagem (fonte de verdade — `git remote -v`):** `upstream` = GitHub `doobidoo/mcp-memory-service` (fetch-only, push DISABLED); `github` = fork `filhocf/mcp-memory-service` (push). GitLab é push-mirror de `main` (nunca tagueia). **Codeberg morreu** — qualquer doc que o cite como líder/espelho/remote ativo está obsoleta.

**Arco delta-sync (#1345) — multi-writer memory mesh:**

| Fase | PR | Estado |
|------|----|----|
| F1 — local sync event-log | #1478 | ✅ merged 08/out |
| F2 — deterministic ordering (HLC + resolver) | #1485 | ✅ merged 08/out |
| F3 — embedding consistency guardrail | #1487 | ✅ merged 08/out |
| F4 — pull + push transport + orchestration | #1489 | ✅ merged 09/out |
| F5 — bootstrap + event version negotiation | #1494 | ✅ merged 09/out (commit e9c9ffc6) — **fechou o RFC #1345** (CLOSED 09/out via Closes) |

**🏁 Arco delta-sync (#1345) COMPLETO** — 5/5 fases merged no upstream. RFC fechado. Deferidos RFC §5 (fora do arco): identidade cripto por spoke + privacidade shareable.

Ao mergear o #1494, o RFC #1345 fecha automático. Deferidos RFC §5 (fora do arco): identidade cripto por spoke + privacidade shareable.

**Arco #1304 (desacoplar hybrid de Cloudflare) — CONCLUÍDO:** #1469 (host stamping) #1470 (F1 list_content_hashes) #1471 (F2 HTTP secondary) #1474 (F3 capability gating) #1476 (F4 model-match) #1480 (fix CF creds). Todos merged 06-08/out.

**Arco learning-loop (#1345-família NÃO — ver RFC-MM):** L4 wiring (job recálculo quality + tool get_assertiveness_metrics + clamp) feito no FORK 05/out, em janela de medição N1. PRs ao Henry só após a janela provar valor (ADR-0005). Trilogia fact/gap/feedback resgatada, fork-only, pendente spec para virar 3 PRs (#1286).

**Backups de reconciliação (hoje):** branches `backup/fork-main-pre-reconcile-20261009`, `backup/fork-main-pre-rebase-20261008`.



### Snapshot histórico (20/jul/2026 — pré-hackathon)

**Upstream v11.5.2 | PRs mergeadas:** 22 | **Issues abertas nossas:** 5

### PRs Abertas (aguardando review Henry)

| PR | Título | Status |
|----|--------|--------|
| #152 | fix(beliefs): session-legacy noise (#121) | Aberta, aguardando review |
| #153 | docs(onboarding): Kiro CLI guide rewrite | Aberta, aguardando review |

### PRs Mergeadas (22 total, cronológico reverso)

| Versão | PRs |
|--------|-----|
| v11.5.2 | #151 (entity prune fix) |
| v11.5.0 | #127 (bootstrap beliefs) #126 (consolidation fix) #124 (beliefs functional) #123 (temporal decay) |
| v11.4.0 | #107 (NER pluggable) #105 (review fixes) |
| v11.2.0 | #77 (composite scoring) |
| v11.1.0 | #78 (two-phase aggregation) #62 (multi-store schema) |
| v11.0.0 | #49 (torch optional) #60 (Block A legacy) |
| Pré-v11 | #50 #42 #38 #37 #36 #33 #22 #20 #15 #14 #13 |

### Issues Abertas (nossas, verificado 20/jul via API)

| # | Título | State | Fork implementa? | Ação |
|---|--------|-------|-------------------|------|
| #118 | agent_id expansion | open | ❌ | Parked no #67 |
| #117 | layered embedding cache | open | ❌ | Parked no #67 |
| #116 | LLM fallback auto_capture | open | ✅ NLI cascade fork-only | Candidato PR — oferecer harvest+NLI multi-provider |
| #114 | Prometheus/OTel metrics | open | ❌ | Parked (lowest prio) |
| #113 | per-agent rate limiting | open | ❌ | Parked no #67 |

### Issues Fechadas (nossas, confirmado)

| # | Título | Como resolveu |
|---|--------|---------------|
| #150 | entity prune bug | PR #151 mergeada v11.5.2 |
| #121 | RFC beliefs | PRs #124+#127 mergeadas v11.5.0 |
| #120 | memory_context dict bug | PR incluída em v11.5.0 |
| #119 | temporal decay | PR #123 mergeada v11.5.0 |

### #67 Consolidation Window (ABERTA — verificado 20/jul)

Issue #67 está **open**. Henry NÃO fechou. Itens parked:
- #116 LLM fallback → candidato nosso (harvest + NLI multi-provider)
- #113/#114/#117/#118 → parked sem previsão
- #54 NER pluggable → RESOLVIDO via #107 (nossa PR!)
- #57 multi-store federation → schema OK (#62), retrieval federation parked

**Implicação**: feature PRs grandes precisam de OK do Henry antes. Fixes (#152) e docs (#153) podem ir direto.

### Fork-Only (não upstream, 20/jul/2026)

| Patch | Motivo fork-only | Candidato upstream? |
|-------|-----------------|---------------------|
| Bootstrap semantic search + specificity filter | Muda behavior do profile | Sim, se Henry quiser |
| Per-store domain NER (store_terms.json) | Nicho | Não |
| NLI cascade LLM (DeepSeek→Groq→Ollama) | Core do #116 | **Sim — próximo PR** |
| Harvest rewrite_batch | Parte do #116 | **Sim — próximo PR** |
| Task-relevant belief ranking | Enhancement opinado | Talvez |
| memory_context tool | Não existe upstream | Avaliar RFC |
| Belief grouping (semantic 0.85) | Opinado | Não |
| AGENTS.md, docs fork, session-miner removal | Housekeeping | Não |
| NER DomainExtractor PT-BR+EN (domain_pt_br.py, domain_en.py) | API pública (não path paralelo) | Não (usa MCP_ENTITY_EXTRACTOR_MODULES) |
| restore-db-from-sync.sh (safeguard completo) | Infra fork, não é código do service | Não |

### Backlog: O que falta implementar (4 itens)

| Item | Estado | Prioridade |
|------|--------|-----------|
| NLI multi-provider → PR upstream (#116) | Fork funcional, falta submeter PR | Alta |
| Feedback loop memória (auto-rating pós-busca) | ✅ Implementado (sirdata 20/jul, session tracker server-side) | Média |
| Fact-extraction (fatos de memórias brutas) | ✅ Implementado (sirdata 20/jul, 3.629 fatos) | Média |
| Gap-detection proativa ("procurei X, não achei") | ✅ Implementado (sirdata 20/jul, tool memory_gaps) | Média |
| Re-link periódico (rodar entity linking com NER PT-BR em batch) | Implementar como cron semanal | Média |

**Cancelados (20/jul):** advisory lock cross-session, cross-session memory sharing (merge-delta resolve).

### Regra de Contribuição

- Remotes: `github` (fork filhocf) + `upstream` (GitHub doobidoo, fetch-only). Codeberg MORTO.
- PRs SEMPRE baseados em `upstream/main` (GitHub, não no nosso `main`)
- 1 feature = 1 PR (nunca scope inflado)
- Testar CI localmente antes de abrir (`pytest -x -q`)
- Henry aceita rápido quando PR está limpa (padrão: <24h)
- #67 ABERTA — perguntar antes de enviar features grandes
- Fixes e docs podem ir sem perguntar

---

## 13. Changelog

| Data | Mudança | Impacto |
|------|---------|---------|
| 21/jul/2026 | restore-db-from-sync.sh substitui merge-delta | Sync traz banco INTEIRO (grafo+beliefs), não só memórias |
| 21/jul/2026 | NER DomainExtractor PT-BR+EN implementado | memory_explore funcional, +30K entity links |
| 21/jul/2026 | Beliefs limpas (107→90 ativas) | Bootstrap profile sem ruído OpenClaw/checkpoints |
| 20/jul/2026 | Fact-extraction, gap-detection, feedback-loop implementados | 3 features fork-only (+2808 linhas, 93 testes) |
| 20/jul/2026 | Startup-hook reescrito (7 steps Fase 1) | Cobre repos+venvs+banco+embeddings+versions |
| 19/jul/2026 | PRs #151/#152/#153 upstream | Entity prune fix mergeado, beliefs noise + onboarding aguardando |
| 18/jul/2026 | REFERENCE criado (11 seções) | Documento fonte de verdade do pipeline |