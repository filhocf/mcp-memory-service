# RFC: Server-Side Lifecycle — Mover autolearn/autodream/harvest do agente para infraestrutura

**Data:** 2026-06-22
**Autor:** filhocf
**Status:** Draft
**Problema:** Agente não executa encerramento de forma confiável

---

## 1. Problema

O pipeline de aprendizado (harvest, consolidation, distill, skill_gaps) depende do agente executar passos no encerramento. Na prática, **o agente falha em executar** porque:

- Contexto compacta antes de chegar ao shutdown
- CLI morre (crash, subagent corrompe canal, OOM)
- Agente pula passos (inicialização de memória em vez de seguir skill)
- Sessão é interrompida pelo usuário sem encerramento formal

**Evidência:** De ~50 sessões no último mês, estimamos que <30% executaram o shutdown completo. O autolearn/autodream/auto-evolve rodam em <10% das sessões.

**Consequência:** Conhecimento se perde entre sessões. O sistema não aprende na velocidade que deveria.

---

## 2. Princípio

```
Se é importante demais para falhar → não pode depender do agente.
Se depende do contexto do agente → aceitar como best-effort.
```

---

## 3. Classificação: O que pode ser server-side

| Processo | Precisa do agente? | Solução |
|----------|-------------------|---------|
| memory_harvest | NÃO — lê transcripts do disco | **Server-side: file watcher ou timer** |
| consolidation (daily/weekly) | NÃO — opera sobre banco | ✅ Já server-side (scheduler) |
| distill (batch LLM) | NÃO — opera sobre banco | ✅ Já server-side (scheduler 6h) |
| contradiction detection | NÃO — opera sobre banco | ✅ Já server-side (scheduler 6h) |
| belief derivation | NÃO — opera sobre banco | ✅ Já server-side (scheduler daily) |
| WAL checkpoint | NÃO — PRAGMA | **Server-side: periodic ou pre-backup** |
| hot backup | NÃO — cópia de arquivo | **Server-side: cron/timer** |
| skill_gaps | SIM — precisa saber quais skills usou | Best-effort agent-side |
| auto-evolve | SIM — precisa contexto de falhas | Best-effort agent-side |
| quality ratings | SIM — precisa julgar se memória ajudou | Best-effort agent-side |
| MEMORY.md append | SIM — precisa resumir a sessão | Best-effort agent-side |

---

## 4. Proposta: 3 camadas

### Camada 1: Server-side automático (NUNCA falha)

Já existe parcialmente. Completar:

```
[memory-service systemd]
├── APScheduler (já existe)
│   ├── daily 03:00: consolidation + belief derivation
│   ├── weekly SUN 04:00: deep consolidation
│   ├── every 6h: distill + contradiction check
│   └── NOVO: every 30min: WAL checkpoint
│
├── on_store hooks (já existe)
│   ├── NLI contradiction check
│   ├── entity linking
│   └── NOVO: increment session_activity counter
│
└── NOVO: session_end trigger
    ├── Detecta: session_registry.session_end() chamado
    ├── Executa: harvest da sessão que acabou
    └── Executa: WAL checkpoint
```

### Camada 2: Infra-side (timer/cron, independente do CLI)

```
[systemd timers / cron]
├── Cada 1h: hot backup (backup-and-sync.sh)
├── On session_end event: harvest transcripts
└── Daily 02:00: verificar sessões sem harvest (gap detection)
```

**Implementação session_end → harvest:**

O `session_end` do session-registry já é chamado no encerramento. Adicionar webhook/callback:

```python
# No session-registry, ao receber session_end:
async def on_session_end(session_id, hostname, theme):
    # Notificar memory-service para harvest
    async with httpx.AsyncClient() as client:
        await client.post("http://localhost:3202/internal/harvest", json={
            "session_id": session_id,
            "hostname": hostname,
            "sessions_dir": f"~/.kiro/sessions/cli/"
        })
```

### Camada 3: Agent-side best-effort (pode falhar, sistema não quebra)

```
[Kiro CLI steering - shutdown-hook.md]
├── skill_gaps() — detecta, registra nota para próxima sessão
├── quality ratings — classifica memórias consultadas
├── MEMORY.md append — resumo humano-legível
├── promessas pendentes — verifica
└── mistake notes — registra padrões
```

Se o agente não executar: **o startup da próxima sessão detecta** via gap detection (Camada 2) e informa:
```
⚠️ Sessão anterior encerrou sem harvest. Rodando agora...
⚠️ MEMORY.md não atualizado na sessão anterior.
```

---

## 5. Detecção de falha (gap detection)

No startup, verificar:
1. `session_registry.session_list()` — última sessão teve harvest?
2. Comparar timestamp do último `memory_harvest` vs último `session_end`
3. Se harvest não rodou → executar agora (late harvest)
4. Se MEMORY.md não foi atualizado → avisar o usuário

---

## 6. Implementação (fases)

### Phase 1: WAL checkpoint periódico (trivial)
- Adicionar job no scheduler: every 30min `PRAGMA wal_checkpoint(PASSIVE)`
- Antes do backup: `PRAGMA wal_checkpoint(TRUNCATE)`
- ~5 linhas de código

### Phase 2: session_end → auto-harvest
- Hook no session-registry que notifica memory-service
- memory-service expõe `/internal/harvest` (internal-only endpoint)
- Harvest roda com `sessions=1, dry_run=false` na sessão mais recente
- ~30 linhas total (registry + service)

### Phase 3: Gap detection no startup
- Startup-hook verifica se última sessão teve harvest
- Se não → roda harvest tardio + avisa o usuário
- ~15 linhas no steering (detecção) + já funciona com tools existentes

### Phase 4: Hot backup via timer
- systemd timer `memory-backup.timer` every 1h
- Executa `backup-and-sync.sh`
- Remove dependência do agente fazer isso
- ~10 linhas (unit + timer files)

---

## 7. O que NÃO muda

- Steering de encerramento continua existindo (para o agente que conseguir executar)
- Mistake notes, quality ratings, MEMORY.md = agent-side (contextual)
- Nada quebra se o agente faz O shutdown — só garante que se não fizer, o mínimo está coberto

---

## 8. Métricas de sucesso

| Antes | Depois |
|-------|--------|
| Harvest executa em <30% das sessões | Harvest executa em 100% (server-side) |
| WAL checkpoint depende do agente | WAL checkpoint a cada 30min + pre-backup |
| Backup depende do agente lembrar | Backup a cada 1h via timer |
| Sessão sem encerramento = dados perdidos | Próximo startup detecta e recupera |

---

## 9. Relação com upstream

- Phase 1 (WAL periódico): fork-only, trivial
- Phase 2 (session_end → harvest): propor como RFC upstream (Henry já fez PR #97 com auto-capture on Stop para Claude hooks — mesma direção)
- Phase 3 (gap detection): agent-side, não precisa de mudança no server
- Phase 4 (timer backup): infra local, irrelevante para upstream
