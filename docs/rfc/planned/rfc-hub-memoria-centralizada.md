# SPEC ARQUITETURAL — Hub de Memória Multi-Agente Centralizado (local-first estrela)

**Data:** 2026-09-21
**Autor:** Claudio + Zero (Kiro CLI, papel arch-analyst)
**Status:** DRAFT — spec executável (origina tarefas G3 RED depois)
**Escopo:** arquitetura + requisitos. NÃO é implementação.
**Base de código:** fork `~/git/mcp-memory-service-dev` (worktree em `feat/nli-observability`); serviço roda da branch `service`/`main` (v11.12.0) no repo `~/git/mcp-memory-service`.
**RFCs relacionadas (repo `~/git/mcp-memory-service`, branch main):**
- `docs/rfc/rfc-agent-id-multi-agent.md` (v0.1 draft, 11 EARS R1–R11, 3 fases; GitHub #1100, Henry confirmou "is implementing it" para Fase 1).
- `docs/rfc/rfc-self-service-memory-intelligence.md` (prior art per-agent; assume agent_id existente).
- `~/git/mcp-memory-service-dev/specs/phase3-nli-contradiction.md` (RFC #732, pipeline NLI 4 estágios; Fase 3 usa isto).

> **CORREÇÃO de premissa do briefing:** os arquivos `docs/rfc/rfc-agent-id-multi-agent.md` e `rfc-self-service-memory-intelligence.md` **NÃO estão** no worktree `~/git/mcp-memory-service-dev` (nem em `service`), e sim no repo irmão `~/git/mcp-memory-service` (branch `main`). O `-dev` tem base `upstream/main` e não carrega os docs fork-only. Todas as demais premissas do briefing foram confirmadas no código (ver §11 Evidências).

---

## 1. Visão — Hub local-first em estrela (não N×N)

### Problema atual (topologia N×N)
Hoje cada máquina Zero puxa o `hot.db` de **todas** as outras via cópia no OneDrive + `sync-memories-incremental.sh` (crontab */30). Scotty e T'Pol têm bancos **separados**, sem sync automático real. Isso é uma malha N×N (cada nó fala com cada nó), que causou 3 bugs reais (§2 do briefing, todos confirmados):
1. `created_at` carimbado no destino (corrigido hoje no script).
2. Ruído de consolidação replicado (2178 cards = ~10% de 506MB).
3. Contradições cross-agent (40 `conflict:unresolved` T'Pol/Scotty tratados como mesmo autor).

### Topologia-alvo (estrela, local-first)
```
                         ┌──────────────────────────────────┐
                         │        VPS cfnarede.dev           │
                         │  ┌────────────────────────────┐   │
                         │  │   HUB (banco autoritativo) │   │
                         │  │   consolidação LIGADA      │   │
                         │  │   MCP_CONSOLIDATION=true   │   │
                         │  └────────────┬───────────────┘   │
                         │      leitura cruzada (pool)        │
                         │   ┌───────────┴──────────────┐     │
                         │  Scotty(work)          T'Pol(work) │
                         │  consolidação OFF     consolidação OFF │
                         └──────▲───────────────────▲─────────┘
                                │ sync incremental   │  (*/30 min, bidirecional)
              ┌─────────────────┼───────────────────┼─────────────────┐
              │                 │                    │                 │
      ┌───────┴──────┐  ┌───────┴──────┐     ┌───────┴──────┐
      │ DNBSCDC289   │  │  sirdata     │     │  socrates    │
      │ (Zero, VPN)  │  │  (Zero, casa)│     │  (Zero, casa)│
      │ banco LOCAL  │  │  banco LOCAL │     │  banco LOCAL │
      │ consolid.OFF │  │  consolid.OFF│     │  consolid.OFF│
      └──────────────┘  └──────────────┘     └──────────────┘
```

**Princípios:**
- **LOCAL-FIRST:** cada agente lê/escreve no banco local (rápido, offline-tolerante). Rede caindo NÃO derruba a memória.
- **ESTRELA:** cada ponta fala **só com o hub**, nunca com as outras pontas (elimina N×N e a replicação combinatória).
- **SYNC ASSÍNCRONO */30:** não há leitura remota em tempo real (decisão do Claudio).
- **CONSOLIDAÇÃO CENTRALIZADA:** só o hub gera `[TREND]/[PATTERN]/[GAP]/Cluster`; pontas recebem via sync, não geram.
- **VOLUME BAIXO:** ~80–130 memórias/dia, média 531 bytes ⇒ ~70 KB/dia. Não justifica event-log distribuído.

---

## 2. Identidade — agent_id + host (impressão digital quem + onde)

Cada memória deve carregar **quem** a escreveu (`agent_id`) e **onde** (`host`).

### 2.1 host (JÁ EXISTE — reusar)
`store_memory(client_hostname=...)` em `services/memory_service.py:373+`:
- adiciona tag `source:{hostname}` (memory_service.py ~L420-423);
- grava `metadata["hostname"] = client_hostname` (L424-426).
Env `MCP_MEMORY_INCLUDE_HOSTNAME` (`config/consolidation.py:14`).

**Gap real de host:** o `sync-memories-incremental.sh` **não passa `client_hostname`** no push MCP (o payload só manda `content`/`metadata.tags`/`type`/`conversation_id`). Logo, memórias sincronizadas **perdem a estrutura de host** do autor original. A fonte tem o dado (a query SELECT já traz tudo), mas o import não o propaga.

### 2.2 agent_id (GAP — implementar no memory_store comum = Fase 1 da RFC #1100)
- Já existe em `commit_session_legacy` (server_impl.py:2149,2169) e em `auto_commit` do harvest (server_impl.py:1877; schema em registry.py:853).
- **NÃO existe** no tool `memory_store` (o usado 99% do tempo): o schema em `registry.py:26-108` só declara `content`, `conversation_id`, `metadata{tags,type}`, `store`. Sem `agent_id`, sem `client_hostname`.
- Padrão a seguir: `Memory.source_type`/`credibility` são **properties sobre metadata** com getter/setter (memory.py:259-278). `agent_id` deve ser idêntico: property `metadata.get("agent_id")`, zero migração de schema.

### 2.3 Vocabulário controlado
| Eixo | Valores | Fonte |
|------|---------|-------|
| `agent_id` | `zero`, `tpol`, `scotty` | argumento do tool OU env `MCP_AGENT_ID` (server_impl.py:1877) |
| `host` | `dnbscdc289`, `sirdata`, `socrates`, `vps` | `client_hostname` → `metadata.hostname` + tag `source:{host}` |

### 2.4 Backward-compat
`null = unknown` em ambos os eixos (R3/R9 da RFC). Memórias legadas sem agent_id/host continuam válidas; NLI e busca caem no comportamento atual quando o sinal falta.

---

## 3. Topologia de sync — banco mestre e pool

### Pergunta central: hub tem banco dedicado, ou pool único compartilhado por Scotty+T'Pol?

Estado real (confirmado): Scotty e T'Pol têm **bancos separados** na VPS, sem sync automático. Scotty diagnosticou que 2 bancos separados exigem leitura cruzada para virar malha real.

### Opção A — Pool único na VPS (um banco, Scotty+T'Pol+hub compartilham)
- **Prós:** leitura cruzada automática (T'Pol vê o que Scotty escreveu); um só ponto de consolidação; sync das pontas fala com 1 alvo.
- **Contras:** contenção de escrita SQLite (WAL mitiga, mas volume é baixo então OK); um bug de consolidação afeta os dois agentes; acoplamento operacional.

### Opção B — Banco dedicado do hub, separado dos bancos de trabalho de Scotty/T'Pol
- **Prós:** isola o "banco canônico" (destino de sync + consolidação) dos bancos "de trabalho quente" dos agentes VPS.
- **Contras:** reintroduz o problema que Scotty apontou (bancos separados = precisa de sync interno VPS entre Scotty/T'Pol/hub); mais partes móveis; consolidação teria que rodar sobre um banco que não é o de trabalho.

### RECOMENDAÇÃO: **Opção A — pool único na VPS é o "hub"**
Justificativa: volume baixíssimo (~70 KB/dia) elimina a preocupação de contenção; a leitura cruzada que Scotty pediu vem de graça; o hub SER o banco de trabalho de Scotty+T'Pol evita um sync intra-VPS redundante. O `agent_id` (§2) é o que dá a separação lógica que a separação física de bancos daria — sem os custos. **Um banco autoritativo na VPS = mestre**; as 3 máquinas Zero são réplicas locais que sincronizam bidirecionalmente com ele.

**Mestre = o pool único da VPS.** Em conflito de dedup exato (mesmo `content_hash`), o hub é a fonte da verdade para timestamps (importer preserva `created_at` — importer.py:216).

---

## 4. Consolidação só no hub

### Decisão
`MCP_CONSOLIDATION_ENABLED=false` em TODAS as pontas (3 máquinas Zero + processos de trabalho Scotty/T'Pol se distintos); `=true` só no processo de consolidação do hub. Env lido em `config/consolidation.py:11`. Scheduler APScheduler em `consolidation/scheduler.py`.

### Efeito
Os cards `[TREND]/[PATTERN]/[GAP]/Cluster` passam a ser gerados **num único lugar**. Não há mais N geradores produzindo hashes divergentes por máquina → **acaba a inflação combinatória**. Os cards fluem do hub para as pontas via sync (read-path), como qualquer outra memória.

### Limpeza dos 2178 cards existentes
1. **Backup primeiro:** `VACUUM INTO` do banco de cada nó antes de qualquer delete (cópia OneDrive já é a prática — steering bootstrap-rules §Multi-máquina).
2. **Identificar cards de consolidação:** por tag/prefixo (`[TREND]`, `[PATTERN]`, `[GAP]`, `Cluster`) e/ou `memory_type` de consolidação.
3. **Soft-delete no hub**, deixar a consolidação central re-gerar o conjunto canônico a partir do corpus unificado.
4. **Propagar deleção às pontas** (o sync precisa passar a honrar `deleted_at` — hoje o script só olha `WHERE deleted_at IS NULL`, então soft-deletes no hub NÃO reaparecem, mas soft-deletes locais também não são propagados; ver R-sync abaixo).
5. **`VACUUM`** pós-limpeza para recuperar os ~10% de 506MB.

---

## 5. Resolução de conflito cross-agent (Fase 3 RFC #1100 + RFC #732)

### Problema (confirmado)
`reasoning/nli.py::detect_contradictions_nli` decide contradição/quarentena **sem olhar autor** — trata T'Pol e Scotty como o mesmo autor. Resultado: 40 `conflict:unresolved` que são, na verdade, perspectivas legítimas de agentes diferentes.

### Como agent_id habilita a resolução
Com `agent_id` persistido (Fase 1), a Fase 3 da RFC estende o pipeline NLI 4-estágios (specs/phase3-nli-contradiction.md):
- **Mesmo `agent_id` não-null contradizendo** → contradição real → mantém quarentena (R7).
- **`agent_id` distintos não-null contradizendo** → `perspective_conflict` (status novo, NÃO quarentena) (R8).
- **Algum `agent_id` null** → comportamento atual author-agnostic (R9).

Os 40 conflitos existentes serão reclassificados quando (a) as memórias envolvidas tiverem agent_id (backfill opcional ou re-store) e (b) a Fase 3 estiver ativa no hub. Registro de conflito já existe (`web/api/conflicts.py`, `memory_conflicts` table).

---

## 6. Transporte de sync

### Opção A — Manter o `sync-memories-incremental.sh` corrigido, adaptado para estrela
Estado hoje (confirmado no script): diff por `content_hash` ativo, batch ≤100/ciclo, import via MCP `memory_store`, restauração de `created_at` original via UPDATE por hash (bugfix 21/set), lock flock, verificação pós-hoc no banco (Transport-closed-após-gravar). É N×N (varre `hot.db` de todas as outras máquinas).

### Opção B — Migrar para o importer oficial (`sync/importer.py`)
`_create_memory_from_dict` (importer.py:189-217) já **preserva `created_at`** nativamente e adiciona `metadata.import_info.source_machine` (L199-206), dedup por `content_hash` (`_get_existing_hashes`, L219). Faz nativamente o que o script hoje remenda por fora.

### RECOMENDAÇÃO: **híbrido — manter o script como orquestrador de transporte, MAS**
1. **Reapontar para estrela:** cada ponta sincroniza só com o hub (VPS), não com todas as outras. Elimina o N×N na origem.
2. **Passar `client_hostname` e `agent_id`** no payload do push (fecha o gap §2.1) — depende da Fase 1 (agent_id no memory_store) e de expor `client_hostname` no schema do tool.
3. **Honrar `deleted_at`** (propagar soft-deletes hub↔ponta) para a limpeza §4 funcionar.
4. **Não** migrar para event-log distribuído: volume não justifica (decisão do Claudio, confirmada pelo cálculo ~70 KB/dia).

O importer oficial é a referência de corretude (preserva timestamp + source_machine); o script pode convergir para chamá-lo/espelhá-lo, mas a troca completa é opcional e de menor prioridade que reapontar a topologia.

---

## 7. Plano em fases (pequenas, reversíveis, com dependências)

| Fase | Entrega | Depende de | Onde roda | Reversível? |
|------|---------|------------|-----------|-------------|
| **F0** | Backup (VACUUM INTO) de todos os bancos + snapshot do estado | — | todas | N/A (é a rede de segurança) |
| **F1** | `agent_id` no `memory_store` comum (property + handler + schema) = **Fase 1 RFC #1100** | F0 | branch `service` (fork-only imediato); PR `feat/agent-id` p/ upstream depende do **Henry** | sim (aditivo, null=unknown) |
| **F2** | `client_hostname` + `agent_id` no payload do sync script | F1 | script (fork-only, imediato) | sim (reverter script) |
| **F3** | Desligar consolidação nas pontas (`MCP_CONSOLIDATION_ENABLED=false`), ligar só no hub | F0 | config env de cada nó (imediato) | sim (reverter env) |
| **F4** | Reapontar sync para estrela (ponta↔hub, fim do N×N) + honrar `deleted_at` | F1,F2 | script (fork-only, imediato) | sim |
| **F5** | Limpeza dos 2178 cards + VACUUM (soft-delete no hub, re-gerar) | F3,F4 | hub + propagação | parcial (backup F0 permite restore) |
| **F6** | Filtro `agent_id` em search/list = **Fase 2 RFC #1100** | F1 | branch `service` (imediato); upstream depende do **Henry** | sim |
| **F7** | NLI cross-agent `perspective_conflict` = **Fase 3 RFC #1100/#732** | F1,F6 | branch `service` (imediato); upstream depende do **Henry** | sim |
| **F8** | Reclassificar os 40 conflitos existentes | F7 | hub | sim |

**Marcação upstream (Henry) vs fork-only (imediato):**
- **Fork-only, roda já na branch `service`:** F0, F2, F3, F4, F5, F8, e as três fases da RFC podem ser aplicadas ao serviço local sem esperar o Henry (o serviço roda do fork).
- **Depende do Henry (PR upstream):** os PRs `feat/agent-id` (F1/F6/F7 como contribuição). Não bloqueiam o serviço; só a contribuição upstream.
- **Isolamento de colisão (RFC §4.4):** conjunto de arquivos da agent-id é DISJUNTO das branches da pilha harvest; único contato é `server_impl.py` (schema Fase 1), bloco distante do harvest-provenance.

---

## 8. Riscos

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Rede/VPN cai (DNBSCDC289) | Ponta fica sem sync | LOCAL-FIRST: agente continua lendo/escrevendo local; sync recupera no próximo */30 (catch-up já existe no state file) |
| VPS indisponível | Sem hub temporariamente | Pontas seguem locais; consolidação atrasa (não crítica, roda background); sync retoma quando VPS volta |
| Migração bancos separados→pool único (Scotty/T'Pol) | Perda/duplicação de memória | F0 backup obrigatório; dedup por `content_hash` no merge; validar contagem antes/depois |
| Colisão com pilha de PRs aberta (#1250, #1252, fila) | Conflito de merge em `server_impl.py`/`harvester.py` | agent-id sai de `upstream/main` limpa, arquivos disjuntos; aplicar no `service` sem tocar branches de PR (runbook §disciplina de transporte) |
| Soft-delete não propagado hoje | Cards deletados no hub reaparecem via ponta | R-sync (§6.3): honrar `deleted_at` antes da limpeza F5 |
| `agent_id` errado/ausente em massa | perspective_conflict não dispara | null=unknown cai no comportamento atual (seguro); backfill opcional |
| Consolidação central sobrecarrega VPS | CPU/latência | Volume baixo; scheduler em background; monitorar |

---

## 9. Requisitos EARS + Critérios de Aceite

> Convenção: uma ação por frase, sujeito=componente, SHALL=obrigatório, testável (origina G3 RED).

### Funcional — Identidade
**RF1** — WHEN a memory is stored via `memory_store` with an `agent_id` argument, THE store handler SHALL persist it in `metadata.agent_id`.
**RF2** — WHERE `agent_id` is not provided, THE store handler SHALL fill it from `MCP_AGENT_ID` when set.
**RF3** — WHERE neither `agent_id` argument nor `MCP_AGENT_ID` is present, THE stored memory SHALL keep `agent_id` null (unknown).
**RF4** — WHEN a memory is stored with `client_hostname`, THE sync push SHALL forward that hostname so the imported memory retains `metadata.hostname` and tag `source:{host}`.
**RF5** — WHEN `Memory.agent_id` is read, THE model SHALL return `metadata.get("agent_id")`.

### Funcional — Topologia / Sync
**RF6** — WHEN a spoke node runs the sync job, THE job SHALL synchronize only with the VPS hub and SHALL NOT pull from other spoke nodes.
**RF7** — WHEN a memory is imported by the sync job, THE job SHALL preserve the source `created_at` timestamp.
**RF8** — WHEN a memory is soft-deleted on the hub, THE sync job SHALL propagate `deleted_at` to spoke nodes.
**RF9** — WHEN the hub imports two memories with identical `content_hash`, THE hub SHALL keep a single record (exact dedup preserved).

### Funcional — Consolidação
**RF10** — WHERE a node is a spoke, THE node SHALL run with `MCP_CONSOLIDATION_ENABLED=false`.
**RF11** — WHERE the node is the hub, THE hub SHALL run with `MCP_CONSOLIDATION_ENABLED=true`.
**RF12** — WHEN consolidation cards are needed, THE hub SHALL be the sole generator of `[TREND]/[PATTERN]/[GAP]/Cluster` cards.

### Funcional — Conflito cross-agent
**RF13** — WHEN two contradicting memories share the same non-null `agent_id`, THE NLI SHALL treat it as a real contradiction and keep quarantine.
**RF14** — WHEN two contradicting memories have distinct non-null `agent_id`, THE NLI SHALL classify it as `perspective_conflict` and SHALL NOT quarantine either memory.
**RF15** — WHERE either memory has a null `agent_id`, THE NLI SHALL fall back to author-agnostic behavior.

### Não-Funcional
**RNF1** — THE identity feature SHALL only add optional metadata keys and optional parameters, never altering existing table schema.
**RNF2** — WHEN a spoke loses network to the hub, THE spoke SHALL continue serving local reads and writes.
**RNF3** — WHEN the network is restored, THE sync job SHALL reconcile within one scheduled cycle (≤30 min).
**RNF4** — THE sync transport SHALL NOT introduce a distributed event-log (volume ~70 KB/day does not justify it).
**RNF5** — WHEN evaluated against the existing NLI test suite (author-less memories), THE Phase 3 change SHALL keep all current quarantine decisions unchanged.
**RNF6** — BEFORE any destructive cleanup, THE operator SHALL produce a `VACUUM INTO` backup of each affected database.

### Critérios de Aceite (verificáveis)
- [ ] `memory_store(agent_id="zero")` → `metadata.agent_id == "zero"` (RF1).
- [ ] Sem arg + `MCP_AGENT_ID=zero` → agent_id preenchido (RF2); sem nada → null (RF3).
- [ ] Memória sincronizada mantém `metadata.hostname` e tag `source:{host}` (RF4).
- [ ] `Memory.agent_id` retorna `metadata.get("agent_id")` (RF5).
- [ ] Spoke sincroniza só com o hub; grep no log não mostra pull peer-to-peer (RF6).
- [ ] `created_at` importado == origem (RF7); soft-delete do hub some na ponta (RF8).
- [ ] Spokes com consolidação OFF; hub ON; contagem de novos cards só cresce no hub (RF10-12).
- [ ] Mesmo agent_id contradizendo → quarantine; distintos → perspective_conflict; null → atual (RF13-15).
- [ ] Suíte NLI existente 100% verde após Fase 3 (RNF5).
- [ ] Backup VACUUM INTO existe antes da limpeza dos 2178 cards (RNF6).
- [ ] Após limpeza+VACUUM, tamanho do banco reduz ~10% (proxy dos 2178 cards).

---

## 10. Fora de escopo (explícito)
- Event-sourcing / event-log distribuído (Henry respondeu "pass"; volume não justifica).
- Migração de schema SQL (agent_id/host vivem em metadata, não em colunas).
- Leitura remota em tempo real (Claudio aceita sync */30; NÃO é centralizado puro).
- Backfill obrigatório de agent_id em memórias legadas (null=unknown é aceitável; backfill é opcional futuro).
- Belief/Bootstrap Profile per-agent além do que a self-service RFC já cobre.
- Camada de autenticação/multi-tenant nova (reusa o deployment atual da VPS).
- Substituição completa do script pelo importer oficial (opcional, menor prioridade que reapontar topologia).

---

## 11. Evidências (arquivo:linha) — premissas confirmadas/refutadas

| Premissa do briefing | Veredito | Evidência |
|----------------------|----------|-----------|
| host via `client_hostname` → `source:{host}` + `metadata.hostname` | ✅ CONFIRMADO | services/memory_service.py:373 (assinatura), ~L420-426 (tag+metadata) |
| `INCLUDE_HOSTNAME` env | ✅ | config/consolidation.py:14 |
| Model usa properties sobre metadata (source_type/credibility) | ✅ | models/memory.py:259 (source_type), 269 (credibility) — com setters |
| `memory_store` comum NÃO aceita agent_id | ✅ CONFIRMADO (gap) | tools/registry.py:26-108 (schema só content/conversation_id/metadata/store) |
| agent_id em commit_session + auto_commit | ✅ | server_impl.py:1877,2149,2169; registry.py:853 |
| `MCP_AGENT_ID` env fallback | ✅ | server_impl.py:1877 |
| `CONSOLIDATION_ENABLED` via env | ✅ | config/consolidation.py:11 |
| importer preserva created_at + import_info.source_machine | ✅ | sync/importer.py:199-206 (import_info), 216 (created_at preservado) |
| sync corrigido hoje (timestamp, lock, verify pós-hoc) | ✅ | ~/Insync/.../scripts/sync-memories-incremental.sh (path real; NÃO em ~/dtp) |
| sync NÃO passa client_hostname no push | ✅ CONFIRMADO (gap) | script: payload MCP só manda content/metadata.tags/type/conversation_id |
| RFC agent-id existe (11 EARS, 3 fases) | ✅ mas ⚠️ path | está em `~/git/mcp-memory-service/docs/rfc/rfc-agent-id-multi-agent.md`, NÃO no `-dev` |
| Phase 3 NLI (perspective_conflict) | ✅ | specs/phase3-nli-contradiction.md (RFC #732) + RFC #1100 §Fase 3 |
| conflito registrado em memory_conflicts | ✅ | web/api/conflicts.py |
| NLI cego a autor hoje | ✅ | RFC #1100 §1 cita reasoning/nli.py::detect_contradictions_nli (autor-agnóstico) |

**Correções apontadas:**
1. Caminho da RFC estava errado no briefing (repo irmão, não `-dev`). Conteúdo confirmado e usado.
2. Caminho do script é `~/Insync/.../ai-configs/scripts/` (OneDrive), symlink/cópia de `~/dtp/ai-configs/`.
3. `-dev` está em `feat/nli-observability`, não em `service` — o serviço roda de `~/git/mcp-memory-service`.


---

## 12. Canal de Transporte sirdata↔VPS — Defesa em Duas Camadas (verificado 24/set/2026)

> **Decisão do Claudio (repetida em várias sessões, formalizada aqui):** o acesso ao hub
> na VPS é protegido por **duas camadas independentes**: (1) nginx com `auth_basic`+htpasswd+TLS
> na `location /memory/`; (2) autenticação nativa do próprio memory-service (API key).
> Regra: **"se fura no nginx, barra no serviço"**. O serviço NUNCA fica exposto por porta aberta.

### Desenho canônico

```
sirdata (cliente)                        VPS cfnarede.dev
─────────────────                        ────────────────────────────────────
delta-sync client  ──HTTPS──▶  nginx :443
                               location /memory/
                               ├─ TLS (Let's Encrypt)
                               ├─ auth_basic + .htpasswd-memory   ◀── CAMADA 1
                               └─ proxy_pass http://127.0.0.1:8000
                                                │
                                       memory-service :8000
                                       ├─ LISTEN 127.0.0.1 (localhost-only, SEM porta aberta)
                                       └─ API key nativa                ◀── CAMADA 2
```

### Estado atual verificado (24/set/2026, `ssh claudio@cfnarede.dev`)

| Item | Estado | Evidência |
|------|--------|-----------|
| VPS memory-service versão | ✅ v11.13.0 | reconstruído 23-24/set (Camadas 1-4) |
| `:8000` bind | ✅ `LISTEN 127.0.0.1:8000` (localhost-only) | `ss -tlnp` — ponto (2) do desenho FEITO |
| Health endpoint (v11.13) | ✅ `/api/health` → 200 (NÃO `/health`, que dá 404) | `/`→200, `/mcp`→405, `/api/health`→200 |
| htpasswd padrão na VPS | ✅ existe molde (agent-chat, builder-one, knowledge-one, translation-one em `/etc/nginx/`) | replicável para `.htpasswd-memory` |
| **nginx `location /memory/`** | ✅ **ATIVA (24/set)** — `location /memory/` auth_basic + `.htpasswd-memory` + proxy_pass 127.0.0.1:8000 | CAMADA 1 FEITA (validada) |
| **API key nativa do serviço** | ✅ **ATIVA (24/set)** — `MCP_API_KEY` na unit, `MCP_ALLOW_ANONYMOUS_ACCESS` removida | CAMADA 2 FEITA (validada) |

### ✅ CANAL COMPLETO — E2E validado de sirdata via HTTPS (24/set/2026)

| Teste (de sirdata → https://cfnarede.dev/memory/) | Resultado | Barreira |
|---|---|---|
| `/memory/api/health` sem nada | 200 | health público por design |
| `/memory/api/memories` sem basic | **401** | Camada 1 (nginx) |
| basic OK + sem api-key | **401** | Camada 2 (serviço) |
| basic OK + `X-API-Key` OK | **200** | passa as duas ✅ |
| basic OK + api-key errada | **401** | Camada 2 |

### ⚠️ GOTCHA CRÍTICO — usar `X-API-Key`, NÃO `Bearer`

O nginx `auth_basic` **ocupa o header `Authorization`** (basic auth). Se o cliente mandar
`Authorization: Bearer <key>`, o nginx sobrescreve com o basic e o Bearer **não chega** ao
backend → serviço barra mesmo com key correta (visto no 1º teste: 401 indevido).

**Solução:** o memory-service aceita a API key por 3 vias — `Authorization: Bearer`, header
`X-API-Key`, ou query param `?api_key=`. Com nginx basic no caminho, usar **`X-API-Key`**
(limpo, não vaza na URL/logs). Cliente delta-sync deve mandar: basic auth (camada 1) +
header `X-API-Key: <chave>` (camada 2).

### Credenciais (na VPS, FORA do sync)
- Camada 1 basic: user `zero`, senha em `~/.config/mcp-memory-basicpass.txt` (0600) · htpasswd bcrypt `/etc/nginx/.htpasswd-memory`.
- Camada 2 API key: `~/.config/mcp-memory-apikey.txt` (0600).
- Backups: unit `.bak-<ts>`, nginx conf `.bak.<ts>`.

### 🔴 CORREÇÃO DE BANCO (25/set/2026) — a virada do hub apontou para banco de teste

**Dívida de doc corrigida (lição "mudou→documenta"):** a virada do hub (21/set backup `pre-hub-update`) + a reescrita da unit (24/set 07:18) + um teste da T'Pol (23/set) deixaram o serviço apontando para o banco ERRADO. Isso NÃO havia sido documentado — descoberto por ssh em 25/set.

**Estado que estava errado (24-25/set):**
- Unit `mcp-memory.service` tinha `MCP_MEMORY_SQLITE_PATH=~/.local/share/mcp-memory/memory.db` = **419 memórias** (banco de TESTE da T'Pol, tag `recomeco-teste`, criado 23/set 21:27).
- O banco autoritativo `sqlite_vec.db` = **19.585 memórias** (real, até 15/set) estava IGNORADO.
- 418 dos 419 já estavam no autoritativo; a única órfã era `[RECOMECO-TESTE] validacao ingest hub VPS 23set` (lixo de teste).

**Correção aplicada (25/set 08:51):**
1. Unit reapontada: `MCP_MEMORY_SQLITE_PATH=...sqlite_vec.db` (backup `mcp-memory.service.bak-a0-20260925-085118`).
2. `memory.db` de teste preservado como `memory.db.teste-tpol-23set.bak-<ts>` (não apagado).
3. `daemon-reload` + restart. Validado: `/api/health` → 19.585 mems, backend sqlite-vec, model multilingual; search E2E retorna conteúdo real.
4. Backup do autoritativo antes de mexer: `sqlite_vec.pre-v1114.20260925-085213.db` (VACUUM INTO).

**Estado REAL após correção (25/set):**
| Item | Valor |
|------|-------|
| Banco servido | `~/.local/share/mcp-memory/sqlite_vec.db` (19.585 vivas) |
| Versão código | **v11.14.0** (subida 25/set 08:56 após corrigir remote) |
| agent_id | F1+F2 presentes (merge fork 23/set, HEAD b28ae277) — pré-req do hub OK |
| Embeddings | ONNX multilingual (paraphrase-multilingual-MiniLM-L12-v2), dim 384 |
| Serviço | systemd `--user mcp-memory.service`, active, roda `~/.local/bin/memory` (uv tool editable de `~/git/mcp-memory-service`) |

**✅ Remotes da VPS CORRIGIDOS (25/set):** `upstream` reapontado de Codeberg congelado → `github.com/doobidoo/mcp-memory-service` (origem viva). `git merge upstream/main` trouxe v11.14.0 (limpo). Reinstalado editable no uv tool COM `--with onnxruntime --with tokenizers`. Serviço v11.14.0 active, banco 19.585, search E2E OK. Backups: `backup/main-vps-pre-real-v1114-<ts>`, `sqlite_vec.pre-v1114.<ts>.db`. Startup leva ~1min40 (carrega ONNX+19.585 mems); health responde 0.004s depois de pronto.

### ✅ A2 — Consolidação ligada no hub (25/set 09:09)
Unit `mcp-memory.service` ganhou (com aspas — systemd corta valor no espaço sem elas):
```
Environment=MCP_CONSOLIDATION_ENABLED=true
Environment=MCP_SCHEDULE_DAILY=03:00
Environment="MCP_SCHEDULE_WEEKLY=SUN 04:00"
Environment="MCP_SCHEDULE_MONTHLY=01 04:30"
```
GOTCHA: sem aspas, `SUN 04:00` chega como `SUN` → "Invalid weekly schedule format". Backup: `mcp-memory.service.bak-a2-<ts>`. PID atual: 0 erros de trigger, startup completo. Hub agora é o ÚNICO que consolida (Scotty/Spock em disabled-backup; só 1 serviço memory ativo = estrela de fato).

### ✅ A3 — Sync incremental corrigido (25/set 09:07)
`~/scripts/sync-memories-incremental.py` estava dando SKIP há dias: `check_health()` fazia `POST /mcp` (autenticado) sem key → 401 → falso "serviço morto". CORRIGIDO: check_health usa `/api/health` (público); `import_memories` agora manda `X-API-Key` (lida de `~/.config/mcp-memory-apikey.txt`); +log anti-silêncio quando ciclo sem novidades. Backup: `.bak-<ts>`. Validado: `check_health()=True`, ciclo roda, log "OK: ciclo sem novidades".
⚠️ DERIVA (fora da VPS): os hot.db dos hosts em `~/memory-backup/` estão ANTIGOS (sirdata 14/set, socrates 12/set, DNBSCDC 15/set) — os hosts pararam de subir hot.db recente ~10 dias. Problema do lado dos HOSTS (hot-backup.sh + OneDrive→VPS), não da VPS. É a deriva que o delta-sync (event-log) quer eliminar. Hub (19.585) já contém o que esses hot.db antigos têm → sync não importa nada (correto).

**⚠️ GOTCHA repetido (mistake note a1de2c29):** reinstalar editable no uv tool (`uv tool install --force --editable .`) REMOVE onnxruntime+tokenizers → serviço crasha na proteção #1225 (recusa hash pseudo-vectors). SEMPRE reinstalar com `--with onnxruntime --with tokenizers` e confirmar import antes do restart. Aconteceu 22/set (sirdata) e 25/set (VPS).


### Mecanismo de auth (doc oficial `docs/agents/http-generic.md`)

- **Ativar:** `Environment=MCP_API_KEY=<chave>` na unit + REMOVER `MCP_ALLOW_ANONYMOUS_ACCESS`.
- **Cliente:** header `Authorization: Bearer <chave>`.
- **`/api/health` é PÚBLICO por design** (health check não exige auth) — testar enforcement em `/api/memories`.
- `X-Agent-ID` é header SEPARADO (Fase 2 agent_id) — coexiste com o Bearer.

### CAMADA 2 — implementada e validada (24/set/2026)

- Chave gerada `openssl rand -hex 32`, salva em `~/.config/mcp-memory-apikey.txt` (0600, FORA do sync).
- Unit `~/.config/systemd/user/mcp-memory.service`: +`MCP_API_KEY`, −`MCP_ALLOW_ANONYMOUS_ACCESS`. Backup `.bak-<ts>`.
- Validação: `/api/memories` sem auth → **401** · Bearer correto → **200** · Bearer errado → **401**. ✅
- ⚠️ Startup do serviço leva ~10-15s (carga ONNX) — aguardar antes de testar após restart.

### Lacunas a fechar (para destravar Camada 5 / delta-sync)

1. **CAMADA 2 (serviço):** desligar `MCP_ALLOW_ANONYMOUS_ACCESS=true` e ativar API key nativa
   no `~/.config/systemd/user/mcp-memory.service` da VPS. Restart. (Fazer ANTES de expor via nginx.)
2. **CAMADA 1 (nginx):** criar `.htpasswd-memory` + adicionar `location /memory/` com
   `auth_basic` + TLS + `proxy_pass http://127.0.0.1:8000/`. `nginx -t` + reload.
3. **Teste de fora:** de sirdata, `curl https://cfnarede.dev/memory/api/health` deve exigir
   basic auth (401 sem credencial, 200 com). Confirmar que sem API key o serviço barra mesmo
   passando o nginx.

### Por que isto importa (contexto que escapava entre sessões)

O canal define o protocolo do delta-sync (RFC `docs/rfc/rfc-delta-sync.md`). O `sync_server.py`
da RFC fala HTTP com auth (R5: servidor vê só metadata quando cripto ativa). Esse HTTP é
exatamente o `location /memory/` do nginx + API key do serviço. Sem o canal fechado, o
event-log delta não tem transporte confiável nem atribuição segura de `agent_id` (Fase 2, PR #1297).

**Cadeia:** Fase 2 agent_id (header X-Agent-ID) → canal 2-camadas (esta seção) → delta-sync (Camada 5).
