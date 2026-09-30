# Pipeline: Harvest Pipeline Quality Fix

**Data:** 2026-05-30 (consolidado: 2026-07-02)
**Autor:** Claudio + Kiro (análise conjunta)
**Branch:** `feat/harvest-quality-fix`
**Base:** `main` (v10.70.0)
**Versão:** 1.0 (consolidado)
**Contém:** Spec de qualidade, Resultados do pipeline v2, Relatório de testes

---

## 1. Problema

O pipeline de harvest produz memórias de baixa qualidade que poluem o banco (46% do total = 3.579 memórias) e não geram valor para o bootstrap do agente.

### Evidências coletadas (30/mai/2026)

1. **Extração bruta:** O `PatternExtractor` faz regex match no texto inteiro da mensagem e armazena os primeiros 500 chars — que frequentemente são contexto irrelevante, não o insight.

2. **Falsos positivos:** Em teste com 2 sessões, 2/2 candidatos extraídos eram texto irrelevante (prompt do user + análise do assistant sobre o próprio harvest).

3. **Sem distinção de role:** Mensagens do user e do assistant são processadas igualmente.

4. **LLM classifier não resolve:** O LLM apenas classifica o texto bruto como "decision/bug/learning" — não reescreve como insight standalone.

5. **Bootstrap profile inexistente:** `get_bootstrap_profile` retorna "Unknown tool".

6. **Banco poluído:** 4.269 memórias tipo "observation" (55%), 881 tipo "bug" (11% — maioria falso positivo).

### Causa raiz

```
Mensagem completa (2000 chars)
    ↓ regex match ("o problema era")
Primeiros 500 chars da mensagem (irrelevante)
    ↓ armazena como "bug"
Banco poluído → memory_search retorna lixo → agente não melhora
```

---

## 2. Solução

### 2.1 Fase 1 — Extração cirúrgica (Sentence-level extraction + Role filter + Confidence gate)

**Sentence-level extraction:** Quando um pattern faz match, extrair **a sentença que contém o match + 1 sentença de contexto antes e depois** (máx 300 chars total).

```python
# ANTES
content = clean_text[:MAX_CANDIDATE_CONTENT_LENGTH].strip()

# DEPOIS
content = extract_context_around_match(clean_text, match_span, context_sentences=1, max_chars=300)
```

**Role filter:** Só processar mensagens do **assistant** por padrão. Mensagens do user raramente contêm insights.

**Confidence gate:** Elevar threshold mínimo de 0.6 → 0.75.

### 2.2 Fase 2 — LLM como rewriter

O LLM não apenas classifica — ele **reescreve** o candidato como insight standalone.

**Prompt:**
```
Given this excerpt from a coding session conversation:
---
{candidate.content}
---

Extract the key insight as a standalone fact in 1-2 sentences.
Rules:
- Must be self-contained (understandable without the conversation)
- Must be actionable or informative
- Remove conversational filler, markdown formatting, emojis
- If no clear insight exists, respond with "SKIP"

Format: TYPE: content
Types: decision, bug, convention, learning, context
```

**Fluxo:**
1. Heurística extrai candidato (sentence-level, confidence ≥ 0.75)
2. LLM recebe candidato + contexto (±3 sentenças)
3. LLM reescreve como insight standalone OU retorna "SKIP"
4. Se SKIP → descarta
5. Se insight → armazena com confidence boosted (+0.1)

### 2.3 Fase 3 — Bootstrap Profile

Compilar top-K memórias em perfil curado para injeção no startup.

```python
async def get_bootstrap_profile(agent_id: str = "default", max_items: int = 20) -> dict:
    # 1. Buscar memórias com maior quality_score + access_count
    top_memories = await storage.query(
        order_by="quality_score * 0.6 + (access_count / max_access) * 0.4",
        limit=max_items * 3,
        where={"deleted_at": None, "memory_type": ["decision", "convention", "learning", "bug"]},
    )
    # 2. Filtrar: remover duplicatas semânticas (similarity > 0.85)
    deduplicated = deduplicate_by_similarity(top_memories, threshold=0.85)
    # 3. Agrupar por tipo
    profile = {
        "agent_id": agent_id, "generated_at": now_iso(),
        "decisions": [m for m in deduplicated if m.type == "decision"][:5],
        "conventions": [m for m in deduplicated if m.type == "convention"][:5],
        "mistakes": [m for m in deduplicated if m.type == "bug"][:5],
        "learnings": [m for m in deduplicated if m.type == "learning"][:5],
    }
    return profile
```

### 2.4 Fase 4 — Limpeza do banco

Remover memórias harvest de baixa qualidade: quality < 0.3 e sem acesso há 60+ dias.

---

## 3. Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `harvest/extractor.py` | Sentence-level extraction, confidence gate |
| `harvest/harvester.py` | Role filter, LLM rewriter integration |
| `harvest/classifier.py` | Prompt de rewrite (não só classify) |
| `harvest/patterns/pt_BR.yaml` | Ajustar patterns muito amplos |
| `harvest/patterns/en.yaml` | Idem |
| `server_impl.py` | Registrar tool `get_bootstrap_profile` |
| `services/memory_service.py` | Implementar `get_bootstrap_profile` |
| **Novo:** `harvest/rewriter.py` | LLM rewriter com prompt standalone |
| **Novo:** `services/bootstrap.py` | Lógica do bootstrap profile |

---

## 4. Resultados do Pipeline v2 (31/mai/2026)

### Pipeline implementado

```
┌──────────────┐    ┌───────────────┐    ┌──────────────┐    ┌──────────────┐
│   Harvester  │───▶│    Distill    │───▶│   Bootstrap  │───▶│   Profile    │
│ (sessão raw) │    │ (insights LLM)│    │  (curated)    │    │  (output)    │
└──────────────┘    └───────────────┘    └──────────────┘    └──────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
 Observation Store    Tag: memory-distill    Profile resource
```

### Componentes criados

| Componente | Descrição |
|------------|-----------|
| `SessionHarvester` | Orquestra harvest (detecta formato, extrai, filtra, classifica) |
| `TranscriptParser` | Detecta formato (Claude Code, Kiro, OpenClaw, genérico) |
| `PatternExtractor` | Extração por locale (PT-BR e EN) com confidence |
| `LLMRewriter` | Reescrita via LLM (Groq/DeepSeek) com fallback |
| `ConsolidationScheduler` | Distill batch + rebuild bootstrap em background |
| `get_bootstrap_profile` | Tool MCP que compila perfil curado |

### Estados dos componentes

| Componente | Testes |
|------------|--------|
| Harvester | 10/10 passando |
| Parser | 6/6 passando |
| Extractor | 8/8 passando |
| Rewriter | 6/6 passando |
| Bootstrap formatter | ✅ |
| Fresh-start sentinel | ✅ |
| Session legacy tool | ✅ |
| Pipeline v2 (E2E) | ✅ |
| Negative learning | ✅ |
| Observation store | ✅ |
| Distill | ✅ |
| Quality fix tests | ✅ |

### Feature flags (env vars)

```bash
MCP_HARVEST_LOCALE=pt_BR          # Locale de extração
MCP_HARVEST_LLM_ENABLED=false     # LLM rewriter (default off para testes)
MCP_HARVEST_ROLE_FILTER=true      # Só assistant (default on)
MCP_HARVEST_CONFIDENCE_GATE=0.75  # Threshold mínimo
MCP_BOOTSTRAP_ENABLED=false       # Bootstrap (default off)
MCP_BOOTSTRAP_FRESH_START_INTERVAL=10  # Fresh-start a cada 10 sessões
```

---

## 5. Relatório de Testes

### Suíte completa (31/mai/2026)

| Testes | Status |
|--------|--------|
| Testes de extração | ✅ 8/8 |
| Testes de parser | ✅ 6/6 |
| Testes de harvester | ✅ 10/10 |
| Testes de rewriter | ✅ 6/6 |
| Testes de quality fix | ✅ 6/6 |
| Testes de bootstrap | ✅ 3/3 |
| Testes de fresh-start | ✅ 2/2 |
| Testes de session legacy | ✅ 3/3 |
| Testes de pipeline v2 (E2E) | ✅ 2/2 |
| Testes de negative learning | ✅ 3/3 |
| Testes de observation store | ✅ 3/3 |
| Testes de distill | ✅ 2/2 |
| Testes de server-side learning | ✅ 5/5 |
| Testes de RFC 1047 parciais | ✅ 8/8 |
| Testes de onboarding | ✅ 6/6 |

**Total:** 67+ testes implementados, todos GREEN.
