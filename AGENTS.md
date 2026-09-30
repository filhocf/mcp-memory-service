<!-- gitnexus:start -->
# GitNexus MCP

This project is indexed by GitNexus as **mcp-memory-service** (6259 symbols, 18031 relationships, 300 execution flows).

GitNexus provides a knowledge graph over this codebase — call chains, blast radius, execution flows, and semantic search.

## Always Start Here

For any task involving code understanding, debugging, impact analysis, or refactoring, you must:

1. **Read `gitnexus://repo/{name}/context`** — codebase overview + check index freshness
2. **Match your task to a skill below** and **read that skill file**
3. **Follow the skill's workflow and checklist**

> If step 1 warns the index is stale, run `npx gitnexus analyze` in the terminal first.

## Skills

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/refactoring/SKILL.md` |

## Tools Reference

| Tool | What it gives you |
|------|-------------------|
| `query` | Process-grouped code intelligence — execution flows related to a concept |
| `context` | 360-degree symbol view — categorized refs, processes it participates in |
| `impact` | Symbol blast radius — what breaks at depth 1/2/3 with confidence |
| `detect_changes` | Git-diff impact — what do your current changes affect |
| `rename` | Multi-file coordinated rename with confidence-tagged edits |
| `cypher` | Raw graph queries (read `gitnexus://repo/{name}/schema` first) |
| `list_repos` | Discover indexed repos |

## Resources Reference

Lightweight reads (~100-500 tokens) for navigation:

| Resource | Content |
|----------|---------|
| `gitnexus://repo/{name}/context` | Stats, staleness check |
| `gitnexus://repo/{name}/clusters` | All functional areas with cohesion scores |
| `gitnexus://repo/{name}/cluster/{clusterName}` | Area members |
| `gitnexus://repo/{name}/processes` | All execution flows |
| `gitnexus://repo/{name}/process/{processName}` | Step-by-step trace |
| `gitnexus://repo/{name}/schema` | Graph schema for Cypher |

## Graph Schema

**Nodes:** File, Function, Class, Interface, Method, Community, Process
**Edges (via CodeRelation.type):** CALLS, IMPORTS, EXTENDS, IMPLEMENTS, DEFINES, MEMBER_OF, STEP_IN_PROCESS

```cypher
MATCH (caller)-[:CodeRelation {type: 'CALLS'}]->(f:Function {name: "myFunc"})
RETURN caller.name, caller.filePath
```

<!-- gitnexus:end -->
---

# 🎯 START HERE — agente (fork/serviço do Claudio)

> Este arquivo vive na branch `main` do fork = LINHA VIVA (NUNCA vira PR — não vaza pro upstream).
> Ao entrar neste repo, ANTES de qualquer tarefa, situe-se com os passos abaixo.
> **Reorg concluída 15/set:** a `main` do fork é agora upstream/main (v11.12.0) + camada nossa. O serviço roda dela.

## Passos de arranque (sempre)
1. **Carregar a skill:** `~/.kiro/skills/memory-service-maintainer/SKILL.md`
   (mandato do Henry, escopo de merge, fluxo de PR, gate G5, pitfalls).
2. **Buscar estado recente:** `memory_search("mcp-memory-service Henry mandato fila", tags=["mcp-memory-service","henry"], limit=5)`.
3. **Ler o runbook:** `~/git/conhecimentos-de-ia/ferramentas/mcp/memory-service/PILHA-PRs-runbook.md`
   (ambiente, pilha de PRs, baldes, §Atualização do SERVIÇO).

## Dois modos de trabalho (NÃO confundir)
- **DESENVOLVER nossas feats** → nosso método SDD/G0-G6 (`~/git/conhecimentos-de-ia/padroes/DEVELOPMENT-STANDARDS.md §0`).
- **TRANSPORTAR para upstream/PR** → método do HENRY (board verde, `tests-prove-fix`, squash + `(#PR)`,
  1 review dele, 1 PR por issue). Antes do PR: gate **G5** (subagent reviewer + teste de INTEGRAÇÃO).

## Ambiente (3 lugares, não misturar)
- **`~/git/mcp-memory-service`** (ESTE) → branch **`main`** = LINHA VIVA = `upstream/main` (v11.12.0) + camada nossa (docs/rfc, feats fork-only: Store-NER, harvest provenance/re-harvest, NLI wire, **harvest on-demand action com path+guard (0ccaf01e)**, AGENTS). **O SERVIÇO systemd roda daqui** (venv editable uv, `--user memory-service`). Banco: `~/local-data/mcp/sqlite_vec.db`.
- **`~/git/mcp-memory-service-dev`** → worktree da pilha de PRs (branches `pr/NNNN`, saem de `upstream/main`).
- **`upstream`** = GitHub doobidoo (fetch-only). Push só no fork (`github`).

**Modelo de branches (em vigor desde 15/set):**
```
upstream/main ──→ pr/<feat> ──(Henry mergeia)──→ upstream/main
                                       │ (merge periódico do upstream)
                                       ▼
                                    main (fork) ← LINHA VIVA (serviço roda daqui)
```
- **Feat aprovada volta à `main` via `git merge upstream/main`, NUNCA cherry-pick** — quando o Henry mergeia nosso PR, o merge do upstream substitui nossa versão fork-only pela oficial (evita duplicata). Foi assim que NLI #1215/ONNX #1242/scheduler #1241 convergiram no merge de 15/set.
- **Gestão viva:** a cada PR nosso mergeado no upstream, fazer `git merge upstream/main` na `main` e resolver conflitos ficando com o upstream onde ele absorveu a feat.
- Tudo que difere do upstream (docs/rfc, fork-only) habita SÓ na `main`.
- Backups: `backup/service-pre-mainswap-0915` (service pré-swap), `backup/main-fork-2026-09-02`.

## RFCs e feats novas (fluxo — NÃO improvisar)
- **RFC = doc de amadurecimento, FORK-ONLY.** Vive SÓ em `docs/rfc/RFC-<tema>.md` na branch **`main`** do fork. NUNCA vira PR upstream.
- **EARS obrigatório na RFC.** Requisitos em prosa + EARS (DEVELOPMENT-STANDARDS §8.4.1): uma ação por frase, sujeito = componente (`THE harvester SHALL`), testável. A EARS da RFC vira acceptance criteria e origina os testes G3 RED — é o que guia a implementação.
- **Este repo é FORK de terceiro.** `specs/` e `docs/superpowers/` são do UPSTREAM (Henry) — read-only, NUNCA commitar ali. O layout SDD nosso (`sdd/specs/planned|implemented`, SPEC-F###) é para projetos PRÓPRIOS (MIR, query-one), NÃO para forks. Em fork, a RFC em `docs/rfc/` É a spec de trabalho.
- Fluxo: (1) RFC na `main` para amadurecer → (2) issue/RFC no GitHub p/ o Henry avaliar quando é algo novo → (3) atualizar o RFC local conforme evolui.
- **Commit de RFC na `main`:** a `main` É o working tree do serviço (este repo). Editar `docs/rfc/`, commitar, e `git merge`/push quando alinhar. Se o serviço estiver rodando, o commit de docs não afeta runtime.
- **Feat nova que estende um PR ainda não mergeado:** empilhar em worktree próprio a partir do PR-pai (ex: `feat/harvest-provenance` sai de `pr/scheduled-harvest`). Só vira PR quando o pai mergear (regra 1-PR-por-vez). Estado da pilha vive no runbook.

## Estado da `main` (atualizar quando mudar)
- **30/set (DNBSCDC289):** main **0 atrás / sincronizada com upstream** (merges 772d1eb4 + eee64834; backups backup/main-pre-upstream-merge-20260930 e -20260930b). Trazidos do upstream: **#1382** (honor MCP_LOCALE no harvest/rewriter/bootstrap — reusável pelo I2), **#1368** (retention_periods rekeyed p/ ontologia — **FECHA o furo #1355; nosso #1349 quality-split volta a ter efeito no decay**, antes mascarado), #1146 sanitize, #1373 backfill (nosso), deps/docs. **Arco harvest multi-formato (grupo I) entregue:** **#1378 MERGEADO** (a95f85f2 — discovery+id+resolve sessões workspace + path guard); **#1379 MERGEADO** (9079737b, 13:32 UTC) (parser SQLite conversations_v2 + idioma no Phase 0 split extracted/dropped). Fork-only novo: I0-lang (idioma Phase 0), parse_sqlite, _session_id/_resolve_session_id, _detect_language, RFCs harvest-kiro-sessions v2.0 / design-extraction v0.4 (idioma=locale mechanism) / source-identity v0.1. **Arco portabilidade:** Henry aceitou modelo 5 camadas; wiki Memory-Portability-Map; issue #1390 (conversor mem0). G0 do I2 feito (CdIA G0-design-extractor-I2.md). PRÓXIMO: I1 (visibilidade thinking/ToolResult) → I2 (gate: #1379 mergear + números Phase 0).
- **28/set (DNBSCDC289):** main mergeada com `upstream/main` (7 commits: **#1349 quality-split #1312 NOSSO agora OFICIAL** upstream 97e699e0 + #1358 GH triage-digest + #1356 CF topK 100 + #1357/#1351 docs-roadmap + #1360/#1146 log-sanit embeddings + #1353 test-hybrid). **ahead 62 / behind 0**, github `98461cf9`, backup/main-pre-1349merge-20260928. Suíte quality 6/6 verde. **Arco rating/quality-model ENTREGUE** (computed_quality vs user_rating, effective score materializado, forgetting lê computed). Fila Henry VAZIA.
- Base **upstream/main v11.14.0 + 14 commits** (25/set: #1306/#1146 log-sanit, #1307 scorers, #1315 holiday, #1316 exact-match; 26/set manhã: #1302 UTC decay, #1317 contradiction supersede fix, #1320 AUTO_SUPERSEDE; 26/set noite: #1314/#1146 log-sanit graph, #1322/#1323 README revamp 589→265, #1325 test log-injection, **#1326 evolve через MemoryService (scored)**, #1327 BM25 individual terms, #1329 codeowners; 56 ahead / 0 behind, backup/main-pre-1326merge-20260926) + camada fork-only: Store-NER, NLI wire. ⚠️ No merge de 26/set-noite houve 1 conflito real em test_session_coverage.py + harvester.py: nossa `verify_session_coverage` era a versão ANTERIOR (sem fixes Greptile threshold/path-traversal/session_found) — resolvido ficando com upstream (superset). ⚠️ **DECISÃO 26/set: `MCP_CONSOLIDATION_AUTO_SUPERSEDE=false`** (env compartilhado + sirdata.env). compartilhado + sirdata.env) — o #1317 ligou o superseding-por-contradição que estava dormente; com graph_only+consolidation on, memórias "contradicts" (conf≥0.75) sumiriam do retrieval. false mantém aresta no grafo + ambas visíveis. Conservador enquanto arco rating/#1312 aberto. **agent_id Fase 1 (#1100) + Fase 2 (#1297) agora OFICIAIS no upstream v11.14.0** (autoria no store + filtro opt-in search/list + header X-Agent-ID no /mcp) — pré-requisito do delta-sync satisfeito. **harvest provenance (#1243), verify_session_coverage (#1252), re-harvest/force_reharvest (R8), NLI cascade (#1215/#1265), last_accessed (#1240) — TODOS absorvidos pelo upstream** (não são mais fork-only). NLI cascade/ONNX/scheduler = versões do upstream.
- ⚠️ **Base do arco rating mudou (v11.14.0):** #1291 (get_access_patterns janela content_hashes) + #1240 (lê last_accessed) foram mergeados por terceiros/nós → o G0 do arco rating (relatório f3-g0-analise.md) precisa RE-VALIDAÇÃO antes de agir (parte dos furos pode ter sido corrigida). #1216 (belief quarantine + NLI on-store) também mexeu em dedup/belief.
- Embedding: **ONNX** (`paraphrase-multilingual-MiniLM-L12-v2`, PT-BR, dim 384). USE_ONNX=1, venv leve uv (sem torch).
- **28/set (DNBSCDC289, tarde) — feat fork-only harvest on-demand:** action `harvest` no `memory_consolidate` (`0ccaf01e`). Dispara harvest de um `path` sob demanda, **in-process** (usa `server.storage`/`MemoryService` → grafo/dedup/provenance íntegros; standalone perde o `memory_graph`). Params `path/sessions/use_llm/dry_run/force_reharvest`. Preenche o gap: `memory_harvest` aceita `project_path` mas é **bloqueado no HTTP** (GHSA-7crr-2r7w-cpfm). ⚠️ **Guard obrigatório** (o 1º commit `aee64cad` reintroduzia o path-traversal): `resolve()` + allowlist `MCP_HARVEST_ALLOWED_ROOTS` (`:`-sep, default fechado `~/.kiro`/`MCP_HARVEST_SESSION_DIR`/`~/local-data`) + `is_relative_to`. 16 testes (`tests/test_harvest_action.py`) incl. bloqueio traversal/symlink (`assert_not_called`). Gates arch+dev-tests+reviewer (reviewer APROVADO PARA PR). **Usado p/ resgatar 195 conversas SQLite CLI** (dez25–jun26, só no `data.sqlite3`) → 37 mems com grafo. **Candidato a PR upstream** (mandato harvest; sincronizar upstream + checar issue vizinha antes). changelog.d/1367.added.md.
- 18 RFCs em `docs/rfc/` (harvest-provenance v0.5, 9 Mnemosyne, agent-id, config-audit, etc). Ver ANALISE.md.
- Onda 2 pendente: Trilogia RFC-MM (facts/gaps/feedback, background via scheduler).
- reinstalar após pull: `VIRTUAL_ENV=.venv uv pip install -e . --no-deps` (venv é uv, sem pip; alinha versão instalada).

## Validação de features LLM
## Validação de features LLM — TESTES E2E REAIS (obrigatório antes de PR)

**Regra (Claudio, 13/set): NUNCA publicar sem testes E2E REAIS contra os providers.** E2E é parte do G5 (não gate separado): teste de integração no caminho real + subagent(reviewer). Mock não conta.

**Ordem de prioridade dos providers (o que o usuário geral usa):**
1. **groq** (primário — usuário geral). Modelo: `openai/gpt-oss-120b` (llama-3.3 foi descontinuado).
2. **ollama** (local, offline). Modelo: `qwen2.5:3b` (instruct, não-thinking; qwen3/gemma3 dão saída vazia). Roda em GTX 1050 Ti 4GB + RAM.
3. **deepseek** (fallback). Modelo: `deepseek-chat`.

**Como rodar o E2E real:**
```bash
set -a; source ~/dtp/ai-configs/services/env/memory-service.env; set +a
set -a; source ~/dtp/ai-configs/services/env/memory-service.$(hostname).env; set +a  # keys host-specific
MCP_E2E_LLM=1 PYTHONPATH=src <venv>/python -m pytest tests/test_*_e2e.py -v
```
Validar CADA provider isolando `HARVEST_LLM_PROVIDERS=<p>` + confirmar o efeito no banco (não só contar totais).

**API keys**: vivem em `memory-service.$(hostname).env` (host-specific, blindado contra reversão do Insync — ver §RFCs). NUNCA só no `.env` compartilhado.
