# SPEC — Delta-Sync Fase 4b: orquestração do PULL (sync_from_peer)

- **Data:** 2026-10-07
- **Arco:** delta-sync #1345 · **Item:** 56bf1faa · **Branch:** `feat/delta-sync`
- **Cadeia:** RFC §7 → ADR-0023/0026 → **este SPEC** → gate G0-G5 + E2E
- **Escopo:** 4b = ORQUESTRAR o PULL (ligar as peças da 4a num loop testável). Push=4c, scheduler/E2E-VPS=4d.

## Técnica grafo-baseline (aplicada neste gate)
Baseline ANTES (grafo): `apply_remote_event`/`get_events_since`/`advance_sync_cursor` = 0 callers de produção. BackgroundSyncService (`_sync_loop`) move ESTADO, não eventos — fundir criaria dupla-escrita (RFC §7 proíbe) → orquestrador SEPARADO (ADR-0023). DELTA a verificar no Gate 4: as 3 peças ganham caller de produção = o orquestrador; orquestrador SEM aresta p/ `_sync_loop`.

## Requisitos cobertos
- **R1** (transferir só mudanças desde o último sync) — orquestra o pull incremental por cursor.
- Liga: Fase 4a (feed/apply/cursor) num fluxo automático. NÃO cobre: push (4c), scheduler (4d), anti-impersonação (4c).

## Requisitos funcionais (EARS)

**F1 — pull orquestrado**
> WHEN `sync_from_peer(local, peer, peer_id)` is called, THE orchestrator SHALL read the current `sync_cursor[peer_id]`, call `peer.get_events_since(cursor, limit)`, apply each event via `apply_remote_event`, and advance the cursor per page — until `has_more` is false.

**F2 — paginação completa**
> WHILE the feed reports `has_more`, THE orchestrator SHALL continue pulling pages from `next_seq`, applying each, so a feed larger than one page is fully consumed.

**F3 — cursor durável por página**
> WHEN a page is applied successfully, THE orchestrator SHALL advance `sync_cursor[peer_id].last_seq_seen` to the page's `next_seq` durably (commit); a crash mid-sync SHALL resume from the last durable cursor (§8.5).

**F4 — idempotência de ciclo**
> WHEN `sync_from_peer` runs twice against the same feed, THE result SHALL be identical (zero duplicate), via the Phase 1 UNIQUE(agent_id,event_id) + apply idempotency.

**F5 — reconciliação preservada**
> WHILE applying, THE orchestrator SHALL rely on the Phase 2 resolver (via apply): late events do not overwrite the materialized winner; authorship is preserved (§8.4).

**F6 — orquestrador agnóstico/separado**
> THE orchestrator SHALL live in `storage/sync/orchestrator.py`, operate over a `MemoryStorage` local + a peer transport (RemoteHTTPStorage OR another local storage in test mode), and SHALL NOT be wired into `BackgroundSyncService._sync_loop` (ADR-0023).

## Requisitos não-funcionais
- **NF1** sem migração nova (sync_cursor é da 4a).
- **NF2** disparo manual (método awaitable); scheduler é 4d (ADR-0026).
- **NF3** modo de teste LOCAL (2 storages, sem rede): o "peer" é um adaptador que lê A.sync_events e serve como get_events_since.
- **NF4** reusa o transporte #1304 (remote_http) sem fundir o loop de estado.

## Critérios de aceite (viram testes RED no Gate 2)
- [ ] **CA1 (F1/F6)** `sync_from_peer` existe em storage/sync/orchestrator.py; pull A→B via adaptador local materializa as memórias de A em B.
- [ ] **CA2 (F2 paginação)** feed com N > limit → todas as N aplicadas (segue has_more/next_seq).
- [ ] **CA3 (F3 cursor)** após sync, sync_cursor[peer].last_seq_seen = maior seq; crash simulado (parar no meio) → re-sync resume do cursor, não do zero.
- [ ] **CA4 (F4 idempotência)** sync_from_peer 2× → estado idêntico, zero duplicata.
- [ ] **CA5 (F5 late/autoria)** evento late no feed não sobrescreve; autoria preservada (agent_id de A em B).
- [ ] **CA6 (F6 anti-fusão)** o orquestrador não referencia BackgroundSyncService/_sync_loop (import/chamada); teste de que opera sobre storage puro.

## E2E a quente (modo local)
1. A (alpha) store 5 distintas (feed > 1 página com limit=2) → `sync_from_peer(B, adaptadorA, "peer-A")`.
2. Confirmar: B tem as 5 materializadas e pesquisáveis; cursor[peer-A]=último seq; autoria=alpha; re-sync = no-op.
3. Paginação: com limit pequeno, todas as páginas consumidas.

## Gate (G0-G5)
- G0/G1 feito (grafo-baseline + Gate 1 seven + ADRs + SPEC).
- G2 RED: rok (CA1-CA6, modo local, anti-skip, confirmar tipos).
- G3 impl: reg — storage/sync/orchestrator.py sync_from_peer (loop de páginas sobre get_events_since+apply+cursor). SEM tocar _sync_loop.
- G4 verify: suite + **DELTA DO GRAFO** (re-trace: apply/get_events ganham caller; orquestrador sem aresta p/ _sync_loop).
- G5 review: tuvok (paginação completa, cursor durável, idempotência, anti-fusão, mutation).
- E2E a quente (modo local) após G5.
