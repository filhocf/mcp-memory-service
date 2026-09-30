# Recuperação de Sessões Kiro — Estado da Arte + Plano de Colheita Sem Perda

**Data:** 2026-09-28 · **Host:** DNBSCDC289 · **Autor:** Claudio + Zero
**Contexto:** ~2.5GB de sessões Kiro (backup que "estava sendo apagado" + ativas) NÃO estão sendo colhidas pelo harvest — o parser de produção não reconhece o formato atual. Recuperar sem perda.
**Método:** investigação CdIA + código + web (estado da arte) + Gate 0 (arch-analyst). NÃO executar colheita antes do fix validado.

## ⏱️ EXECUÇÃO (28/set — degraus 1-6 feitos)
- ✅ **1. Cópia read-only** `~/local-data/kiro-sessions-SAFE-COPY-20260928` (2.5GB/3071, chmod a-w).
- ✅ **2. Sync + duplicata:** nenhum PR upstream sobre payload-wrapped.
- ✅ **3-5. Fix parser** via TDD (dev-tests→dev-python→reviewer APROVADO). Antes 0 msgs → agora 854 (5 maiores sessões); coverage user/assistant/tool_result extraídos, resto seen+dropped. 8 testes + 315 regressão verdes.
- ✅ **6. PR #1366** aberto (https://github.com/doobidoo/mcp-memory-service/pull/1366), MERGEABLE, CI verde.
- ⏳ **7-10 PENDENTES:** redação de secrets (BLOQUEANTE), run paginado, auditoria, consolidação. Aguardam merge #1366 + decisão sobre redação.

---

## 1. Acervo neste host (medido 28/set)

| Acervo | Local | Volume | Arquivos | Formato |
|--------|-------|--------|----------|---------|
| Backup "que apagava" | `~/local-data/kiro-sessions-backup/` | 1.5 GB | 2039 .jsonl | payload-wrapped |
| Sessões ativas | `~/.kiro/sessions/` | 993 MB | 1031 .jsonl | payload-wrapped |
| Sub-execuções (subagentes) | dentro das sessões `sub-executions/` | incluído | — | idem |
| IDE migradas | `sessions/ide-migrated/` | incluído | — | idem |

Backup criado por cron (`backup-sessions.sh`) porque sessões Kiro estavam sendo apagadas. É a **única fonte** — perda aqui é irreversível.

## 2. Formato real (medido, 5217 linhas, 100% uniforme)

Topo SEMPRE `{id, timestamp, payload}`. O tipo está em `payload.type`:

| payload.type | freq | conteúdo | colher? |
|---|---|---|---|
| tool_call | 1406 | toolName, args, actionType (sem texto) | não (metadado) |
| **tool_result** | 1406 | **content (str/JSON) = DADO RICO** | **sim** (RFC #1346 R1) |
| **assistant** | 593 | content (str) = resposta/design longo | **sim** |
| **user** | 274 | content (str) = prompt | **sim** |
| session_metadata/turn_start/turn_end/usage_summary/session_event/pending_interaction/interaction_resolved/steering_inclusion/sub_agent_*/session_start | resto | metadados | não |

Confirmado externamente (web): Codex usa a mesma estrutura `payload.type` — payload-wrapped é padrão de mercado, não anomalia.

## 3. O bug (confirmado empiricamente pelo arch)

`src/mcp_memory_service/harvest/parser.py` — `TranscriptParser`:
- **Detecção** (`parse_file` L120-133): olha chaves do TOPO — `traceSchema`→openclaw, `type`→claude, `kind`→kiro, senão `"Unknown session format, skipping"` → retorna vazio. O formato atual tem só `{id,timestamp,payload}` → nenhum casa → **descarta a sessão inteira ANTES do instrumento de cobertura #1350** (por isso `coverage_report()` = `{}`).
- `_parse_kiro_line` (L164) espera `kind`+`data` no topo (formato Kiro ANTIGO). Zero overlap com o atual.
- **Teste real do arch:** `parse_file(messages.jsonl atual)` → `msgs: 0, coverage: {}`.
- **Consequência: 0 mensagens colhidas de ~2.5GB.**

Regressão: em 12/set (memória caa1a179) o CLI era `{kind,data}` e o parser funcionava (231 msgs). O Kiro mudou para payload-wrapped desde então; o parser ficou para trás.

## 4. Caminho de produção do harvest

`memory_harvest` (MCP, server_impl ~L1775) **e** `ConsolidationScheduler._run_scheduled_harvest` (scheduler.py:238, `MCP_HARVEST_SESSION_DIR` default `~/.kiro/sessions/cli`) → ambos `SessionHarvester.harvest_and_store` → `_harvest_file` → `parser.parse_file`. Parser volta `[]` → todo o pipeline (extractor, LLM, evolve, store) recebe zero.

**Dedup em 2 camadas:** (1) tracker por session ID (memória tag `harvest-tracker`, `harvested_sessions:<ids>`, id=`filepath.stem`); (2) `content_hash` UNIQUE + `_check_semantic_duplicate` (24h/0.85) + `_try_evolve` (evolui se similar >0.85).

**Bug menor:** handler MCP marca TODAS as sessões processadas como feitas (mesmo stored=0) → nunca re-tenta; o scheduler só marca stored>0. **Preferir o scheduler.**

## 5. Segurança de colheita — o que o parser já trata vs falta

| Item (guia Agent Island "parse safely") | Estado |
|---|---|
| Linha malformada não aborta as seguintes | ✅ trata (`except JSONDecodeError: continue`) |
| Dedupe (hash + semantic + evolve) | ✅ trata |
| Filtro de system content | ✅ parcial |
| **Redação de secrets ANTES de indexar** | ❌ **FALTA — bloqueante (2 secrets reais já vazaram hoje)** |
| Torn-tail (offset da última newline) | ❌ falta (relevante só p/ sessões ativas em escrita) |
| Rewind/truncate → re-parse full | ❌ falta (compaction trunca e reescreve → dup) |
| Linha gigante (backstop de tamanho) | ⚠️ parcial |

## 6. Fix do parser (aditivo, 1 arquivo)

`harvest/parser.py`, sem tocar claude/kiro-antigo/openclaw:
1. **Detecção:** `elif "payload" in obj and isinstance(obj["payload"],dict) and "type" in obj["payload"]: format="kiro-cli-v4"` (antes do fallback de warning).
2. **`_parse_kiro_v4_line(obj)`:** `payload.type` user/assistant → role + `payload.content` → texto; `tool_result` → conteúdo rico (RFC #1346); `tool_call`+metadados → `_record_coverage(type, was_extracted=False)` (visível no #1350, não colhido).
3. **Fixtures CI** payload-wrapped (user/assistant/tool_call/tool_result/metadata) — padrão deja-vu (1 harness = 1 parser + fixture).

## 7. Estado da arte (web, 28/set)

- **deja-vu** (vshulcz, MIT): indexa 8 formatos (Claude Code, Codex, opencode SQLite, Cursor, Gemini, aider, Antigravity, Grok). 1 parser/harness, fixtures por formato em CI, token search (não embeddings) p/ exact strings, redação de secrets (AWS/JWT/PEM) antes de indexar, sync SSH local-first.
- **Agent Island "Parse JSONL Safely"** — 8 testes essenciais (ver §5); ordem: read bounded → parse → project provider fields → identity+time → reduce.
- **arxiv 2603.29678** (View-oriented Conversation Compiler): "message format é infraestrutura de context engineering". Sessão = user/assistant/CoT/tool_call/tool_result/subagent/compaction/directives, pode passar 10k linhas.
- Compliance (EU AI Act ago/2026): histórico exportável de conversas vira requisito.

## 8. Escopo: upstream vs fork

- **Fix do parser = PR UPSTREAM.** Bug/regressão real, mandato Henry (storage/harvest), aditivo, com fixtures, alinha RFC #1346 (tool_result). 1 PR = detecção + `_parse_kiro_v4_line` + fixture. Confirmar antes que não há PR aberto para payload-wrapped.
- **Redação de secrets na ingestão** = possível 2º PR (segurança, valor universal).
- **Campanha de ingestão dos 2.5GB = FORK-ONLY/LOCAL** (ARC 4a6d729e F2, dados nossos).

## 9. Sequência recomendada (10 passos) — NÃO colher antes do fix verde

1. **Cópia read-only de segurança** do acervo (backup + ativas). Não deletar nada.
2. **Sincronizar main com upstream** + verificar PR/issue existente para payload-wrapped.
3. **Fix do parser** (detecção kiro-cli-v4 + `_parse_kiro_v4_line` + coverage em todos os ramos).
4. **Fixtures + teste CI** payload-wrapped.
5. **Dry-run numa amostra** (10-20 sessões: ativa, backup, sub-execution, ide-migrated) + validar `coverage_report()`.
6. **PR upstream** só do fix (escopo mínimo, mandato Henry).
7. **Redação de secrets** na ingestão — BLOQUEANTE para run real.
8. **Run real paginado via Scheduled Harvest**, SEM `force_reharvest`, ordem ativas → backup → sub-executions → ide-migrated; confiar em tracker + dedup semântico + evolve.
9. **Auditar amostra** do colhido (secrets? dup? sinal do tool_result?) antes de ampliar; `force_reharvest` só cirúrgico em sessões comprovadamente não colhidas.
10. **Consolidação final** via serviço; atualizar ARC 4a6d729e (F2→done).

**DEGRAU Nº 1:** cópia read-only de segurança + fix do parser com dry-run verde. Nada é colhido de verdade até o fix estar verde E a redação ativa.

## 10. Riscos

- **R1 (crítico):** recuperação em massa sem redação → re-vazamento de secrets em escala. Bloqueia tudo.
- **R2:** `force_reharvest` global → duplicação massiva contra as 22k existentes. Nunca global.
- **R3:** mexer no acervo antes do fix validado → perda irreversível.
- **R4:** divergência de tracker (handler MCP marca stored=0 como feito). Preferir scheduler.
- **R5:** tool_result rico pode inflar volume/ruído; validar sinal-ruído no dry-run.
