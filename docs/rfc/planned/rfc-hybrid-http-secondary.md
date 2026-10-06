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

---

## 6. Fase 2 — `remote_http.py` + secondary-backend config

### 6.1 Achados (codebase)
- `MemoryStorage` (base) tem ~47 métodos, mas o secondary de sync usa um subconjunto:
  store, get_by_hash, delete, update_memory_metadata, `list_content_hashes[_page]` (Fase 1).
  O Henry: "store/get-by-hash/delete/metadata já cobertos por `web/api/memories.py`".
- `factory.py:159-181` só monta `cloudflare_config`; `SUPPORTED_BACKENDS` (`config/base.py:356`)
  não tem knob de secondary.

### 6.2 Requisitos (EARS)
**R6**: Existe um backend de storage que fala com a REST API de outra instância.

> EARS: THE system SHALL provide a `RemoteHTTPStorage(MemoryStorage)` that implements store, get-by-hash, delete, metadata update and `list_content_hashes[_page]` by calling another instance's REST API (`/api/memories*`, `/api/memories/hashes`).

**R7**: O secondary do hybrid é configurável, com Cloudflare como default.

> EARS: WHEN `MCP_HYBRID_SECONDARY_BACKEND` is `http`, THE factory SHALL assemble the hybrid secondary as a `RemoteHTTPStorage` from `MCP_HYBRID_SECONDARY_URL` + API key; WHERE the var is unset or `cloudflare`, THE factory SHALL keep the current Cloudflare secondary unchanged.

**R8**: Métodos não suportados pelo remote falham explícito, não silencioso.

> EARS: WHERE a `MemoryStorage` method is not serviceable over the REST surface, THE `RemoteHTTPStorage` SHALL raise `NotImplementedError` rather than return an empty/plausible result.

**R9**: Credenciais e URL nunca são logadas em claro.

> EARS: THE `RemoteHTTPStorage` SHALL redact the API key and host from logs (reuse `_sanitize_log_value`).

### 6.3 Design
- `storage/remote_http.py`: `httpx` client; mapeia os métodos do subconjunto para as rotas REST;
  reusa `/api/memories/hashes` (Fase 1) para `list_content_hashes_page`.
- `config/base.py`: `MCP_HYBRID_SECONDARY_BACKEND`, `MCP_HYBRID_SECONDARY_URL`, API key.
- `factory.py`: ramo `http` monta o `RemoteHTTPStorage`.
- Doc: `configuration-guide.md`, `README.md`, `SUPPORTED_BACKENDS`.

### 6.4 Aceite
- [ ] `RemoteHTTPStorage` implementa o subconjunto + list_content_hashes_page via HTTP.
- [ ] factory monta http quando a env pede; default cloudflare intocado.
- [ ] método não suportado → NotImplementedError (teste).
- [ ] E2E quente: cliente local sincroniza contra um hub http real (nossa topologia).

---

## 7. Fase 3 — desacoplar `BackgroundSyncService` do Cloudflare

### 7.1 Achados (codebase)
- `BackgroundSyncService` (hybrid.py:190-964) é tipado contra `CloudflareStorage`;
  `_fetch_secondary_content_hashes` (145-187) fala direto com D1.
- 135 menções a Cloudflare em `hybrid.py` (acoplamento forte).
- `HybridMemoryStorage` (967-2142), 30 callers — mas via interface pública (seguro).

### 7.2 Requisitos (EARS)
**R10**: O serviço de sync opera sobre a interface, não um backend concreto.

> EARS: THE `BackgroundSyncService` SHALL be typed against `MemoryStorage`, not `CloudflareStorage`, and SHALL drive sync through interface methods.

**R11**: A detecção de drift usa o contrato polimórfico.

> EARS: WHEN detecting drift, THE service SHALL call `secondary.list_content_hashes[_page]()` instead of the Cloudflare D1 special-case.

**R12**: Os trechos específicos de Cloudflare ficam atrás de capability-gate.

> EARS: WHERE a Cloudflare-only concern applies (Vectorize capacity, metadata normalization, the 10 KB metadata limit), THE service SHALL gate it behind a capability check, not run it unconditionally.

**R13**: Comportamento com secondary Cloudflare é inalterado.

> EARS: WHEN the secondary is Cloudflare, THE sync behavior SHALL be identical to today (regression suite green).

### 7.3 Design
- Typar `BackgroundSyncService.__init__` contra `MemoryStorage`.
- Substituir `_fetch_secondary_content_hashes` por `secondary.list_content_hashes_page()`.
- Capability-gate: `getattr(secondary, 'is_cloudflare', False)` ou um método de capacidade
  (`supports_vectorize_capacity()` etc.) — decidir no arch.
- Doc: `architecture-overview.md` (hoje diz "background Cloudflare sync — recommended"),
  `cloudflare-setup.md`.

### 7.4 Aceite
- [ ] sync funciona com secondary http (nossa topologia, E2E quente).
- [ ] sync com Cloudflare inalterado (regressão verde).
- [ ] nenhum caminho CF-only roda quando o secondary é http.

---

## 8. Fase 4 — model-match startup check

### 8.1 Achados (codebase)
- `/health/detailed` (web/api/health.py:167) tem `embedding_model` MAS atrás de
  `if hasattr(storage, 'embedding_model_name')` — sqlite-vec não expõe → **falha open**
  (campo ausente lido como "sem info"). O Henry: um check que trata "sem info" como
  "match" é pior que não ter check.

### 8.2 Requisitos (EARS)
**R14**: O hub expõe o modelo de embedding configurado como dado, autenticado.

> EARS: THE REST API SHALL expose the configured embedding model as an explicit field on an authenticated status response (not the fail-open `hasattr` path on `/health/detailed`).

**R15**: O secondary http recusa iniciar em mismatch de modelo.

> EARS: WHEN `MCP_HYBRID_SECONDARY_BACKEND=http` AND the hub's embedding model differs from the local one, THE service SHALL refuse to start and SHALL name both disagreeing values.

**R16**: Ausência de info de modelo também bloqueia (fail-closed).

> EARS: WHERE the hub does not report its embedding model, THE startup check SHALL refuse to start (treat absent model info as a failure, never as a match).

### 8.3 Design
- Campo dedicado de modelo numa resposta autenticada (não sobrecarregar `/health`).
- Startup check no caminho `http` secondary: busca o modelo do hub, compara, aborta em
  mismatch OU ausência, com mensagem clara (os dois valores).
- Doc: `configuration-guide.md` (a env + o check), `troubleshooting.md` (mudança
  intencional de modelo exige **re-embed do hub**, não só restart — o check previne nova
  divergência, não cura vetores já escritos).

### 8.4 Aceite
- [ ] endpoint autenticado retorna o modelo configurado (campo explícito).
- [ ] http secondary aborta em mismatch, nomeando os dois valores (teste).
- [ ] http secondary aborta em modelo ausente (fail-closed, teste).
- [ ] doc do re-embed no troubleshooting.

## 9. Fora de escopo
- Two-hop; event-log (#1345); backends além de http; criptografia (herda do delta-sync).
