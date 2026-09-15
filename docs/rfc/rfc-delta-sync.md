# RFC: Delta Event-Log Sync (malha de memória multi-agente)

**Data:** 2026-09-13
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `feat/delta-sync` (a partir de `upstream/main`)
**Base:** `upstream/main` v11.11.0
**Versão:** 0.1 (draft)
**Inspiração:** Mnemosyne `sync.py` / `sync_server.py` (delta event-log + cripto client-side)
**Reintegra:** dor de sync via Insync (tasks internas 5d41dda2 stale-reads, corrupção SQLite+WAL)
**Status:** DRAFT — amadurecer localmente antes de virar issue/RFC para o Henry

---

## 1. Problema

O sync de memória entre máquinas e agentes (Zero em 3 máquinas; T'Pol/Scotty na VPS) é feito hoje por **file-sync do `.db` inteiro** via Insync/OneDrive + hot-backup com score composto. Isso transfere o arquivo todo, corre risco de corrupção e não modela "memória por agente".

### Evidências

- Banco de 457 MB sincronizado inteiro a cada operação (Insync) — custo escala com o tamanho.
- Corrupção documentada: "Insync + SQLite = corrupção — WAL ativo durante sync" (lessons learned).
- Stale reads: task interna 5d41dda2 — o processo mantém conexão aberta e não vê o `.db` atualizado por outra máquina.
- Modelo atual não é "memória por agente": é um banco copiado, não uma troca deliberada entre agentes (Zero não "sabe o que T'Pol fez" de forma seletiva — ou copia tudo, ou nada).

### Causas

1. **Sync de arquivo, não de deltas.** Transfere o `.db` inteiro; não há protocolo de mudanças incrementais.
2. **Sem event-log.** Não há registro append-only de operações que permita reconciliação e auditoria.
3. **Sem fronteira por agente.** Não há noção de "o que este agente compartilha" vs "o que é privado".

### Risco / motivação estratégica

Corrupção e stale reads são problemas ativos. E o modelo de arquivo impede a visão de **malha de memória da tripulação**: cada agente com sua memória, compartilhando seletivamente o que faz sentido (Zero vê a pesquisa da T'Pol e a implementação do Scotty).

---

## 2. Objetivo

Substituir o file-sync por um **sync delta baseado em event-log**, bidirecional, com reconciliação por timeline+importância, opcionalmente com criptografia client-side, modelando compartilhamento **por agente**.

**Não-objetivos:** forçar criptografia (opcional); remover o hot-backup (permanece como rede de segurança); federar retrieval entre stores (RFC #57 upstream separada).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1).

### Funcional

**R1**: O sync transfere apenas mudanças desde o último sync.

> EARS: WHEN a sync runs, THE sync client SHALL transfer only the events changed since the last successful sync.

**R2**: As operações são registradas em log append-only auditável.

> EARS: WHEN a memory is created, updated or deleted, THE system SHALL append an event to an immutable event log with id, timestamp and operation type.

**R3**: O sync é bidirecional com reconciliação determinística.

> EARS: WHEN two instances have divergent events, THE sync SHALL reconcile them by timeline and importance, deterministically.

**R4**: O sync não corrompe o banco durante operação.

> EARS: WHILE syncing, THE sync SHALL operate over the event log and never copy the raw `.db` file with an active WAL.

**R5**: O conteúdo pode ser criptografado no cliente (opcional).

> EARS: WHERE client-side encryption is enabled, THE sync SHALL encrypt payload before transmission so the server sees only metadata.

**R6**: O compartilhamento é escopado por agente.

> EARS: WHEN an agent marks memories as shareable, THE sync SHALL propagate only those to peers, keeping the rest private.

### Não-Funcional

**R7**: O sync é resiliente a stale reads.

> EARS: WHEN the local `.db` changes on disk, THE service SHALL detect the change (e.g. `PRAGMA data_version`) and avoid serving stale data.

**R8**: O hot-backup permanece como rede de segurança.

> EARS: THE delta sync SHALL coexist with the existing hot-backup rather than replace it during transition.

---

## 4. Design

- `sync.py`: event-log append-only (id, ts, op, payload, agent_id) + cliente delta bidirecional.
- `sync_server.py`: servidor HTTP (na VPS) com auth (API key/JWT); vê só metadata quando cripto ativa.
- Cripto opcional: Fernet/PyNaCl, chave client-side (nunca sai da máquina).
- Escopo por agente: flag `shareable` + `agent_id` na memória; reconciliação timeline+importância.
- Detecção de stale: `PRAGMA data_version` no serviço para reconectar/recarregar.
- Coexistência: manter Insync/hot-backup durante transição; migrar quando o delta sync provar estabilidade.

---

## 5. Fora de Escopo

- Federated retrieval cross-store (RFC #57 upstream).
- Remoção imediata do Insync (coexistência na transição).
- Criptografia obrigatória (opcional; rede LAN + OneDrive já é privada para nós).

---

## 6. Critérios de Aceite

- [ ] Sync transfere só deltas desde o último sync (não o `.db` inteiro).
- [ ] Event-log append-only auditável (id/ts/op/agent).
- [ ] Reconciliação bidirecional determinística por timeline+importância.
- [ ] Sync não copia `.db` com WAL ativo (sem corrupção).
- [ ] Compartilhamento escopado por agente (shareable vs privado).
- [ ] Serviço detecta mudança em disco e não serve dado stale.
- [ ] Coexiste com hot-backup na transição.
