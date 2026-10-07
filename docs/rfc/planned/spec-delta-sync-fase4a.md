# SPEC — Delta-Sync Fase 4a: transporte PULL (feed + apply + cursor)

- **Data:** 2026-10-07
- **Arco:** delta-sync #1345 · **Item:** 56bf1faa · **Branch:** `feat/delta-sync`
- **Cadeia:** RFC §7/§8.4/§8.5 → ADR-0018/0019/0020/0021/0022 → **este SPEC** → gate G0-G5 + E2E
- **Co-autoria RFC:** @ducanhnguyen223 (§8.4, §8.5)
- **Escopo:** Fase 4a = PULL unidirecional (ADR-0018). Push/bidirecional/scheduler = Fase 4b. Backend sqlite_vec.

## Requisitos cobertos
- **R1** (transferir só mudanças desde o último sync) — via feed paginado por seq + cursor.
- **R3/R3'** (reconciliação determinística) — APPLY reusa o resolver (Fase 2).
- **§8.4** (autoria preservada no replay). **§8.5** (cursor por-peer = fonte de verdade).
- Reusa: #1304 remote_http; Fase 1 sync_events; Fase 2 resolver/HLC; Fase 3 embedding_pending.
- NÃO cobre: push, loop bidirecional, scheduler (Fase 4b); anti-impersonação forte server-side (4b).

## Requisitos funcionais (EARS)

**F1 — feed de eventos**
> WHEN `GET /api/sync/events?since_seq=S&limit=N` is called with read access, THE server SHALL return up to N events with seq > S ordered by seq, each with event_id/op/content_hash/agent_id/hlc/embedding_model/payload, enriching `create` events with `content`; plus `next_seq` and `has_more` (ADR-0020/0021).

**F2 — consumo no cliente**
> WHEN the client pulls, THE `remote_http.get_events_since(cursor, limit)` SHALL return the feed page via the authenticated transport.

**F3 — apply idempotente**
> WHEN a remote event is applied, THE apply SHALL insert it into the local `sync_events` preserving agent_id/event_id/HLC (ADR-0022), idempotent via `UNIQUE(agent_id,event_id)` — re-applying is a no-op.

**F4 — reconciliação pelo resolver**
> WHEN a remote event competes with local state for the same content_hash, THE apply SHALL use the Phase 2 resolver to pick the winner and materialize only if the remote wins; a late event (lower HLC) SHALL be recorded but SHALL NOT overwrite the materialized winner.

**F5 — materialização + embedding_pending**
> WHEN a winning create/update is materialized, THE apply SHALL write directly to local SQLite; IF the event's embedding model differs or content is absent, THE memory SHALL be marked `embedding_pending=1` (Fase 3). A winning delete SHALL soft-delete (tombstone, §8.1c).

**F6 — cursor por-peer**
> WHEN a batch is applied successfully, THE apply SHALL advance `sync_cursor[peer_id].last_seq_seen` to the batch's `next_seq` in the SAME transaction; a crash mid-batch SHALL re-pull from the last durable cursor (§8.5).

**F7 — autoria preservada**
> WHILE applying, THE apply SHALL NOT re-stamp `agent_id` with the local identity; replayed events keep original authorship (§8.4).

## Requisitos não-funcionais
- **NF1** migração `018_add_sync_cursor.sql`: CREATE TABLE sync_cursor (peer_id PK, last_seq_seen, last_hlc_*, updated_at). Aditiva, idempotente, `.down.sql` documental.
- **NF2** o apply materializa via SQLite direto, NÃO via POST /api/memories (contorna limitação de timestamp do store remoto).
- **NF3** sync-sites continuam vendo pending (Fase 3); o feed expõe TODOS os eventos (inclusive de memórias pending — reconciliação precisa).
- **NF4** modo de teste LOCAL (2 storages, sem rede): feed de A aplicado em B via apply.

## Critérios de aceite (= fixtures §8.4/§8.5, viram testes RED no Gate 2)
- [ ] **CA1 (F1)** endpoint retorna eventos > since_seq, ordenados, create enriquecido com content, next_seq/has_more corretos; require_read_access.
- [ ] **CA2 (F3 idempotência)** aplicar o mesmo feed 2× → estado idêntico, zero duplicata (UNIQUE agent_id,event_id).
- [ ] **CA3 (F4 resolver/late)** evento remoto com HLC maior vence e materializa; evento late (HLC menor) é registrado mas não sobrescreve.
- [ ] **CA4 (F6 cursor)** após aplicar lote, sync_cursor[peer].last_seq_seen = next_seq; re-pull do mesmo cursor é no-op; cursor não regride.
- [ ] **CA5 (F7 autoria §8.4)** evento de agent A aplicado em B (agent B) → o evento em B.sync_events mantém agent_id=A (não vira B).
- [ ] **CA6 (F5 materialização)** create vencedor → memória materializada e pesquisável (se modelo bate); delete vencedor → soft-delete; modelo diferente → embedding_pending=1.
- [ ] **CA7 (NF1)** migração 018 cria sync_cursor; idempotente.

## E2E a quente (modo local, 2 storages)
1. Storage A (agent=alpha): store 3 memórias distintas → eventos em A.sync_events.
2. Simular feed: ler A.sync_events por seq (enriquecido) → apply_remote_event em B (agent=beta).
3. Confirmar: B tem as 3 memórias materializadas e pesquisáveis; eventos em B mantêm agent_id=alpha; sync_cursor[A] avançou; re-aplicar = no-op (idempotente).
4. Late event: injetar evento HLC menor sobre hash existente em B → não sobrescreve.

## Gate (G0-G5) — delegação
- G0/G1 feito (Gate 1 seven APROVADO + ADRs + SPEC).
- G2 RED: rok (CA1-CA7; modo local sem rede; anti-skip; cuidado com tipo de retorno real).
- G3 impl: reg — migração 018 + endpoint sync_events.py + remote_http.get_events_since + storage/sync/apply.py (reusa resolver) + cursor.
- G4 verify: suite + reindexar. G5 review: tuvok (idempotência, resolver no apply, cursor atômico, autoria §8.4, mutation).
- E2E a quente (modo local) após G5. (E2E contra VPS real = Fase 4b quando houver push, OU teste pull do hub já populado.)
