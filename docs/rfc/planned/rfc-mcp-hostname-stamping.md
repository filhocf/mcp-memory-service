# RFC: hostname automático no store MCP (server-side host stamping)

**Data:** 2026-10-06
**Autor:** Claudio + Zero (Kiro CLI)
**Base:** `upstream/main` v11.15.0+ (camada nossa, fork)
**Versão:** 0.1
**Status:** IMPLEMENTED (fork) 6/out — gate G0-G5 + E2E quente + store_session coberto (G5 P2). Candidata a PR upstream.
**Vizinhas:** `rfc-agent-id-multi-agent` (autoria = QUEM; host = ONDE — ortogonais e complementares), `rfc-delta-sync` (host é o writer_id natural do multi-writer mesh), `rfc-harvest-source-identity` (identidade na COLHEITA; esta é identidade no STORE DIRETO).

## 1. Problema

Numa instalação multi-máquina (Zero roda em DNBSCDC289, sirdata, socrates; cada
`memory-service` roda num host e só nele), a memória gravada não registra **de
qual máquina** veio. Hoje:

- `agent_id` responde QUEM escreveu (Zero) — recém-ligado no store e na telemetria.
- **Nenhum campo responde ONDE** (qual host) de forma automática no caminho MCP.

Evidência (código real, 6/out, verificado via grafo + grep):
- `INCLUDE_HOSTNAME` (`MCP_MEMORY_INCLUDE_HOSTNAME`) é lido **só** em `web/api/memories.py:151` — **apenas a Web API** carimba host (via header `X-Client-Hostname` ou `socket.gethostname()`).
- O caminho **MCP** (`server/handlers/memory.py:199`) lê `client_hostname` **só do argumento do cliente**; o Kiro não passa esse argumento, e o handler **não consulta `INCLUDE_HOSTNAME` nem resolve `socket.gethostname()`**.
- `MemoryService.store_memory` (`services/memory_service.py:426-431`) JÁ grava `metadata["hostname"]` + tag `source:{host}` SE `client_hostname` chegar — a plumbing de persistência existe; falta a RESOLUÇÃO no caminho MCP.

Consequência: ligar `MCP_MEMORY_INCLUDE_HOSTNAME=true` sozinho NÃO carimba host nas
memórias que o Kiro grava (MCP). A env é inócua para o nosso fluxo.

Dado atual do banco vivo: só ~1.800 de 24k memórias têm host (via tags
inconsistentes), 10 têm `metadata.hostname`.

## 2. Objetivo

Quando `MCP_MEMORY_INCLUDE_HOSTNAME` está ligado, o host é o **fato do processo**
(o serviço roda numa máquina) e deve ser carimbado automaticamente em toda
memória gravada via MCP, sem o cliente precisar passar nada — espelhando o que a
Web API já faz. Fonte: `socket.gethostname()`. Backward-compatible (opt-in, default off).

**Não-objetivos:** backfill retroativo do host no legado (o host de origem das 22k
memórias antigas é incerto — fica para o delta-sync, que define writer_id); mudar
schema; alterar a Web API (já funciona).

## 3. Requisitos (Prosa + EARS)

**R1**: O caminho MCP resolve o host do servidor quando o cliente não o fornece e a flag está ligada.

> EARS: WHEN a memory is stored via the MCP `store_memory` handler AND no `client_hostname` argument is given AND `MCP_MEMORY_INCLUDE_HOSTNAME` is enabled, THE handler SHALL resolve the hostname from `socket.gethostname()`.

**R2**: O host explícito do cliente tem precedência sobre o do servidor.

> EARS: WHERE a `client_hostname` argument is provided, THE handler SHALL use it unchanged (server resolution SHALL NOT override an explicit client value).

**R3**: Com a flag desligada, o comportamento é inalterado.

> EARS: WHERE `MCP_MEMORY_INCLUDE_HOSTNAME` is disabled, THE MCP handler SHALL NOT add any hostname (unchanged from current behavior).

**R4**: O host resolvido é persistido como os demais (metadata + tag source).

> EARS: WHEN a hostname is resolved (client or server), THE store path SHALL persist it in `metadata.hostname` and as a `source:{hostname}` tag (the existing MemoryService behavior).

**R5**: A resolução é best-effort e nunca quebra o store.

> EARS: IF `socket.gethostname()` raises, THE handler SHALL log a warning and store the memory without hostname (never fail the write).

## 4. Design (cirúrgico)

- `server/handlers/memory.py` (`handle_store` ~L199): após `client_hostname = arguments.get("client_hostname")`, adicionar fallback:
  ```python
  if not client_hostname and INCLUDE_HOSTNAME:
      try:
          client_hostname = socket.gethostname()
      except Exception as e:
          logger.warning("hostname resolve failed (non-fatal): %s", e)
  ```
  Espelha `web/api/memories.py:158-161`. Import de `INCLUDE_HOSTNAME` do config e `socket`.
- Nenhuma mudança em `MemoryService.store_memory` (já grava quando `client_hostname` chega).
- Os outros call sites MCP (L456, L479 — ingest/batch) recebem o mesmo tratamento se gravam memória do operador.

## 5. Fora de escopo

- Backfill do legado (delta-sync define o writer_id retroativo).
- Web API (já implementada).
- Normalização de hostname (ex. tirar `.741` do `DNBSCDC289.741`) — decisão separada; por ora grava cru.

## 6. Critérios de aceite

- [ ] `MCP_MEMORY_INCLUDE_HOSTNAME=true` + store via MCP sem client_hostname → `metadata.hostname = socket.gethostname()` + tag `source:{host}`.
- [ ] client_hostname explícito → vence o do servidor.
- [ ] flag off → sem hostname (comportamento atual).
- [ ] gethostname falhando → store OK sem host (best-effort).
- [ ] E2E quente: memória real gravada no serviço vivo carimba o host da máquina.
- [ ] Teste RED por requisito (G3).

## 7. Ganho

- **Debug multi-máquina:** "esse checkpoint foi no sirdata ou aqui?" vira resposta, não adivinhação.
- **Delta-sync (ADR-0002):** host é o `writer_id` natural do multi-writer mesh — pré-requisito de reconciliação por origem.
- **Ortogonal ao L4:** host NÃO entra no sinal de reaccess/retry (isso é agent_id); é enriquecimento puro, zero risco ao learning-loop.

## 8. Candidato a PR upstream

SIM — é melhoria genérica (não fork-specific): "MCP store path honors INCLUDE_HOSTNAME like the Web API does". Fecha uma assimetria real do upstream (a flag existe mas só a Web API a respeita). PR pequeno, auto-contido, com teste. Recortar de `upstream/main` limpo no worktree `-dev` após gate completo.
