# RFC: Self-Service Memory Intelligence for Ephemeral AI Agents

**Data:** 2026-05-29 (consolidado: 2026-07-02)
**Versão:** 1.0 (consolidado)
**Autores:** Claudio Ferreira Filho (visão), Spock (ecossistema), Kiro (protocolo + feedback loop)
**Target:** doobidoo/mcp-memory-service
**Contém:** RFC principal (§1–§7), Spec de implementação (P1+P3+P4+P5+P8), Fechamento de parciais (§3+§7)

---

## Motivação

Assistentes de IA efêmeros (Kiro CLI, Claude Code, Cursor, Codex) spawnam por tarefa e morrem ao final. Não acumulam contexto entre sessões. O memory MCP server é o único componente persistente — mas hoje ele é **passivo**: armazena e recupera sob demanda, sem influenciar proativamente o comportamento do assistente.

O resultado:
- Erros se repetem entre sessões (60% de recorrência medida)
- Padrões aprendidos numa sessão não transferem para a próxima
- O assistente começa cada spawn com tábula rasa, dependendo de `memory_search` ad-hoc
- Consolidação existe mas precisa ser orquestrada externamente (pelo agente ou por cron)

**Este RFC propõe transformar o mcp-memory-service de biblioteca passiva em sistema de inteligência ativa** — que aprende, consolida, e aconselha o assistente automaticamente.

---

## Princípios de Design

1. **MCP é transporte, não política.** O server expõe dados e capacidades; o host decide quando e como injetar. Não violamos a spec.
2. **Observation Store é imutável.** Agentes efêmeros só escrevem observações. Beliefs são derivadas por consolidação governada.
3. **Erros pesam mais que acertos.** Negative learning com λ > 1 (erro pesa 3x mais que sucesso).
4. **Confidence é first-class.** Toda belief tem score, provenance, e pode ser desafiada.
5. **Anti-hallucination by design.** Separação observation/belief + probes + fresh-start sentinel.
6. **Zero breaking changes.** Tudo é aditivo ao mcp-memory-service existente.

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                    Memory MCP Server (persistente)                │
│                                                                   │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────────┐   │
│  │ Observation   │   │ Belief Store │   │ Bootstrap Profile │   │
│  │ Store         │──▶│ (governed)   │──▶│ (per-agent)       │   │
│  │ (append-only) │   │              │   │                   │   │
│  └──────┬───────┘   └──────┬───────┘   └────────┬──────────┘   │
│         │                   │                     │              │
│         │    ┌──────────────┴──────────────┐      │              │
│         │    │     Consolidation Engine     │      │              │
│         └───▶│  (scheduled + on-demand)     │──────┘              │
│              │  - Pattern detection         │                     │
│              │  - Contradiction search      │                     │
│              │  - Confidence update         │                     │
│              │  - Profile rebuild           │                     │
│              └──────────────────────────────┘                     │
│                                                                   │
│  Exposed via MCP:                                                 │
│  - Resource: memory://agent/{id}/bootstrap                        │
│  - Tool: get_bootstrap_profile(task_summary)                      │
│  - Tool: commit_session_legacy(legacy_json)                       │
│  - Notification: ResourceUpdatedNotification (post-consolidation) │
└───────────────────────────────────┬───────────────────────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │        CLI Host (Kiro)         │
                    │                               │
                    │  SessionStart:                 │
                    │    → fetch bootstrap profile   │
                    │    → inject in system prompt   │
                    │                               │
                    │  SessionEnd:                   │
                    │    → commit session legacy     │
                    │    → release                   │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │    Ephemeral Agent (LLM)       │
                    │                               │
                    │  Reads bootstrap profile       │
                    │  Executes task                 │
                    │  Reports observations          │
                    │  Cannot write beliefs directly │
                    └───────────────────────────────┘
```

---

## Seções do RFC

### §1: Observation Store (append-only)

**O que é:** Camada de escrita para agentes efêmeros. Tudo que o agente observa durante uma sessão vai para cá — sem filtro, sem julgamento.

**Tipos de observação:**
- `decision` — escolha feita pelo agente ("Usei jose em vez de jsonwebtoken")
- `error` — falha com contexto (tool, mensagem, count, severidade)
- `user_correction` — usuário corrigiu o agente (sinal forte)
- `tool_outcome` — resultado de tool call (sucesso/falha)
- `preference_signal` — preferência implícita ou explícita

**Propriedades:**
- Append-only, imutável após escrita
- Cada observação tem: `session_id`, `agent_id`, `timestamp`, `type`, `content`, `context_signature`
- Agentes efêmeros SÓ escrevem aqui — nunca no belief store ou bootstrap profile

**Implementação:** Extensão do `memory_store` existente com `metadata.source = "observation"` e novo tipo `observation`. Compatível com o auto-capture (RFC #1008 §3) já implementado.

---

### §2: Belief Store (governed, versionado)

**O que é:** Conhecimento causal derivado de observações. Só atualizado pelo Consolidation Engine, nunca diretamente por agentes.

**Estrutura de uma belief:**
```json
{
  "belief_id": "uuid",
  "content": "User prefers argon2 over bcrypt for password hashing",
  "confidence": 0.85,
  "evidence": ["obs_123", "obs_456", "obs_789"],
  "contradictions": ["obs_234"],
  "error_count": 0,
  "frustration_score": 0.0,
  "source_type": "user_correction",
  "first_seen": "2026-05-20",
  "last_confirmed": "2026-05-29",
  "status": "active"
}
```

**Status possíveis:** `emerging` (< 2 confirmações) → `active` (≥ 2) → `quarantine` (confidence < 0.2) → `archived`

**Regras de promoção:**
- Observation → Belief requer ≥ 2 sessões confirmando
- User correction → promoção imediata (confidence 0.9)
- Contradição detectada → ambas beliefs rebaixadas, flag para review

---

### §3: Consolidation Engine (autolearn + autodream)

**O que é:** Background job que transforma observações em beliefs e beliefs em bootstrap profile. Equivalente ao "dreaming" do Claude Code, mas como serviço MCP.

**Triggers:**
- Scheduled (cron interno, configurável — default: a cada 6h)
- On-demand (tool `memory_consolidate` já existente)
- Threshold (após N novas observações — default: 20)

**Fases (inspiradas no Claude AutoDream):**

| Fase | Ação | Input | Output |
|------|------|-------|--------|
| 1. Scan | Ler observações desde última consolidação | Observation Store | Candidatos |
| 2. Correlate | Entity linking + pattern detection cross-session | Candidatos + Beliefs existentes | Correlações |
| 3. Update Beliefs | Aplicar negative learning, confidence update, contradiction search | Correlações + Belief Store | Beliefs atualizadas |
| 4. Rebuild Profile | Gerar bootstrap profile sob token budget | Beliefs ativas (top-K por confidence) | Bootstrap Profile |
| 5. Self-Critique | LLM adversarial verifica se alguma belief é inconsistente com observações | Profile + Observações recentes | Flags de quarantine |

**Negative Learning (§3.3):**
```
confidence_delta = LEARNING_RATE * (1.0 se sucesso, -ERROR_WEIGHT se erro)
frustration += 1 se erro, -= 0.1 se sucesso
Se frustration > THRESHOLD → belief ganha flag "AVOID" no profile
```
Com `ERROR_WEIGHT = 3.0` e `THRESHOLD = 5`.

**Contradiction Search (§3.5):**
- Via sampling: server pede ao host LLM para analisar beliefs vs observações recentes
- Prompt: "Aqui está o profile atual. Aqui estão as últimas 10 sessões. Alguma regra parece falsa baseada na evidência recente? Flagge."
- Beliefs flaggeadas → quarantine

---

### §4: Bootstrap Profile (per-agent)

**O que é:** Resource MCP que o host lê no spawn e injeta no system prompt. Gerado automaticamente pela consolidação.

**URI:** `memory://agent/{agent_id}/bootstrap`

**Estrutura:**
```markdown
=== BEHAVIORAL PROFILE (confidence-weighted) ===

## Conventions (stable)
- Use pnpm, not npm [confidence: 0.95]
- Always add LIMIT to SQL queries [confidence: 0.92, evidence: 5 errors]

## Preferences (user-stated)
- Concise answers with bullet points [confidence: 0.90]
- Portuguese for prose, English for code [confidence: 0.88]

## Avoidances (from errors)
- ⚠️ Do NOT use strReplace on MEMORY.md — use insert/append [confidence: 0.95, errors: 13]
- ⚠️ Always show draft before posting to GitHub [confidence: 0.93, errors: 4]

## Advisory (confidence < 0.7 — may challenge)
- User might prefer dark mode UI components [confidence: 0.55, evidence: 1 session]

## Meta-instruction
Rules with confidence < 0.7 are advisory. If user behavior contradicts them,
note the contradiction in your session report. You are an active verifier,
not a blind follower.

=== END PROFILE ===
```

**Token budget:** Configurável (default: 2048 tokens). Se over budget, server prioriza por confidence * recency.

**Versionamento:** Cada rebuild gera nova versão. Host pode pin ou rollback.

---

### §5: Session Legacy ("Death Rattle")

**O que é:** Tool MCP que o agente chama obrigatoriamente antes de morrer, reportando o que aprendeu.

**Tool:** `commit_session_legacy`

**Schema:**
```json
{
  "session_id": "string",
  "agent_id": "string",
  "task_summary": "string",
  "decisions": [{"what": "string", "why": "string"}],
  "errors": [{"tool": "string", "error": "string", "count": "int", "severity": "string", "resolution": "string"}],
  "user_corrections": [{"original": "string", "corrected_to": "string"}],
  "belief_updates": [{"belief": "string", "new_confidence": "float", "reason": "string"}],
  "memories_used": ["hash1", "hash2"],
  "outcome": "success | partial | failure"
}
```

**Enforcement:** O system prompt do agente inclui instrução obrigatória:
> "Your final action before completing ANY task MUST be to call commit_session_legacy."

**Processamento:** Server recebe, armazena no Observation Store, e agenda consolidação se threshold atingido.

---

### §6: Anti-Hallucination Safeguards

| # | Safeguard | Mecanismo |
|---|-----------|-----------|
| 1 | Write-path isolation | Agentes só escrevem observations, nunca beliefs/profile |
| 2 | Multi-session confirmation | Belief requer ≥2 sessões confirmando (exceto user_correction) |
| 3 | Confidence display | Profile mostra scores; agent pode desafiar rules < 0.7 |
| 4 | Fresh-start sentinel | Cada N sessões (default: 10), host ignora profile e valida baseline |
| 5 | Exploration probes | Server injeta "teste hipótese contrária" periodicamente |
| 6 | Contradiction search | Consolidation critica próprias regras via LLM adversarial |
| 7 | Bootstrap versioning | Rollback se comportamento degrada |
| 8 | User correction priority | Override imediato + trigger consolidation review |
| 9 | External validation | Server pode chamar tools (rodar teste, query DB) para verificar belief |

---

### §7: MCP Protocol Integration

**Mecanismos usados (todos dentro da spec atual):**

| Primitivo MCP | Uso neste RFC |
|---------------|---------------|
| Resources | `memory://agent/{id}/bootstrap` — profile lido no spawn |
| Tools | `get_bootstrap_profile`, `commit_session_legacy`, `memory_consolidate` |
| Notifications | `ResourceUpdatedNotification` após consolidation rebuild |
| Sampling | Consolidation engine usa sampling para self-critique (LLM do host) |

**Mecanismo desejado (proposta #148):**
- `instructions/get` — server retorna system messages per-turn
- Se adotado, substituiria o padrão de host-level injection

**O que NÃO fazemos:**
- Não injetamos conteúdo sem o host decidir (respeitamos client-driven)
- Não usamos tool descriptions como canal comportamental (security-adjacent)
- Não modificamos o system prompt do agente diretamente

---

## Plano de Implementação

| Fase | Módulo | Esforço | Depende de |
|:----:|--------|:-------:|:----------:|
| **P1** | Observation Store (novo type + metadata.source) | 2 dias | — |
| **P2** | Belief Store (schema + CRUD + confidence tracking) | 3 dias | P1 |
| **P3** | `commit_session_legacy` tool | 2 dias | P1 |
| **P4** | Negative learning (error_weight, frustration, AVOID rules) | 2 dias | P2 |
| **P5** | Bootstrap Profile resource + `get_bootstrap_profile` tool | 3 dias | P2, P4 |
| **P6** | Consolidation Engine (scheduled + threshold trigger) | 5 dias | P1, P2, P5 |
| **P7** | Self-critique via sampling (contradiction search) | 3 dias | P6 |
| **P8** | Fresh-start sentinel + exploration probes | 2 dias | P5, P6 |

**Total estimado:** 22 dias-dev, paralelizável em 2 tracks (P1-P3-P4 || P2-P5-P6).

---

## Compatibilidade

- **Zero breaking changes** — tudo aditivo
- **Backward compatible** — agentes que não usam bootstrap/legacy continuam funcionando
- **Opt-in** — cada feature ativada por env var (MCP_BOOTSTRAP_ENABLED, MCP_SESSION_LEGACY_ENABLED, etc.)
- **Reusa infra existente** — observation store = memory_store com type novo; consolidation = extensão do dream cycle existente; negative learning = extensão do mistake_note existente

---

## Métricas de Sucesso

| Métrica | Baseline | Target |
|---------|:--------:|:------:|
| Cross-session error repetition | ~60% | < 20% |
| Bootstrap relevance (top-5 match) | ~30% | > 70% |
| Mistake-to-learning conversion | 0% (manual) | > 80% (auto) |
| Session legacy coverage | 0% | > 90% |
| Hallucination compounding rate | 29% (5+ steps) | < 10% |
| Profile token efficiency | N/A | < 2K tokens com > 80% relevance |

---

## Relação com Trabalho Existente

| Feature existente | Como este RFC estende |
|-------------------|----------------------|
| `memory_store` | Observation Store é memory_store com `type=observation` |
| `memory_consolidate` | Consolidation Engine é extensão com belief extraction + profile rebuild |
| `mistake_note_add/search` | Negative learning generaliza mistake_notes com confidence + frustration |
| RFC #1008 §3 (auto-capture) | Auto-capture alimenta o Observation Store automaticamente |
| `memory_harvest` | Session legacy é harvest estruturado com schema fixo |
| `memory_quality maintain` | Safeguards (fresh-start, contradiction) estendem o maintain cycle |

---

## Discussão Aberta

1. **Onde rodar o LLM para consolidation?** Via sampling (usa LLM do host) ou LLM local (Ollama)? Sampling é mais elegante mas depende do host suportar.
2. **Granularidade do profile por projeto vs global?** Proposta: hierarquia `global → project → task_type`.
3. **Quem faz o fresh-start sentinel?** Host (mais simples) ou server (mais portável)?
4. **Upstream ou fork?** Este RFC é grande. Propor como issue de discussão primeiro, implementar no fork, depois PR incremental?
5. **Interação com GitHub #148 (system message injection)?** Se aprovado, simplifica drasticamente o host-side. Monitorar.

---

## Referências

### Papers
- Reflexion (NeurIPS 2023) — semantic gradients from failures
- MAR: Multi-Agent Reflexion (Dec 2025) — 6.2pt improvement over single-agent
- Mem^p (Zhejiang/Alibaba) — procedural revision on failure
- Sleep-Consolidated Memory for LLMs (arXiv 2604.20943)
- Adaptive Memory Crystallization (arXiv 2604.13085)
- Hindsight: Building Agent Memory that Retains, Recalls, and Reflects (arXiv 2512.12818)
- ACT-R Inspired Memory Architecture (ACM HAI 2026)

### Produtos/Sistemas
- Claude Dreaming / AutoDream (Anthropic, abr/2026)
- Hindsight TEMPR + CARA (Vectorize)
- Mem0 v3 (multi-signal retrieval)
- Zep/Graphiti (temporal knowledge graph)
- Honcho (peer-centric async reasoning)
- Praetorian Self-Annealing (anti-pattern entries)
- agentmemory Codex plugin (lifecycle hooks)
- OpenClaw Auto-Dream (MIT, markdown-based)

### MCP Spec
- GitHub Issue #148: System Message Injection proposal
- MCP Sampling primitive (server-initiated LLM requests)
- MCP Notifications (ResourceUpdatedNotification)
- SEP-1300: Tool Groups proposal
- PulseMCP: Agentic MCP Configuration pattern

### Documentos Internos
- `padroes/mcp-memory-autolearn-rfc.md` — Spock: ecossistema + implementação
- `padroes/mcp-memory-feedback-loop-research.md` — Kiro: protocolo + feedback loop
- `ferramentas/kiro-hooks-enforcement.md` — enforcement atual via hooks

---

## Apêndice A — Spec de Implementação (P1+P3+P4+P5+P8)

**Branch:** `feat/self-service-memory-intelligence`
**Base:** `main` (v10.68.0)
**Scope:** P1, P3, P4, P5, P8 (excluindo P2 Belief Store, P6 Consolidation Engine, P7 Self-critique)

### Overview

Esta implementação adiciona 5 features ao fork, todas backward-compatible e opt-in:

1. **P1 — Observation Store**: New `memory_type=observation` with structured subtypes
2. **P3 — Session Legacy**: New tool `commit_session_legacy`
3. **P4 — Negative Learning**: Extend `mistake_note` with confidence + frustration decay
4. **P5 — Bootstrap Profile**: New tool `get_bootstrap_profile`
5. **P8 — Fresh-start sentinel**: New env var `MCP_BOOTSTRAP_FRESH_START_INTERVAL`

---

### P1: Observation Store

**No new tables or schema.** Uses existing `memory_store` with conventions:
- `memory_type = "observation"`
- `metadata.observation_type` = one of: `decision`, `error`, `user_correction`, `tool_outcome`, `preference_signal`
- `metadata.source = "observation"` (triggers recursion guard from §3 auto-capture)
- `metadata.session_id` = session identifier
- `metadata.agent_id` = agent identifier

**Files modified:**
- `src/mcp_memory_service/models/ontology.py` — add `observation` subtypes to TAXONOMY
- No new files needed — uses existing `memory_store` path

**New subtypes in ontology:**
```python
"observation": [
    "decision",           # Agent chose X over Y
    "error",             # Something failed
    "user_correction",   # User corrected the agent
    "tool_outcome",      # Tool call result (success/failure)
    "preference_signal", # Implicit or explicit preference
]
```

**Validation:**
- `observation_type` must be one of the 5 defined subtypes
- `session_id` and `agent_id` are required in metadata for observations

---

### P3: Session Legacy

**New tool:** `commit_session_legacy`

**Files modified/created:**
- `src/mcp_memory_service/server/handlers/memory.py` — add `handle_commit_session_legacy`
- `src/mcp_memory_service/server_impl.py` — register tool + route

**Tool schema:**
```python
types.Tool(
    name="commit_session_legacy",
    description="Record end-of-session learnings from an ephemeral agent. "
                "Stores decisions, errors, corrections, and belief updates "
                "as structured observations for future consolidation.",
    inputSchema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Unique session identifier"},
            "agent_id": {"type": "string", "description": "Agent identifier (e.g., 'kiro', 'spock')"},
            "task_summary": {"type": "string", "description": "Brief description of what was attempted"},
            "decisions": {
                "type": "array",
                "items": {"type": "object", "properties": {"what": {"type": "string"}, "why": {"type": "string"}}},
                "description": "Decisions made during the session"
            },
            "errors": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "tool": {"type": "string"}, "error": {"type": "string"},
                    "count": {"type": "integer"}, "severity": {"type": "string"},
                    "resolution": {"type": "string"}
                }},
                "description": "Errors encountered"
            },
            "user_corrections": {
                "type": "array",
                "items": {"type": "object", "properties": {"original": {"type": "string"}, "corrected_to": {"type": "string"}}},
                "description": "User corrections (strongest learning signal)"
            },
            "belief_updates": {
                "type": "array",
                "items": {"type": "object", "properties": {"belief": {"type": "string"}, "new_confidence": {"type": "number"}, "reason": {"type": "string"}}},
                "description": "Beliefs that changed during the session"
            },
            "outcome": {"type": "string", "enum": ["success", "partial", "failure"]},
        },
        "required": ["session_id", "agent_id", "task_summary", "outcome"]
    }
)
```

**Implementation logic:**
1. Store the full legacy as a single memory with `memory_type="observation"`, `metadata.observation_type="session_legacy"`
2. For each `error` in the payload: call `mistake_note_add` internally (auto-creates/increments)
3. For each `user_correction`: store as separate observation with `observation_type="user_correction"` and high priority tag
4. Return: `{"status": "recorded", "observations_created": N, "mistake_notes_updated": M}`

---

### P4: Negative Learning

**Extend `mistake_note_add`** with:
- `confidence` field (0.0-1.0, starts at 0.5, decays/grows)
- `frustration_score` field (starts at 0, increments on error, slow decay on success)
- When `frustration_score > MCP_FRUSTRATION_THRESHOLD` (default: 5), the note gets tag `avoid-rule`

**New tool:** `mistake_note_update` (update confidence/frustration of existing note)
**New tool:** `mistake_note_delete` (remove a mistake note — already in PR #1045)

**Files modified:**
- `src/mcp_memory_service/services/memory_service.py` — extend `mistake_note_add` to store confidence + frustration in metadata
- `src/mcp_memory_service/server_impl.py` — register `mistake_note_update`

**New metadata fields on mistake notes:**
```json
{
  "failure_count": 5,
  "confidence": 0.85,
  "frustration_score": 4.2,
  "last_error_at": "2026-05-29T10:00:00Z",
  "last_success_at": "2026-05-28T15:00:00Z",
  "is_avoid_rule": false
}
```

**Update logic:**
```python
def update_mistake_confidence(note_metadata, is_error: bool):
    ERROR_WEIGHT = float(os.getenv("MCP_ERROR_WEIGHT", "3.0"))
    LEARNING_RATE = float(os.getenv("MCP_LEARNING_RATE", "0.1"))
    FRUSTRATION_THRESHOLD = float(os.getenv("MCP_FRUSTRATION_THRESHOLD", "5.0"))

    if is_error:
        note_metadata["confidence"] = min(1.0, note_metadata.get("confidence", 0.5) + LEARNING_RATE * ERROR_WEIGHT)
        note_metadata["frustration_score"] = note_metadata.get("frustration_score", 0) + 1.0
        note_metadata["last_error_at"] = datetime.utcnow().isoformat()
    else:
        note_metadata["confidence"] = max(0.0, note_metadata.get("confidence", 0.5) - LEARNING_RATE)
        note_metadata["frustration_score"] = max(0.0, note_metadata.get("frustration_score", 0) - 0.1)
        note_metadata["last_success_at"] = datetime.utcnow().isoformat()

    note_metadata["is_avoid_rule"] = note_metadata["frustration_score"] >= FRUSTRATION_THRESHOLD
```

---

### P5: Bootstrap Profile

**New tool:** `get_bootstrap_profile`

**Files modified/created:**
- `src/mcp_memory_service/server/handlers/bootstrap.py` — new handler
- `src/mcp_memory_service/server_impl.py` — register tool + route

**Tool schema:**
```python
types.Tool(
    name="get_bootstrap_profile",
    description="Generate a behavioral bootstrap profile for an ephemeral agent. "
                "Returns confidence-weighted rules, avoidances, and preferences "
                "derived from past sessions. Designed to be injected into system prompts.",
    inputSchema={
        "type": "object",
        "properties": {
            "agent_ids": {
                "type": "array", "items": {"type": "string"}, "minItems": 1,
                "description": "Agent identifiers to build profile for"
            },
            "project_id": {"type": "string", "description": "Optional project scope"},
            "task_summary": {"type": "string", "description": "Optional task context for relevance filtering"},
            "max_tokens": {"type": "integer", "default": 2048, "description": "Token budget for the profile"},
        },
        "required": ["agent_ids"]
    }
)
```

**Implementation logic:**
1. Query mistake notes with `is_avoid_rule=True` or high `frustration_score` → "Avoidances" section
2. Query memories with `memory_type="observation"` + `observation_type="user_correction"` → "Preferences" section
3. Query memories with `memory_type="observation"` + `observation_type="decision"` + high access_count → "Conventions" section
4. Format with confidence scores (0.0-1.0)
5. Apply token budget: if over `max_tokens`, truncate lowest-confidence items
6. Return formatted markdown string

**Bootstrap profile format:**
```
=== BEHAVIORAL PROFILE for {agent_id} ===

## Conventions (stable)
- Rule [confidence: X.XX]
- Rule [confidence: X.XX]

## Preferences (user-stated)
- Preference [confidence: X.XX]

## Avoidances (from errors)
- ⚠️ Avoid [confidence: X.XX, errors: N]

## Advisory (confidence < 0.7)
- Suggestion [confidence: X.XX]

## Meta
Generated: {timestamp}
Next refresh: on next consolidation cycle
```

---

### P8: Fresh-Start Sentinel

**New env var:** `MCP_BOOTSTRAP_FRESH_START_INTERVAL` (default: 10, 0 to disable)

**What changes:**
- After N sessions using the same bootstrap profile, the profile includes a `## Fresh Start` section
- That section tells the agent: "The following N sessions are a fresh-start probe. Your observations will be compared against this profile. Contradictions are expected and valuable."
- After the fresh-start window, `memory_quality maintain` evaluates: did the agent's behavior confirm or contradict the profile?
- If contradicted → quarantine affected beliefs
- If confirmed → reinforce confidence

**How it works:**
1. After `MCP_BOOTSTRAP_FRESH_START_INTERVAL` sessions using same profile, profile gains fresh-start flag
2. Agent is instructed to critically evaluate each profile rule during fresh-start sessions
3. Session legacies include explicit `belief_updates` for challenged rules
4. After fresh-start window, consolidation reviews challenge results
5. Rules that survive challenge gain confidence boost (+0.1); rules contradicted get quarantined

**Config:**
```bash
# Sessions between fresh-start sentinel checks (default: 10, 0=disabled)
MCP_BOOTSTRAP_FRESH_START_INTERVAL=10
```

---

## Apêndice B — Fechamento de Parciais §3 e §7

**Data:** 2026-05-31
**Branch base:** `feat/harvest-quality-fix`
**Status:** Implementado

### Contexto

O pipeline v2 está funcional (harvest + distill + bootstrap + post-commit learning).
Faltavam 3 itens para fechar §3 e §7 do RFC 1047:

| # | Seção | Item | Estado |
|---|-------|------|--------|
| A | §3 | Contradiction search automática no scheduler | Pendente |
| B | §3 | Threshold trigger para consolidation full | Pendente |
| C | §7 | Resource URI `memory://agent/{id}/bootstrap` | Pendente |

§2 (Belief Store) e §6 (Anti-Hallucination) ficam bloqueados — dependem de decisão arquitetural com upstream.

---

### A. Contradiction Search no Scheduler (§3)

O scheduler 6h já roda `distill_check`. Adicionar `contradiction_check` que chama `memory_conflicts()` e loga warnings se encontrar contradições não resolvidas.

**Onde:** `src/mcp_memory_service/consolidation/scheduler.py`

**Comportamento:**
1. A cada 6h (junto com distill_check), chamar `self.server.handle_memory_conflicts({})`
2. Se retornar conflitos com `status != "resolved"` → log WARNING com count
3. Não resolve automaticamente (requer decisão humana ou LLM)
4. Métrica: `last_contradiction_check_at` + `unresolved_count` no maintain_status

---

### B. Threshold Trigger para Consolidation (§3)

Quando `memory_store` é chamado e o count de memórias não-consolidadas ultrapassa um threshold (default: 50), disparar consolidation incremental em background.

**Onde:** `src/mcp_memory_service/server_impl.py` → `handle_memory_store` (pós-store hook)

**Comportamento:**
1. Após cada `memory_store` bem-sucedido, incrementar counter interno
2. Se counter >= `MCP_CONSOLIDATION_THRESHOLD` (default 50) E última consolidation > 24h:
   - Disparar `asyncio.create_task(self._background_consolidation())`
   - Reset counter
3. `_background_consolidation()` chama consolidate com `time_horizon="incremental"`
4. Não bloqueia o response do store

**Diferença do threshold de distill:**
- Distill threshold (20): processa memórias individuais via LLM → insights
- Consolidation threshold (50): clustering, compression, associations entre memórias

---

### C. Resource URI Bootstrap (§7)

Expor o bootstrap profile como MCP Resource em `memory://agent/{id}/bootstrap`.

**Onde:** `src/mcp_memory_service/server_impl.py` → resource handlers

**Comportamento:**
1. Registrar resource template: `memory://agent/{agent_id}/bootstrap`
2. `resources/list` inclui o resource com description
3. `resources/read` com URI `memory://agent/kiro/bootstrap` retorna o profile (mesmo resultado de `get_bootstrap_profile(agent_ids=["kiro"])`)
4. Após consolidation/distill rebuild, emitir `notifications/resources/updated`

---

### Ordem de Implementação

1. Escrever todos os testes RED (A + B + C)
2. Implementar A (contradiction scheduler) — ~10 linhas
3. Implementar B (threshold consolidation) — ~20 linhas
4. Implementar C (resource URI) — ~30 linhas
5. Rodar testes → GREEN
6. Rodar suite completa (`pytest tests/`)
7. Commit + push

---

### Env Vars Novas

```bash
# Threshold para consolidation automática (default: 50)
MCP_CONSOLIDATION_THRESHOLD=50

# Intervalo mínimo entre consolidations automáticas (default: 86400 = 24h)
MCP_CONSOLIDATION_MIN_INTERVAL=86400
```

### Critérios de Aceite

- [ ] Contradiction check roda a cada 6h e loga se há conflitos
- [ ] Consolidation dispara automaticamente após 50 stores (se >24h desde última)
- [ ] `resources/read memory://agent/kiro/bootstrap` retorna profile
- [ ] Nenhum breaking change
- [ ] Testes passam
