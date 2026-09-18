# RFC: Memory Hygiene — Noise Audit & Safe Cleanup

**Data:** 2026-09-13
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `feat/memory-hygiene` (a partir de `upstream/main`)
**Base:** `upstream/main` v11.11.0
**Versão:** 0.1 (draft)
**Inspiração:** Mnemosyne `hygiene.py` + `filters.py` (audit_noise / clean_noise, secret detection)
**Reintegra:** dor das beliefs ruidosas (task interna dc1c7756)
**Status:** DRAFT — amadurecer localmente antes de virar issue/RFC para o Henry

---

## 1. Problema

O banco acumula ruído que entrou antes de qualquer filtro existir (ou por vias que o ignoram) e não há mecanismo para auditar e limpar com segurança. Isso infla FTS e conteúdo, degrada retrieval e polui o belief/bootstrap profile.

### Evidências (13/set/2026, banco de produção sirdata)

- FTS (`memory_content_fts_data`) 142 MB (31% do banco) + conteúdo (`memories`) 101 MB (22%) = **243 MB sujeitos a ruído**.
- Beliefs ruidosas: 107 beliefs ativas, confiança máx 0,64; top-10 do bootstrap profile inclui checkpoints, sessões antigas (OpenClaw, Core API) e demos (WireMock) — não conhecimento acionável.
- Acervo `session-harvest` com 63% de memórias 80–200 chars (fragmentos conversacionais crus).
- Sem ferramenta de audit: o único caminho hoje é `memory_delete` manual por hash/tag.

### Causas (a confirmar no código)

1. **Ruído legado.** Memórias escritas antes do `ignore_patterns` existir, ou via MCP/SDK/CLI que o contornaram: terminal spam, stack traces, dumps, secrets já no banco.
2. **Sem audit/score de ruído.** Não há função que varra `memories` + `working` + `episodic` e pontue cada linha por probabilidade de ruído e presença de secret.
3. **Sem cleanup seguro.** Não há operação dry-run + archive reversível + log de auditoria para remoção em lote.

### Risco

Deletar memória-fonte de sessão (plano OneDrive) sem limpar antes cristaliza o ruído. E o bootstrap profile propaga ruído para todo agente que spawna.

---

## 2. Objetivo

Fornecer **audit de ruído** (dry-run, com score) e **cleanup seguro** (delete/archive/keep, com log auditável), mais **secret detection na ingestão**, reduzindo tamanho e melhorando a qualidade do retrieval e do belief system.

**Não-objetivos:** re-derivar beliefs (mecanismo já existe); alterar o pipeline de harvest (RFC própria); comprimir embeddings (RFC própria).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1).

### Funcional

**R1**: É possível auditar o acervo por ruído sem modificá-lo.

> EARS: WHEN `audit_noise()` is invoked, THE system SHALL scan `memories` (and `episodic`/`working` when present), score each row for noise likelihood and secret presence, and return ranked candidates without writing.

**R2**: O audit é dry-run por padrão.

> EARS: WHEN `audit_noise()` is invoked without an explicit write flag, THE system SHALL operate in dry-run and modify nothing.

**R3**: O cleanup aplica uma de três ações por candidato.

> EARS: WHEN `clean_noise(action)` is invoked, THE system SHALL apply `delete`, `archive` or `keep` per candidate and write a full audit log.

**R4**: O archive é reversível.

> EARS: WHERE `action=archive`, THE system SHALL move the memory to an archive store recoverable by hash.

**R5**: A ingestão detecta e sinaliza secrets.

> EARS: WHEN a memory containing a detected secret pattern (API key, token, private key) is stored, THE ingestion SHALL flag or block it per policy.

**R6**: O cleanup devolve espaço ao disco.

> EARS: WHEN a cleanup batch completes with deletions, THE system SHALL run `VACUUM` and report bytes reclaimed.

### Não-Funcional

**R7**: O audit não produz falso-positivo destrutivo.

> EARS: THE audit SHALL classify borderline rows as `keep` rather than `delete` when the noise score is below the high-confidence threshold.

**R8**: O secret detection não bloqueia caminhos legítimos.

> EARS: WHERE a memory merely references a secret's variable name without its value, THE ingestion SHALL allow it.

---

## 4. Design

- `hygiene.py`: `audit_noise()` (score por regex de ruído + heurística de fragmento curto + detecção de secret) → candidatos ranqueados; `clean_noise(batch, action)` → aplica + loga.
- `filters.py`: `detect_secret(content)` reusado tanto na ingestão (R5) quanto no audit (R1).
- Tool MCP: `memory_hygiene_audit` (dry-run) e `memory_hygiene_clean` (com confirmação).
- Integração com belief system: após cleanup, disparar re-derivação de beliefs para expurgar ruído do profile.

### Estimativa (dados reais)
- Ruído sobre 243 MB (FTS+conteúdo): conservador 10% = **−24 MB**; moderado 20% = **−49 MB**; agressivo 30% = **−73 MB**.
- Ganho real depende do `candidate_ratio` medido — **rodar audit dry-run no banco antes de fixar**.

### ⚠️ MEDIÇÃO REAL — audit_noise dry-run em sirdata (18/set/2026)

Rodado o `audit_noise` (protótipo) contra o banco de produção (22.033 memórias, 505 MB). Resultado **corrige a estimativa acima, que estava superestimada**:

| Bucket | Qtd | Nota |
|--------|-----|------|
| delete (score ≥0.6) | 39 | ruído claro (stacktrace, test-artifact) |
| review (0.4–0.6) | 615 | borderline (fragmentos harvest, test-tags) |
| keep (<0.4) | 21.379 | 97% |
| **candidate_ratio** | **3,0%** | 654/22.033 — MUITO abaixo dos 10-30% estimados |
| conteúdo candidato | ~0,2 MB | só coluna `content` |

**Conclusão que reposiciona a RFC:**
1. O banco de 505 MB **não é inchado por ruído de conteúdo** (só 3% / ~0,2 MB). O peso está em **FTS (142 MB) + embeddings** → o ganho de DISCO é da **D1 (quantization)**, não da D2.
2. O valor real da D2 é **QUALIDADE + SEGURANÇA**, não disco:
   - **secret detection funcionou: 5 hits, 2 REAIS** (API key DeepSeek da T'Pol + key OCI/LIA do MIR, vazadas via checkpoint/correção de sessão). Removidas em 18/set; **keys devem ser rotacionadas**. Os outros 3 eram placeholders de doc (HCSO cert_demo, JWT sample techdocs) — o detector precisa distinguir sample de valor real (allowlist de contexto doc).
   - 261 memórias com `test-tag` + 2.643 harvest-fragments poluem bootstrap/belief profile.
3. **Ação p/ RFC madura ao Henry:** reposicionar D2 como "noise & secret hygiene para qualidade de retrieval/belief" (não "reduzir disco"). Números reais dão credibilidade. O `candidate_ratio` real (3%) vira o baseline honesto. Secret detection com allowlist de doc-context é o R5 refinado.

---

## 5. Fora de Escopo

- Re-derivação de beliefs (mecanismo já existe; hygiene apenas dispara).
- Reescrita de extração de harvest.
- Quantização de embeddings (RFC própria).

---

## 6. Critérios de Aceite

- [ ] `audit_noise()` roda dry-run, pontua e ranqueia candidatos sem escrever.
- [ ] `clean_noise()` aplica delete/archive/keep com log de auditoria e archive reversível.
- [ ] Secret detection bloqueia/flagga valor de secret mas permite referência ao nome da variável.
- [ ] Cleanup roda `VACUUM` e reporta bytes recuperados.
- [ ] Bootstrap profile re-derivado após cleanup não contém ruído auditado.
