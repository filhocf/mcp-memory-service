# Plano: Tornar Autolearn e Autodream Produtivos

**Data:** 2026-05-30 (consolidado: 2026-07-02)
**Autor:** Claudio + Kiro (análise conjunta)
**Versão:** 1.0 (consolidado)
**Contém:** Diagnóstico completo (métricas reais), Solução server-side, Fases de implementação, Log de execução

---

## 1. Diagnóstico

### 1.1 Estado atual (30/mai/2026)

| Métrica | Valor |
|---------|-------|
| Total memórias | 4.205 |
| Banco | 28 MB |
| Qualidade média | 0.505 |
| High quality (≥0.7) | 62 (1.5%) |
| Low quality (<0.5) | 4 |
| Associations (auto-geradas, ruído) | 1.588 (38%) |
| Documents MCR (ingestão em massa, lixo) | 718 (17%) |
| Mistake notes | 539 |
| Memórias com rating manual | ~62 |
| Bootstrap profile | Desabilitado |
| Harvest com LLM | Implementado, nunca rodou em escala |

### 1.2 Por que não funciona

| Etapa | Problema |
|-------|----------|
| Entrada (harvest) | Até 29/mai: 500 chars truncados = lixo. Novo pipeline (LLM) pronto mas não testado em escala |
| Classificação | Memórias salvas como `observation` genérico, sem `agent_id`, sem `observation_type` |
| Bootstrap | Desabilitado. Quando habilitado, busca metadata que não existe (`user_correction`, `decision`) |
| Consolidation | Gera associations (ruído). Clustering/compression nunca testados em escala |
| Feedback loop | Quality ratings quase zero. Sem rating, ranked search não prioriza |
| Autodream skill | Cleanup funciona. Síntese real precisa de curadoria humana ou LLM |

### 1.3 Problema fundamental

O sistema upstream foi desenhado para `commit_session_legacy` com campos estruturados.
Nós usamos `memory_store` com texto livre + tags. O bootstrap procura campos que nunca preenchemos.

### 1.4 Autolearn/Autodream dependem do agente LLM lembrar de executá-los

Na prática:
- autolearn roda em ~20% das sessões (quando o agente segue o shutdown-hook)
- autodream roda 1x por semana (quando alguém pede)
- **80% do conhecimento gerado nas sessões se perde**

---

## 2. Solução

### 2.1 Princípio

Construir pipeline que funcione com **o que realmente produzimos** (sessões JSONL + memory_store texto livre), não tentar encaixar no modelo upstream.

### 2.2 Ciclo alvo

```
Sessão → [autolearn] → Memórias com metadata correta → [autodream] → Consolidação → [bootstrap] → Próxima sessão
              ↑                                              ↑                              ↓
    harvest LLM + commit_session_legacy          clustering + dedup + ranking      profile 2K tokens
```

### 2.3 Solução: Server-Side Autolearn & Autodream

Mover a lógica de aprendizado para **dentro do MCP server**. O agente só precisa:
- **Início**: `get_bootstrap_profile(agent_ids=["kiro"])` → recebe regras atualizadas
- **Fim**: `commit_session_legacy(...)` → dispara aprendizado automático

Tudo entre esses dois pontos é server-side, automático, sem depender do agente.

### 2.4 Arquitetura Server-Side

```
┌─────────────────────────────────────────────────────────┐
│  Agente (efêmero)                                        │
│                                                          │
│  START: get_bootstrap_profile() ←─── profile atualizado  │
│  ...trabalha...                                          │
│  END: commit_session_legacy(decisions, errors, ...)      │
└──────────────────────────┬───────────────────────────────┘
                           │ trigger
                           ▼
┌─────────────────────────────────────────────────────────┐
│  MCP Server (persistente, automático)                    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Learning Pipeline (background, async)           │    │
│  │                                                  │    │
│  │  1. Harvest sessão que acabou (JSONL → insights) │    │
│  │  2. Distill memórias novas (batch DeepSeek)      │    │
│  │  3. Rebuild bootstrap profile                    │    │
│  │                                                  │    │
│  │  Triggers:                                       │    │
│  │  - commit_session_legacy (imediato)              │    │
│  │  - Threshold: >20 memórias novas sem distill     │    │
│  │  - Timer: 24h sem consolidation                  │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Consolidation Scheduler (existente, estendido)  │    │
│  │                                                  │    │
│  │  - Weekly: full consolidation (clustering, etc.) │    │
│  │  - Daily: distill batch (memórias não processadas│    │
│  │  - On-demand: via tool memory_distill            │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Fases de Implementação

### Fase 0 — Limpeza (pré-requisito)

- [ ] Deletar 718 memórias MCR/document (poluem buscas semânticas)
- [ ] Verificar se associations (1.588) devem ser mantidas ou limpas
- [ ] Habilitar env vars: `MCP_BOOTSTRAP_ENABLED=true`

### Fase 1 — Harvest em escala (popular banco com insights reais)

- [ ] Rodar harvest em lotes de 20 sessões com `use_llm=true`
- [ ] Validar qualidade entre lotes (amostrar 3-5 insights por lote)
- [ ] Ajustar prompt do rewriter se necessário
- [ ] Meta: 177 sessões processadas, ~50-100 insights de alta qualidade

**Comando:**
```
memory_harvest(sessions=20, use_llm=true, role_filter=true, meta_filter=true)
```

**Critérios de qualidade por insight:**
- Standalone (entendível sem contexto da sessão)
- Acionável (diz o que fazer ou evitar)
- Específico (não genérico como "documentar é importante")
- No idioma correto (pt-BR para sessões pt-BR)

### Fase 2 — Habilitar bootstrap

- [ ] Env var: `MCP_BOOTSTRAP_ENABLED=true` no systemd
- [ ] Testar: `get_bootstrap_profile(agent_ids=["kiro"])` retorna profile não-vazio
- [ ] Adicionar ao startup-hook: chamar bootstrap e injetar no contexto
- [ ] Validar: profile contém avoidances (mistake_notes) + conventions (harvest)

### Fase 3 — Reescrever autolearn.md (encerramento de sessão)

Novo fluxo:
1. `memory_harvest(sessions=1, use_llm=true)` — extrai insights da sessão atual
2. `commit_session_legacy` com campos derivados:
   - `decisions`: memórias com tag `decisao` salvas durante a sessão
   - `errors`: mistake_notes adicionados durante a sessão
   - `user_corrections`: momentos onde o usuário corrigiu (detectável no JSONL)
3. Rate memórias consultadas (thumbs up/down)
4. Verificar: ≥3 ratings feitos na sessão

### Fase 4 — Reescrever autodream.md (semanal)

Novo fluxo:
1. **Limpeza**: cleanup + conflicts
2. **Consolidation incremental**: `consolidate_memories(time_horizon="incremental")`
3. **Síntese temática**: buscar clusters de 3+ memórias sobre mesmo tema → consolidar
4. **Refresh bootstrap**: profile reflete estado atualizado
5. **Métricas**: reportar throughput, qualidade média, stale count

### Fase 5 — Feedback loop (contínuo)

- [ ] Habilitar `MCP_INSIGHT_CARDS_ENABLED=true`
- [ ] Habilitar `MCP_CONTRADICTION_DETECTION_ENABLED=true`
- [ ] Auto-rate implícito: memórias acessadas frequentemente → boost
- [ ] Decay natural: memórias não acessadas em 60 dias perdem score

---

## 4. Implementação Server-Side (detelhamento)

### Fase A: Post-commit trigger (autolearn automático)

**O que**: Quando `commit_session_legacy` é chamado, disparar harvest+distill em background.

**Onde**: `server_impl.py` → `handle_commit_session_legacy`

```python
async def handle_commit_session_legacy(self, arguments):
    result = await self._process_session_legacy(arguments)
    asyncio.create_task(self._post_commit_learning(arguments))
    return result

async def _post_commit_learning(self, session_data):
    try:
        session_id = session_data.get("session_id")
        if session_id:
            await self._harvest_session(session_id)
        new_count = await self._count_undistilled_memories()
        if new_count >= 10:
            await self._distill_batch(batch_size=new_count)
    except Exception as e:
        logger.warning(f"Post-commit learning failed: {e}")
```

### Fase B: Scheduler estendido (autodream automático)

**O que**: Estender o scheduler existente para rodar distill periodicamente.

```python
SCHEDULES = {
    "daily": {
        "interval": 86400,  # 24h
        "tasks": ["distill_undistilled"],
    },
    "weekly": {
        "interval": 604800,  # 7 dias
        "tasks": ["full_consolidation", "distill_undistilled"],
    },
}
```

### Fase C: Bootstrap consumir distill + auto-refresh

- Bootstrap buscar tag `memory-distill`
- Após cada distill run, invalidar cache do bootstrap

### Fase D: Threshold trigger

Se >20 memórias novas sem distill, disparar distill automaticamente (sem esperar timer).

---

## 5. DESCOBERTA CRÍTICA: Gap de "Colheita de Memórias" (30/mai/2026)

### O problema

Temos 3.022 memórias ativas no banco. Muitas contêm decisões, bugs e padrões embutidos em texto longo (checkpoints de sessão). Exemplo:

> "Sessão 2026-04-30: Descoberta: Restrição 'Assentamento' (id=12) ≠ tipo 'AST'. São coisas diferentes! Para análise de trabalho escravo, filtrar apenas IRU."

Esse insight está **enterrado** num checkpoint de 2000 chars. Nenhum processo existente o extrai.

### O que existe vs o que falta

| Processo | Fonte | Extrai aprendizados? |
|----------|-------|---------------------|
| Harvest | JSONLs (conversas) | ✅ Sim (com LLM) |
| Maintain | Memórias | ❌ Não (só manutenção) |
| Consolidation/Compression | Memórias | ❌ Não (resumo estatístico, sem LLM) |
| **Colheita de Memórias (NOVO)** | **Memórias existentes** | **✅ Sim (com LLM)** |

### Proposta: `memory_distill`

1. **Seleciona** memórias candidatas: types observation/decision/reference, min 200 chars, exceto já destiladas
2. **Passa pelo LLM rewriter**: "Isso contém um insight acionável? Se sim, extraia em 1-2 frases."
3. **Armazena** como nova memória com tag `memory-distill`, linkando à original

---

## 6. Métricas de Sucesso

| Métrica | Antes | Meta (30 dias) |
|---------|-------|----------------|
| Bootstrap profile | Vazio | 15-30 regras acionáveis |
| Insights harvest (standalone) | 0 | 50-100 |
| Quality ratings | 62 | 200+ |
| Qualidade média | 0.505 | 0.55+ |
| Memórias lixo (MCR + harvest antigo) | 718 | 0 |
| Sessões com autolearn efetivo | 0% | 80%+ |

---

## 7. Riscos

| Risco | Mitigação |
|-------|-----------|
| Groq rate limit em harvest grande | Lotes de 20, intervalo entre lotes |
| LLM rewriter produz genéricos | Prompt mais rigoroso + meta-filter |
| Bootstrap muito grande (>2K tokens) | max_tokens configurável, ranking por qualidade |
| Consolidation corrompe banco | Sempre em branch, backup antes |

---

## 8. Log de Execução

### 30/mai/2026 — Início

- [x] Diagnóstico completo (banco, distribuição, problemas)
- [x] Autodream manual: 3 sínteses consolidadas (Infra, MIR/MCR, Opensource)
- [x] Maintain cycle rodado (514 entities, 0 duplicatas, 0 conflitos)
- [x] Fase 0: Limpeza MCR (718 memórias soft-deleted)
- [x] Fix: groq instalado no venv
- [x] Fix: rewrite_sync asyncio.run() → ThreadPoolExecutor (funciona dentro de uvicorn)
- [x] Fix: prompt rewriter melhorado (SKIP temporal/meta/genérico)
- [x] Fix: filtro pós-LLM integrado no harvester (keywords meta + regex temporal)
- [x] Testes: prompt atual 40% → prompt melhorado 80% → prompt + filtro 87%
- [ ] Fase 1: Harvest lote 1 (20 sessões)
- [ ] Fase 1: Análise qualidade lote 1
