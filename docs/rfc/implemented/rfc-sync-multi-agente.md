# Sistema de Sincronização de Memórias Multi-Agente

**Data**: 2026-08-24  
**Autor**: Claudio + Zero  
**Status**: IMPLEMENTADO e OPERACIONAL

---

## Problema

Múltiplos agentes (Zero, Chakotay, Trip, Scotty, T'Pol) em máquinas diferentes geram memórias e tarefas independentemente. Sem sync, cada agente opera com visão parcial do todo. O mecanismo anterior (restore-db) era tudo-ou-nada e perdia grafo/beliefs locais.

## Solução: Sync Incremental P2P

Cada máquina produz um hot.db (VACUUM INTO, self-contained) e os outros consomem as memórias faltantes via import MCP.

### Arquitetura

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Zero (289)   │    │Chakotay(sir) │    │  Trip (soc)  │    │Scotty+T'Pol  │
│ Kiro CLI     │    │ Kiro Crew    │    │ Kiro Crew    │    │CLI+Hermes VPS│
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
   hot-backup.sh       hot-backup.sh       hot-backup.sh       hot-backup.sh
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
┌─────────────────────────────────────────────┐    ┌──────────────────────┐
│   OneDrive/Insync (memory-backups/*.latest)  │←──→│  VPS ~/memory-backup │
│  sqlite_vec-{host}.latest.hot.db             │    │  (via scp cada 12h)  │
│  tasks-{host}.latest.hot.db                  │    └──────────────────────┘
└─────────────────────────────────────────────┘
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
 sync-memories-     sync-memories-     sync-memories-     sync-memories-
 incremental.sh     incremental.sh     incremental.sh     incremental.py
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
   memory_store         memory_store        memory_store        memory_store
   (MCP :3202)          (MCP :3202)         (MCP :3202)         (MCP :8000)
```

### Princípios

1. **Só memórias são sincronizadas** — graph, beliefs, embeddings são DERIVADOS (regeneram localmente)
2. **Import via MCP** — garante FTS, embeddings, dedup semântica
3. **Validação de integridade** — hot.db < 1MB é rejeitado (guard contra zero bytes)
4. **Batch limitado** — 100 memórias por ciclo por fonte (throttle)
5. **Idempotente** — content_hash como chave; duplicatas ignoradas
6. **P2P via filesystem** — sem servidor central, cada um produz e consome

---

## Scripts

### Máquinas locais (DNBSCDC289, sirdata, socrates)

| Script | Função | Frequência |
|--------|--------|-----------|
| `hot-backup.sh` | VACUUM INTO → memory-backups/{host}.latest.hot.db + TS rotacionado | */30 cron |
| `sync-memories-incremental.sh` | Diff content_hash (lê memory-backups/*.latest) + import via memory_store MCP | */30 cron |
| `sync-tasks-incremental.sh` | Diff work_items (lê memory-backups/*.latest) + import via import_graph MCP (merge) | */30 cron |
| `sync-vps.sh` | Push hot.db → VPS + Pull scotty.hot.db | 7h/19h cron |
| `memory-maintenance.sh` | Harvest, consolidate, facts, cleanup, quality (catch-up) | */30 cron |
| `backup-and-sync.sh` | Backup datado em memory-backups/ com retenção 4 dias | 18h cron |

> **15/set/2026:** backup consolidado em `memory-backups/` (antes espalhava entre `global/` e `memory-backups/`). `global/` = só config compartilhada. O `.latest.hot.db` (sem rotação) é o canal de sync entre máquinas.

### VPS (cfnarede.dev)

| Script | Função | Frequência |
|--------|--------|-----------|
| `~/scripts/hot-backup.sh` | VACUUM INTO → scotty.hot.db | */30 cron |
| `~/scripts/sync-memories-incremental.py` | Import memórias das outras máquinas | */30 cron |

---

## Crontab por máquina

### DNBSCDC289 (e sirdata/socrates quando replicado)
```
0 18 * * *     backup-and-sync.sh
*/30 * * * *   hot-backup.sh
*/30 * * * *   memory-maintenance.sh
*/30 * * * *   sync-memories-incremental.sh
*/30 * * * *   sync-tasks-incremental.sh
0 7,19 * * *   sync-vps.sh
```

### VPS (cfnarede.dev)
```
*/30 * * * *   hot-backup.sh
*/30 * * * *   sync-memories-incremental.py
0 3 * * *      backup-db.sh (translation-one, pré-existente)
```

---

## Validações e Guards

- **Tamanho mínimo**: hot.db < 1MB → REJEITADO (tanto no backup quanto no sync)
- **SHA256 sidecar**: se existe, validado antes de consumir
- **Integrity check**: `PRAGMA integrity_check` no hot-backup
- **Skip próprio**: cada máquina ignora seu próprio hot.db no sync
- **Batch limit**: 100 memórias por fonte por ciclo (evita sobrecarga)
- **Throttle**: 100ms entre requests MCP

---

## Derivados (regeneram automaticamente)

| Artefato | Gerado por | Quando |
|----------|-----------|--------|
| memory_graph (edges) | fact_extraction + entity_linking | Scheduler interno (6h) + memory-maintenance catch-up |
| beliefs | belief_service.derive_beliefs() | Scheduler interno (diário 3h) |
| embeddings | paraphrase-multilingual-MiniLM-L12-v2 | On-demand na busca ou no memory_store |
| FTS index | Trigger SQLite | Automático no INSERT (via memory_store MCP) |

---

## Decisões de Design

1. **Import via MCP (não INSERT direto)** — garante FTS + embeddings + dedup
2. **Unidirecional por máquina** — cada um produz hot.db, outros consomem. P2P.
3. **VPS via scp (não Insync)** — VPS não tem Insync, sync explícito cada 12h
4. **Tasks via import_graph(merge)** — trata items + notes + dependencies corretamente
5. **Derivados não sincronizados** — regeneram localmente, evita conflitos de graph edges
6. **conversation_id: "sync-incremental"** — bypass dedup semântica no import

---

## Serviços Removidos (cleanup 24/ago)

- cao-server.service (CAO não utilizado)
- mcp-proxy.service (substituído por MCPs HTTP direto)
- piper-tts.service (voice mode desativado)
- voicemode-kokoro.service (idem)
- whisper-backend.service (idem)

## Crons Removidos (cleanup 24/ago)

- kiro-heartbeat.sh (path errado, inútil)
- backup-sessions.sh (já preservou tudo)
- kiro-perf-metrics.sh (nunca consultado)
- find -delete traces (traces não gerados mais)

---

## Erros Encontrados e Correções (26/ago/2026, sirdata)

### 1. restore-db-from-sync.sh matou o banco local (INCIDENTE)

**Sintoma:** no startup do sirdata, o banco local (286MB, 18.243 mems) foi substituído
pela fonte DNBSCDC289 (351MB, 19.364 mems). 91 memórias local-only ficaram para trás.

**Causa raiz:** `setup-workstation.sh §11b` chamava `restore-db-from-sync.sh`
INCONDICIONALMENTE no startup. O restore é DESTRUTIVO — compara score composto
(memories + graph×2 + beliefs) e substitui o banco inteiro quando a fonte remota
tem score maior, mesmo com banco local válido. Redundante e perigoso agora que o
sync incremental já traz memórias faltantes sem sobrescrever.

**Impacto real:** baixo — das 91, eram 89 trackings `harvested_sessions:*` + 2
subprodutos de `memory-distill` (um auto-declarado "SKIP"). Zero conhecimento real perdido.

**Fix aplicado (propaga via Insync para socrates/DNBSCDC289):**
1. `setup-workstation.sh §11b`: restore agora só dispara em disaster-recovery —
   banco AUSENTE ou <100 mems (`DB_MIN_MEMS`). Banco válido → pula, sync incremental cuida.
2. `restore-db-from-sync.sh`: cabeçalho remarcado DISASTER RECOVERY ONLY / uso manual.

**Antes de qualquer restore destrutivo:** preservar PRE_RESTORE.
Ex.: `~/local-data/preserved-<host>-pre-restore-<data>.db`.

### 2. sync-vps.sh timeout em teste manual (FALSO POSITIVO)

**Sintoma:** `timeout 90 bash sync-vps.sh` → exit 124.
**Causa:** PUSH do hot.db (~351MB) para a VPS via scp excede 90s. NÃO é falha —
no cron real não há timeout. Guard de conectividade SSH (BatchMode) funciona.

### 3. sync-memories-incremental.sh "não loga" (COMPORTAMENTO CORRETO)

**Sintoma:** roda com exit 0 mas não cria `logs/sync-incremental.log`.
**Causa:** quando não há memórias faltantes (`missing_json=[]`, count=0), o script
faz `continue` sem logar. Com banco já sincronizado, sai limpo. Esperado.

---

## Replicar no socrates / DNBSCDC289

Os scripts chegam via Insync (`~/dtp/ai-configs/scripts/`). Falta só o **crontab**
(não sincroniza). Adicionar (ajustar path se `~/dtp` diferir):

```
*/30 * * * * bash ~/dtp/ai-configs/scripts/hot-backup.sh
*/30 * * * * bash ~/dtp/ai-configs/scripts/sync-memories-incremental.sh
*/30 * * * * bash ~/dtp/ai-configs/scripts/sync-tasks-incremental.sh
*/30 * * * * bash ~/dtp/ai-configs/scripts/memory-maintenance.sh
0 7,19 * * * bash ~/dtp/ai-configs/scripts/sync-vps.sh
0 18 * * *   bash ~/dtp/ai-configs/scripts/backup-and-sync.sh
```

**Validação pós-setup:**
1. Backup do crontab antes: `crontab -l > ~/dtp/ai-configs/backups/crontab-<host>-$(date +%Y%m%d-%H%M%S).bak`
2. Banco íntegro: `sqlite3 ~/local-data/mcp/sqlite_vec.db "SELECT COUNT(*) FROM memories;"` (>100)
3. Smoke test: `bash sync-memories-incremental.sh` deve sair 0 (SSH VPS opcional).
4. Confirmar restore NÃO dispara em rotina: rodar a lógica do §11b — com banco válido, deve reportar "restore PULADO".
