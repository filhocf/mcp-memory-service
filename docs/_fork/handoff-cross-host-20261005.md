# Handoff cross-host — sessão DNBSCDC289 05/out/2026

> Para quando a próxima sessão abrir no **sirdata** ou **socrates**. O que mudou aqui hoje e o
> que cada máquina precisa fazer para sincronizar. Memória espelho: tag `mms-ledger` + checkpoint.

## 1. Fork mcp-memory-service — PUBLICADO no github (fazer sync)
Estado: `main` @ `a5049863`, 0/0 com github, 0 atrás do upstream. Commits de hoje:
- Merge upstream v11.15.0 (2 commits: #1455 logs, #1456 Prometheus) + migration 014 (usage_events) aplicada no restart.
- `cfabfd95` docs #346 (cruzamento + draft Henry).
- `9acaf2b9` (idem docs).
- **`a5049863` WIRING L4** (feature nova — ver §4).

**AÇÃO sirdata/socrates:** `git fetch github --prune && git checkout main && git merge --ff-only github/main`.
Depois **reinstalar venv + restart** (AGENTS §): `VIRTUAL_ENV=.venv uv pip install -e . --no-deps` → `systemctl --user restart memory-service.service`. O restart aplica migration 014 se o banco local ainda não tiver (checar `migration_registry` MAX version = 14; usage_events existe).

## 2. ai-configs (.kiro) — via Insync/OneDrive (propaga sozinho, mas CONFERIR)
- **Faxina de conflitos de sync** no `.kiro`: deletadas pastas `skills 1/2`, `steering 1/2`, `argv 1/2/3.json`, 11 conflitos em `agents/`, conflitos npm em `extensions`. **Se o Insync recriar algum ` N`/`(N)` no sirdata/socrates, deletar** (são colisões, não conteúdo).
- **4 skills resgatadas** para `skills/` (estavam presas em `skills 2/`): `memory-service-context`, `lgpd-advisor`, `miro-board-code`, `pr-cycle-ai-review`. Confirmar que chegaram.
- **`steering/dynamic/lessons-learned.md` MESCLADO** (version 2026-10-05): tem itens técnicos + seções Doc-Sync e Hooks. Se o Insync trouxer versão antiga em conflito, a de 05/out vence.
- **Backup da config limpa:** `ai-configs/kiro-config-backups/kiro-config-clean-20261005_*.tar.gz` (291K, no sync).

## 3. Config dos agentes dev — trust granular (NOVO)
`reg/dal/torres/rok.json`: adicionado `write` ao `allowedTools` + `toolsSettings.shell` com allowlist de dev
(pytest/python/uv/git/build-por-stack, SEM rm/curl/push). Lido no spawn do subagent — vale automático nas 3 máquinas via sync. seven/tuvok já eram read-only granular.

## 4. Learning-loop L4 — WIRING ATIVO (contexto para continuar)
Fechou o ciclo colher→destilar→injetar→VALIDAR. 3 peças ligadas:
- Job `quality_recalc` no ConsolidationScheduler, opt-in **`MCP_QUALITY_RECALC_SCHEDULE=6h`** (no `memory-service.env` compartilhado → vale nas 3 máquinas).
- Grava `computed_quality` (máquina) + materializa `quality_score` via `effective_quality` **preservando user_rating** (#1312). Clamp [0,1].
- Tool MCP `get_assertiveness_metrics` (ADR-0005): re_query_rate / injection_coverage / lost_context.
- **Baseline N1 (05/out):** re_query=0.125, injection_coverage=0.0, lost_context=0.625. Janela até ~10/out.

**PRÓXIMO (qualquer máquina, após N1 ~10/out):** (1) ligar score no ranking do retrieval (RFC-MM-01 §5, só após N1 provar); (2) N2 push automático; (3) N3 feedback positivo; (4) PR ao Henry quando janela provar valor (confirmar #1286).

## 5. Sessões Kiro recuperadas (só DNBSCDC289, via Insync propaga)
545 sessões da "morte súbita" restauradas em `.kiro/sessions/cli` (1248→1793) + 2 workspace-dirs. Scripts de colheita preservados em `ai-configs/scripts/session-harvest/`. **Colheita NÃO feita** (Claudio não quis agora) — quando colher: `memory_consolidate action=harvest path=~/.kiro/sessions/cli` (triagem ON, serviço já com código novo).

## 6. Pendências abertas (decisão do Claudio)
- `feat/nli-observability`: branch local DNBSCDC289 com 1 commit único #1235, remota apagada na limpeza. ORFAOS.md diz "OBSOLETO — resgatar reverteria melhorias do main". Decidir deletar.
- `pr-cycle-ai-review` vs `pr-review` coexistem em skills/ — consolidar numa só.
- Comentário postado na Discussion #346 (discussioncomment-18760031) — acompanhar resposta do Henry.
- Inbox GitHub: 9 notificações NÃO marcadas como lidas (incl. #1460 auto-supersede — temos evidência própria do falso-positivo de quarentena de hoje para comentar).

## 7. Backups locais (NÃO vão pro sync — por máquina)
- `~/local-data/kiro-conflict-backups/` (faxina .kiro: steering, agents, skills, FULL 964M)
- `~/local-data/mcp-db-backups/` (banco pré-restart + pré-L4wiring)
- `~/local-data/kiro-sessions-backup/` — **EXCLUÍDO** hoje (conteúdo único já resgatado; só DNBSCDC289).

---

## 8. TARDE 05/out — PRs atômicos do arco ingestão (atualização)

**PR1 Kiro→YAML — FEITO (commit 5308efda, na linha viva).** harvest/agents/kiro.yaml + loader
(load_agent_profile, espelha patterns/) + parser lê do profile. Byte-idêntico (arch provou: parser
novo vs HEAD, 0 mismatches). Gate G0-G5. Triagem já estava plugada (02/out). Pronto p/ virar PR upstream
(toca harvest/, nosso mandato). Sem migration.

**PR1.5 — bug canal MCP (NÃO é bug de código).** Arco "3 fontes Kiro" (WI d500bdfb). A tool
`memory_consolidate action=harvest` com sessions=20 dá sessions:1. Arch (seven) PROVOU que o handler
real dá 20 — o código está correto. É stale no CANAL MCP (mcp-proxy/cliente Kiro com schema/conexão em
cache). **Claudio vai REINICIAR O CLIENTE Kiro.** Após reiniciar: testar a tool (sessions=20 deve dar
20) → se OK, PR1.5 fechado como stale de cliente. Evidência: ~/.kiro/active-tasks/bug-harvest-sessions-evidencia.md.

**Arco 3 fontes Kiro (WI d500bdfb):** CLI ✅. IDE 🟡 (neste host JÁ é v4 payload-wrapped = CLI, só path
difere; history[] é formato antigo de outros hosts; discovery do path IDE = evolução WI ad09b221).
Crew ❌ (schema episodic_memories próprio, parse_sqlite só lê conversations_v2 do CLI; importar via
memory_store = evolução WI 0a0fb0f9). Doc base no CdIA: ferramentas/kiro/importar-sessoes-kiro.md.

**Specs reconciliadas:** MM-02 (fonte=uso real, ADR-0003), MM-03 (9 EARS). Achado: trilogia (branch
validacao) tem núcleo+testes mas DESPLUGADA (igual padrão L4).

**Pings postados:** #346 (discussioncomment-18760031), #1393 (discussioncomment-18762368).

**PRÓXIMO (pós-reinício cliente):** testar harvest → fechar PR1.5 → PR2 gap-detection (wiring: hook
record_gap no search + tool registry + migration 015) → PR3 fact-extraction (migration 016 + job + tool).
Janela N1 learning-loop até ~10/out.

**Regra reforçada (mistake 5a08fe0f):** "mesmo código, resultado diferente" = ambiente/runtime
(processo/proxy/cache), NÃO lógica. Diagnosticar runtime primeiro; delegar arch ao 1º sinal de túnel.
