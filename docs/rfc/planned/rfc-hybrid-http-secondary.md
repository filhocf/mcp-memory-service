# RFC: hybrid self-hosted secondary (http) — pluggable sync secondary

**Data:** 2026-10-06
**Autor:** Claudio + Zero (Kiro CLI)
**Base:** `upstream/main` v11.15.0+
**Issue:** GitHub **#1304** (atribuída a filhocf pelo Henry, 27/set, `help wanted`)
**Versão:** 0.1 (draft — guarda-chuva + Fase 1 detalhada)
**Status:** DRAFT — em implementação faseada (G0-G5 + E2E quente por fase)
**Desbloqueia:** `rfc-delta-sync` (#1345, event-log multi-writer, com @ducanhnguyen223) — cujo §9.5 trava o 1º PR "só depois do #1304 integrado".
**Relacionado:** #1100 (agent_id, base de escopo por agente), rfc-delta-sync (#1345).

## 1. Problema

O backend `hybrid` é local-first (SQLite-vec) + um secondary sincronizado em background,
mas o secondary **só pode ser Cloudflare** — está hardwired, não é configurável:
- `storage/hybrid.py` importa `CloudflareStorage` no topo e tipa `BackgroundSyncService`
  contra ele; `_fetch_secondary_content_hashes()` fala direto com D1.
- `factory.py` só monta `cloudflare_config`; `SUPPORTED_BACKENDS` (`config/base.py:356`)
  não tem knob de secondary.

Quem quer largar o Cloudflare fica entre local-only (sem sync) e thin-client (sem cache
local, sem offline). **Rodamos exatamente a topologia-alvo em produção** (3 clientes +
hub VPS self-hosted) por fora, com um sidecar que faz drift detection paginando a REST
API — e o sidecar derrapa (clientes pararam de convergir ~10 dias silenciosamente por
falta do endpoint bulk de hashes).

## 2. Objetivo

Tornar o secondary do `hybrid` plugável: `cloudflare` (default, nada muda) ou `http`
(uma instância self-hosted como hub). Terminal-only (sem two-hop — decidido com o Henry).

**Não-objetivos:** two-hop (hub sincronizando adiante); event-log multi-writer (é o
#1345, que depende desta); novos backends além de `http`.

## 3. Fases (1 PR cada)

| Fase | Entrega | Depende de |
|------|---------|-----------|
| **1** | `list_content_hashes()` na base + endpoint REST bulk | — |
| **2** | `storage/remote_http.py` + `MCP_HYBRID_SECONDARY_BACKEND` | 1 |
| **3** | desacoplar `BackgroundSyncService` do Cloudflare (capability-gate) | 2 |
| **4** | model-match startup check + campo de modelo em status autenticado | 2 |

---

## 4. Fase 1 — `list_content_hashes()` + bulk hash endpoint

### 4.1 Achados (codebase, verificado 06/out)
- `RetrieveMixin.get_all_content_hashes(include_deleted=False) -> Set[str]`
  (`mixins/retrieve.py:525`) JÁ existe no sqlite-vec: filtra `deleted_at IS NULL`,
  retorna set. 1 caller (`hybrid.py:1121`). **Mas não está na base class** → não é
  polimórfico; `CloudflareStorage` não tem equivalente público (usa o D1 special-case).
- A REST API (`web/api/memories.py`) tem POST/GET/DELETE/PUT de memória, **nenhum
  endpoint bulk de hashes**. Paginar `GET /memories` para drift não escala (o Henry).
- O D1 special-case (`hybrid.py:_fetch_secondary_content_hashes`) já faz paginação por
  cursor id-based (D1 falha com OFFSET grande) — o endpoint REST deve seguir o mesmo padrão.

### 4.2 Requisitos (Prosa + EARS)

**R1**: A base `MemoryStorage` declara o contrato de listagem de hashes.

> EARS: THE `MemoryStorage` base class SHALL define `list_content_hashes(include_deleted: bool = False) -> Set[str]`, returning every live memory's `content_hash` (excluding soft-deleted tombstones unless `include_deleted`).

**R2**: O backend sqlite-vec satisfaz o contrato reusando a lógica existente.

> EARS: WHEN `list_content_hashes` is called on the sqlite-vec backend, THE backend SHALL return the same set as the existing `get_all_content_hashes`, honoring the `deleted_at IS NULL` filter.

**R3**: O hub expõe um endpoint REST de listagem bulk de hashes, paginado.

> EARS: THE REST API SHALL expose `GET /api/memories/hashes` that returns content hashes in cursor-paginated pages (id-based cursor, not OFFSET), excluding soft-deleted tombstones by default.

**R4**: O endpoint é autenticado como as demais rotas de leitura.

> EARS: WHERE API-key auth is configured, THE `/api/memories/hashes` endpoint SHALL require read access, mirroring the other `/memories` read routes.

**R5**: A paginação é estável e completa.

> EARS: WHEN a client walks the cursor to exhaustion, THE endpoint SHALL return every live hash exactly once, with no dependence on OFFSET.

### 4.3 Design (cirúrgico)
- `storage/base.py`: declarar `list_content_hashes` (abstrato ou default que levanta
  `NotImplementedError`), documentando o contrato.
- `mixins/retrieve.py`: `list_content_hashes` como alias/wrapper fino sobre a lógica de
  `get_all_content_hashes` (ou renomear + manter alias para não quebrar o caller atual).
- `web/api/memories.py`: `GET /memories/hashes` com cursor id-based (reusar o padrão de
  `cloudflare.py:get_all_memories_cursor`), `require_read_access`.
- **Doc-sync (oficial):** `docs/mastery/api-reference.md` (novo endpoint).

### 4.4 Critérios de aceite
- [ ] `MemoryStorage.list_content_hashes` existe no contrato base.
- [ ] sqlite-vec retorna o set correto (filtra tombstones; `include_deleted` funciona).
- [ ] `GET /memories/hashes` pagina por cursor, autenticado, retorna todos os hashes vivos 1×.
- [ ] Teste RED por requisito (G3) + E2E quente contra a topologia viva (drift convergence).
- [ ] Número coletado: tempo/consistência de drift com o endpoint vs paginando `/memories`.
- [ ] `api-reference.md` atualizado no mesmo PR.

## 5. Fases 2-4 (resumo — detalhar quando desbloqueadas)

- **Fase 2:** `remote_http.py` (`MemoryStorage` via REST da outra instância) + config
  `MCP_HYBRID_SECONDARY_BACKEND=cloudflare|http` + URL/API key. Doc: configuration-guide, README, SUPPORTED_BACKENDS.
- **Fase 3:** typar `BackgroundSyncService` contra `MemoryStorage`, substituir
  `_fetch_secondary_content_hashes` D1-case por `list_content_hashes`, capability-gate dos
  trechos CF-only (Vectorize/normalização/10KB). Doc: architecture-overview, cloudflare-setup.
- **Fase 4:** `http` recusa iniciar se modelo do hub ≠ local (ou ausente); campo de modelo
  em status autenticado dedicado (não o `hasattr` de `/health/detailed` que falha open). Doc: configuration-guide, troubleshooting.

## 6. Fora de escopo
- Two-hop; event-log (#1345); backends além de http; criptografia (herda do delta-sync).
