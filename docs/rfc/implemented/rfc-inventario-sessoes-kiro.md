# Inventário Completo de Sessões Kiro + Estratégia de Resgate Total (sem perda)

**Data:** 2026-09-28 · **Host:** DNBSCDC289 · **Autor:** Claudio + Zero
**Objetivo:** resgatar TODAS as sessões Kiro deste host (incluindo backups fora do radar) para a memória, sem perder nada. Estado da arte via kiro.dev + web + varredura de disco.

---

## 1. Como o Kiro guarda sessões (oficial, kiro.dev)

- **CLI (v3): fonte de verdade = SQLite em `~/.kiro/` (na prática `~/.local/share/kiro-cli/data.sqlite3`).** Auto-save a cada turn, por diretório, session ID = UUID. Os `.jsonl` em `~/.kiro/sessions/cli/` são **export/espelho**, não a fonte primária.
- **Migração v2→v3:** "Session data format has changed and existing sessions are NOT automatically migrated." Backup recomendado `cp -r ~/.kiro/sessions ~/.kiro/sessions-v2-backup`. Aviso oficial: **"Complex sessions with extensive tool result history may lose some historical tool outputs — the conversation flow and decisions are preserved."**
- **Search do dashboard V3:** indexa prompts + respostas; **tool output NÃO é indexado** (nem transcripts de sessão clássica/cloud). É o mesmo gap da RFC #1346 (harvest-design-extraction).
- **Cloud sessions:** store separado na conta (resume de qualquer máquina). Não é local.
- **IDE:** sessões em `~/.config/Kiro/User/globalStorage/kiro.kiroagent/` (formato próprio `history[]`).

## 2. Inventário total deste host (5 acervos)

| # | Acervo | Local | Volume | Formato | Harvest colhe? |
|---|--------|-------|--------|---------|----------------|
| 1 | **CLI SQLite (fonte viva)** | `~/.local/share/kiro-cli/data.sqlite3` | 114 MB | `conversations_v2`=195 (v3), `conversations`=0 (v2), `history`=1008 | ❌ parser lê jsonl, não SQLite |
| 2 | **CLI jsonl (espelho)** | `~/.kiro/sessions/cli/` | 1003 arquivos | Kiro legacy `{kind:Prompt, data, version}` | ✅ sim (rotineiro, scheduler 6h aponta aqui) |
| 3 | **IDE sessions** | `~/.config/Kiro/.../kiro.kiroagent/sessions + workspace-sessions` | 554 reais (+522 marcadores `._migration-`), ~50 MB | `.json` único `{history[], title, sessionId, workspacePath}` | ❌ **NÃO lê** (não é jsonl; conteúdo em history[]) |
| 4 | **Backup fora do radar** | `~/local-data/kiro-sessions-backup/` | 1.5 GB / 2039 jsonl | v4 **payload-wrapped** `{id,timestamp,payload}` | ✅ **sim, fix v4 de hoje** (na main do fork) |
| 5 | **Safe-copy (hoje)** | `~/local-data/kiro-sessions-SAFE-COPY-20260928/` | 2.5 GB, read-only | cópia de 2+4 | (proteção, não colher daqui) |

NÃO são sessão: `kiro-cli/kas` (4 GB, cache de binários), `kiro-cli/run` (1.4 GB), `.config/Kiro` workspaceStorage (cache IDE).

## 2.5. Metadados de IDENTIDADE por encarnação (achado 30/set — verificado ao vivo)

**Correção ao §1:** o "IDE `history[]` em `~/.config/Kiro/.../kiro.kiroagent/`" **migrou** (confirmado 29-30/set). As sessões de IDE hoje vivem no **workspace layout** `~/.kiro/sessions/{workspace_hash}/{sess_uuid}/messages.jsonl` (v4 payload-wrapped, o mesmo que o #1366 lê). Não há mais um formato `history[]` separado a parsear neste host.

**Cada encarnação já expõe metadado de identidade — só não estávamos lendo.** Isto é a base da RFC `rfc-harvest-source-identity.md` (fork, v0.1, 30/set):

| Encarnação | Sessão (conteúdo) | Metadado lateral | Sinais de identidade |
|---|---|---|---|
| **CLI** | `cli/{uuid}.jsonl` | `cli/{uuid}.json` irmão (+ `.history`, `.lock`) | **`agent_id.name`** (ex. `kiro_default`), **`session_created_reason`** (ex. `subagent`), `cwd`, `title` |
| **IDE / workspace** | `{hash}/{sess_uuid}/messages.jsonl` | `session.json` (por sessão) + `.index/index.json` (por workspace) | `agentMode` (ex. `vibe`), **`workspacePaths`**, `rootPaths`, `title`, `schemaVersion` |
| **Crew** | `data.sqlite3` → `conversations_v2.value` (JSON) | embutido no `value` | `conversation_id`, `cwd` (via `file_line_tracker`) |

**Decisivo:** o CLI já carimba `agent_id.name` + `session_created_reason` (distingue agente principal de subagente) no `{uuid}.json`. A distinção CLI vs IDE vs Crew é estrutural + metadado (flat+`{uuid}.json` / nested+`session.json` / SQLite `conversations_v2`), sem heurística frágil. Responde "qual Zero produziu esta sessão?" — o lado de ENTRADA do `agent_id` (#1100/#1278/#1297). Session_id estável para workspace: `{workspace_hash}/{session_dir}` (fix #1376).

## 3. Gaps de colheita reais (o que ainda se perde)

- **Gap A — IDE (554 sessões):** formato `history[]` json nunca colhido. Precisa OU parser IDE OU migração `history[]`→jsonl (task 8705149e já mapeou 418 dessas). ~50 MB de conversa não indexada.
- **Gap B — tool outputs ricos:** `thinking`, `toolUse`, `ToolResults` são `dropped` em TODOS os formatos (medido no coverage). É o gap da RFC #1346 — o dado analítico que embasou decisões se perde. Confirmado pela própria doc oficial ("tool output not indexed").
- **Gap C — SQLite conv_v2 (195):** o espelho jsonl em `cli/` cobre esses 195? Ou há sessões só no SQLite (nunca exportadas)? A confirmar: cruzar UUIDs do SQLite com os nomes de arquivo em `cli/`.

## 4. Estratégia de resgate total (sem perda) — ordem

**Pré (feito hoje):** cópia read-only de segurança (safe-copy 2.5GB) + fix parser v4 na main do fork + serviço reiniciado.

1. **Confirmar Gap C:** cruzar os 195 `conversations_v2.session_id` (SQLite) com os arquivos `cli/*.jsonl`. Se cobertos → espelho basta. Se não → extrair do SQLite (é a fonte viva).
2. **Redação de secrets na ingestão (BLOQUEANTE):** antes de qualquer run em massa. 2 secrets reais já vazaram via sessão→banco hoje. Sem isso, o resgate re-vaza em escala.
3. **Colher acervo v4 (backup 2039):** apontar run de harvest para `~/local-data/kiro-sessions-backup/` (+ sub-executions). Parser v4 já reconhece. SEM `force_reharvest` global (dedup semântico + tracker protegem contra duplicar o que já foi colhido).
4. **Resolver Gap A (IDE 554):** decidir entre (a) escrever parser IDE `history[]` no TranscriptParser, ou (b) migrar `history[]`→jsonl e colher. Opção (a) é mais limpa (mais um formato aditivo, como o v4). Vira PR upstream (mesmo padrão do #1366).
5. **Resolver Gap B (tool outputs):** é a RFC #1346 (design-extractor). Depois do parser reconhecer tudo, medir cobertura real (instrumento #1350) e decidir extractor.
6. **Auditar amostra** (secrets? dup? sinal?) → só então ampliar. Consolidação final via serviço.

## 5. Riscos

- **R1:** run em massa sem redação → re-vazamento de secrets em escala. Bloqueia (item 2 antes de 3).
- **R2:** `force_reharvest` global → duplicação contra as ~22k memórias existentes. Nunca global.
- **R3:** mexer no SQLite vivo (`data.sqlite3`) do CLI enquanto o Kiro roda → corrupção. Ler via cópia/`VACUUM INTO`, nunca direto no arquivo vivo.
- **R4:** IDE `history[]` pode ter estrutura variável (v0/v1) — validar antes de assumir 1 formato.

## 6. Estado dos fixes (hoje)

- Parser v4 (payload-wrapped) → na main do fork (`b5ae2a10`), serviço rodando. PR #1366 (upstream, verde).
- Health lock + P2 → main do fork. PR #1365 (upstream, verde).
- Doc irmão: `RECUPERACAO-SESSOES-KIRO-plano.md` (degraus 1-6 do fix parser).
