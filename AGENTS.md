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

> Este arquivo vive na branch `service` (NUNCA vira PR — não vaza pro upstream).
> Ao entrar neste repo, ANTES de qualquer tarefa, situe-se com os passos abaixo.

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
- **`~/git/mcp-memory-service`** (ESTE) → branch `service` = v11.11.0 + nossas feats. **O SERVIÇO systemd roda daqui** (venv editable, `--user memory-service`). Banco: `~/local-data/mcp/sqlite_vec.db`.
- **`~/git/mcp-memory-service-dev`** → worktree da pilha de PRs (branches `pr/NNNN`, saem de `upstream/main`).
- **`main`** (branch, v11.5.5) = rollback do serviço. `upstream` = GitHub doobidoo (fetch-only). Push só nos forks.

## RFCs e feats novas (fluxo — NÃO improvisar)
- **RFC = doc de amadurecimento, FORK-ONLY.** Vive SÓ em `docs/rfc/RFC-<tema>.md` na branch **`main`** do fork. NUNCA vira PR upstream.
- **EARS obrigatório na RFC.** Requisitos em prosa + EARS (DEVELOPMENT-STANDARDS §8.4.1): uma ação por frase, sujeito = componente (`THE harvester SHALL`), testável. A EARS da RFC vira acceptance criteria e origina os testes G3 RED — é o que guia a implementação.
- **Este repo é FORK de terceiro.** `specs/` e `docs/superpowers/` são do UPSTREAM (Henry) — read-only, NUNCA commitar ali. O layout SDD nosso (`sdd/specs/planned|implemented`, SPEC-F###) é para projetos PRÓPRIOS (MIR, query-one), NÃO para forks. Em fork, a RFC em `docs/rfc/` É a spec de trabalho.
- Fluxo: (1) RFC na `main` para amadurecer → (2) issue/RFC no GitHub p/ o Henry avaliar quando é algo novo → (3) atualizar o RFC local conforme evolui.
- **Commit de RFC na `main`:** checkout temporário da `main` num worktree LIVRE (o dev, se limpo) → commit → volta. Não criar worktree em `/tmp` nem mexer na `service`.
- **Feat nova que estende um PR ainda não mergeado:** empilhar em worktree próprio a partir do PR-pai (ex: `feat/harvest-provenance` sai de `pr/scheduled-harvest`). Só vira PR quando o pai mergear (regra 1-PR-por-vez). Estado da pilha vive no runbook.

## Estado da branch `service` (atualizar quando mudar)
- Base v11.11.0 + NLI cascade + Store-NER + fix cascade (backend=auto).
- Embedding: **torch/multilingual** (`paraphrase-multilingual-MiniLM-L12-v2`, PT-BR). USE_ONNX=0.
  ONNX leve pendente = issue #143 (modelo ONNX pronto: `onnx-community/paraphrase-multilingual-MiniLM-L12-v2-ONNX`).
- Onda 2 pendente: Trilogia RFC-MM (facts/gaps/feedback, roda em background via scheduler).

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
