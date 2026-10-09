# Atualização do serviço memory-service por máquina + Estado da VPS (hub)

## REGRA (07/out): feature comprovada local → replica no VPS
Sempre que uma feature/fix for feita e COMPROVADA localmente (gate completo + E2E), **replicar para o VPS** (hub `cfnarede.dev`) no mesmo fluxo — o hub fica na linha viva, não arrasta atrás. Hub desatualizado impede E2E completo (store→pull cliente↔hub). É ação esperada (autonomia, decisão Claudio), só avisar. Backup do banco SEMPRE antes (sistema compartilhado Scotty/T'Pol). Procedimento abaixo.

---

**Criado:** 2026-09-21 · **Autor:** Claudio + Zero (DNBSCDC289)
**Contexto:** consolidação da memória multi-agente num hub central na VPS. F1 (agent_id) já mergeada no upstream (nosso PR #1278, 19/set). Precisa chegar às 3 máquinas do Zero + VPS.

---

## Padrão único (decisão 21/set): ONNX-only, sem CUDA

TODAS as máquinas usam:
- Embeddings via **onnxruntime** + `paraphrase-multilingual-MiniLM-L12-v2` (384 dims).
- **Sem torch/CUDA** (venv leve ~500M vs 5G). GPU não é usada pelo memory-service.
- Config de host: `CUDA_VISIBLE_DEVICES=` (vazio) + `TORCH_DEVICE=cpu` + `MCP_MEMORY_USE_ONNX=1`.
- socrates (RTX 3060) tinha CUDA — ABANDONADO em 21/set (arquivo memory-service.socrates.env já ajustado).

---

## Procedimento de atualização do serviço (por máquina)

Repo do serviço: `~/git/mcp-memory-service` (branch `main`, editable venv, systemd `memory-service.service`).
Config por host: `~/dtp/ai-configs/services/env/memory-service.{HOST}.env` + `memory-service.env` (ativo).

### Passos (validados na DNBSCDC289 em 21/set)

1. **Backup do banco** (rede de segurança):
   ```bash
   sqlite3 ~/local-data/mcp/sqlite_vec.db "VACUUM INTO '~/local-data/mcp/sqlite_vec.pre-update.$(date +%Y%m%d%H%M%S).db';"
   ```
2. **Guardar rollback point:**
   ```bash
   cd ~/git/mcp-memory-service && git rev-parse HEAD  # anotar
   ```
3. **Merge upstream (NÃO rebase — main é linha viva):**
   ```bash
   git fetch --all --prune --tags   # OBRIGATÓRIO --all: pega github + upstream de uma vez (lição 08/out)
   # ANTES de mergear, confirmar a posição vs o NOSSO remoto (fonte de verdade entre máquinas):
   git rev-list --left-right --count main...github/main   # atrás do github/main? → ff primeiro
   git merge --ff-only github/main 2>/dev/null || true    # pega trabalho de outras máquinas (sirdata/DNBSCDC289)
   git merge upstream/main --no-edit                       # só reconcilia o que github/main ainda não tem
   ```
   - **Lição 08/out (Claudio):** `fetch upstream` sozinho mascara o estado — outra máquina avança `github/main` e esta não vê. Comparar com `github/main` PRIMEIRO, FF, e só então upstream. Nunca basear estado em memória.
   - Conflitos esperados em arquivos fork-only (harvest/scheduler/server_impl/docs). Em 21/set todos eram
     NOSSA feature em versão refinada no upstream → resolver com `git checkout --theirs <arquivo>` para
     CÓDIGO e TESTES (versão final), e fusão manual em docs (conteúdo complementar, não escolher lado).
4. **Validar testes-chave ANTES de reinstalar:**
   ```bash
   .venv/bin/python -m pytest tests/test_agent_id.py tests/test_harvest_reharvest.py tests/test_session_coverage.py -q
   ```
   Esperado: ~28 passed.
5. **Adicionar MCP_AGENT_ID na config do host** (padrão host-specific, blinda contra reversão Insync):
   ```bash
   echo -e '\n# Identidade de autor (RFC #1100 F1)\nMCP_AGENT_ID=zero' >> ~/dtp/ai-configs/services/env/memory-service.{HOST}.env
   # e no memory-service.env ativo
   ```
   - agent_id por máquina: TODAS as máquinas do Zero usam `zero` (é o mesmo agente em máquinas diferentes;
     o HOST distingue via metadata.hostname/source:{host}, o agent_id distingue o AGENTE).
6. **Restart + validar** (venv é `uv`, NÃO tem pip; editable já reflete o merge):
   ```bash
   systemctl --user restart memory-service.service
   systemctl --user is-active memory-service.service
   ```
7. **Teste funcional (o que prova a F1):** gravar sem agent_id → deve pegar `zero` da env; com agent_id explícito → sobrepõe.
   ```bash
   # via MCP na porta 3202 (DNBSCDC289) — ajustar porta por host
   # store sem agent_id, depois: SELECT json_extract(metadata,'$.agent_id') ... deve ser 'zero'
   ```
   ⚠️ o `sqlite3` CLI do sistema pode não ter FTS5 (`no such module: fts5`) — para DELETE/verificação em
   tabelas com trigger FTS, usar as tools MCP (memory_delete/memory_search), não o sqlite3 CLI.

### Rollback
```bash
cd ~/git/mcp-memory-service && git reset --hard <ROLLBACK_HEAD> && systemctl --user restart memory-service.service
# banco: restaurar o pre-update.*.db se necessário
```

---

## Estado por máquina (checklist)
| Máquina | Versão serviço | delta-sync F5 | papel sync | Status (09/out) |
|---------|---------------|---------------|-----------|-----------------|
| DNBSCDC289 | v11.15.0 (HEAD 9355b6cd) | ✅ bootstrap presente | spoke (MCP_SYNC_SCHEDULE=1m → hub) | ✅ OPERACIONAL 09/out: sync bidirecional provado E2E (pull 194→197, push 386→390, hash propagou ao hub). Clamp quality aplicado. |
| VPS (hub) | v11.15.0 (HEAD 9355b6cd) | ✅ bootstrap presente | hub (pivot passivo, sem peers) | ✅ OPERACIONAL 09/out: replicado da F4d→HEAD, 20659 mems preservadas, MCP_SYNC_EVENTLOG=on, serve feed/baseline |
| sirdata | **VERIFICAR ao chegar** | **?** | spoke (quando ligado) | ⚠️ provável ATRÁS do HEAD (última ação 25/set, v11.14.0). PRECISA alinhar git antes de confiar no sync (ver "Chegada numa máquina" abaixo) |
| socrates | **VERIFICAR ao chegar** | **?** | spoke (quando ligado) | ⚠️ provável ATRÁS do HEAD. Idem sirdata |

> **⚠️ delta-sync (#1345) está OPERACIONAL entre DNBSCDC289↔VPS (09/out).** As máquinas de casa (socrates/sirdata) foram tocadas por último em set (v11.14.0) → NÃO têm a Fase 5 (bootstrap). Antes de confiar no sync nelas, rodar a "Chegada numa máquina" abaixo.

---

## Chegada numa máquina (startup — fazer SEMPRE ao trabalhar numa máquina nova/de casa)

Rotina para garantir que a máquina está na linha viva e o delta-sync + learning-loop funcionam ANTES de confiar na memória sincronizada. Protege contra trabalhar com banco dessincronizado ou código atrás do HEAD.

```bash
cd ~/git/mcp-memory-service
# 1. Alinhar git (github-first — ver skill memory-service-maintainer §sync multi-máquina)
git fetch --all --prune
git rev-list --left-right --count main...github/main   # left=à frente, right=atrás
git merge --ff-only github/main                          # pega trabalho das outras máquinas

# 2. Confirmar features presentes no código (F5 delta-sync + learning-loop)
.venv/bin/python -c "from mcp_memory_service.storage.sync import bootstrap; print('F5 OK')"
.venv/bin/python -c "from mcp_memory_service.extraction import facts; print('fact-extraction OK')"
.venv/bin/python -c "from mcp_memory_service.server.handlers import gaps; print('gap-detection OK')"
#    ImportError em qualquer → a máquina estava atrás; o ff do passo 1 trouxe o código, siga para o passo 3.

# 3. REINSTALAR o venv editable (OBRIGATÓRIO após ff que mudou deps/código novo).
#    NUNCA 'uv sync --frozen' (remove ML). Reinstalar editable sem deps:
VIRTUAL_ENV=.venv uv pip install -e . --no-deps -q

# 4. Restart do serviço (o processo vivo tem o código ANTIGO em memória até reiniciar)
systemctl --user restart memory-service.service   # NOME REAL (não "mcp-memory")
sleep 20 && curl -s --max-time 5 http://localhost:3202/health   # {"status":"ok"} após ONNX subir

# 5. Confirmar delta-sync rodando (cursores avançam contra o hub; schedule 1m)
sqlite3 ~/local-data/mcp/sqlite_vec.db "SELECT peer_id,last_seq_seen FROM sync_cursor; SELECT peer_id,last_seq_pushed FROM push_cursor;"
#    Esperar ~2min e reconferir: os last_seq devem avançar se há tráfego.
```

### Camada learning-loop — envs opt-in (fork-only, default OFF, ligar por máquina quando quiser)
Essas features vêm no código via o ff acima, mas são **opt-in** — só agem se a env estiver no `memory-service.env` (`~/dtp/ai-configs/services/env/memory-service.env`, sincronizado via Insync → já chega nas 3 máquinas). Estado em DNBSCDC289 (09/out):

| Env | O quê | Estado |
|-----|-------|--------|
| `MCP_QUALITY_RECOMPUTE_SCHEDULE=6h` | L4: job recalcula quality (clampado [0,1]) a partir dos sinais | ON |
| `MCP_QUALITY_RECOMPUTE_DRY_RUN=false` | persiste o quality (não só calcula) | false (persiste) |
| `MCP_SEARCH_INJECT_CONTEXT=on` | L3 push: memory_search anexa contexto destilado (gera volume p/ o sinal) | ON |
| `MCP_FACT_EXTRACT_SCHEDULE` | L2: job destila fatos S→P→O (precisa LLM: HARVEST_LLM_PROVIDERS/GROQ_API_KEY) | unset (off) |
| `MCP_GAP_THRESHOLD=0.3` | gap-detection: registra busca com top_score abaixo do limiar | default |

- A env é **versionada/sincronizada** (Insync) → setar numa máquina propaga. Mas o serviço só pega no **restart** (passo 4).
- NÃO ligar `MCP_FACT_EXTRACT_SCHEDULE` sem provider LLM configurado (job vira no-op gracioso, mas sem efeito).
- O ganho EMPÍRICO do learning-loop (MRR vs baseline LoCoMo 0.4140) depende de VOLUME acumular com as flags ON — medir com `scripts/benchmarks/benchmark_locomo.py --mode ablation` após 1-2 semanas.

**Pitfall (lição 09/out):** o serviço systemd chama-se `memory-service.service`, NÃO `mcp-memory`. `systemctl --user show mcp-memory ...` dá VAZIO e induz a concluir "env não setado/serviço desligado". Use `systemctl --user list-units | grep memory` para o nome real ANTES de inspecionar; ou leia o env do processo vivo via `/proc/$(pgrep -f memory-server)/environ`.

---

## Estado da VPS cfnarede.dev (levantado 21/set) — base para o hub

Acesso: `ssh claudio@cfnarede.dev` (chave `~/.ssh/id_ed25519`, exceção à regra HTTPS).

### Serviços e portas (todos localhost 127.0.0.1)
| Porta | Serviço | Notas |
|-------|---------|-------|
| 8000 | **mcp-memory-service** (uv tool, PID vivo) | banco `~/.local/share/mcp-memory/sqlite_vec.db` **182MB**, WAL ativo, atualizado. **v11.3.3 (DESATUALIZADO)** |
| 8003 | translation-one | app -one |
| 8004 | knowledge-one | app -one (tem auth_basic + htpasswd) |
| 8100 | builder-one | app -one |
| 3333 | agent-chat (A3/crew) | auth_basic |
| 5476 | crew dashboard | — |
| 6379 | redis | — |
| 25 | mail | — |

- units systemd --user: `mcp-memory-scotty.service`, `mcp-memory-spock.service` (spock legado/aposentado). Reconciliar qual está ativo na 8000.
- Bancos: `sqlite_vec.db` 182MB (VIVO, Scotty+T'Pol JÁ COMPARTILHAM — pool único já é realidade, valida Opção A da spec), `scotty.db` 1.7MB (legado maio), `spock.db` (legado), backups.
- `hermes-gateway.service` ativo (T'Pol).

### Padrão de segurança nginx (JÁ ESTABELECIDO — molde para o hub)
Site `/etc/nginx/sites-enabled/cfnarede` (443 ssl, server_name cfnarede.dev). Padrão por serviço:
```nginx
location /knowledge-one/ {
    auth_basic "Knowledge One";
    auth_basic_user_file /etc/nginx/.htpasswd-knowledge-one;
    proxy_pass http://127.0.0.1:8004/;
}
```
→ **O hub segue o MESMO molde:** serviço memory em localhost + nginx com `auth_basic`/`.htpasswd` + TLS. NUNCA porta aberta.

---

## Desenho do HUB (a implementar — NÃO exposto ainda)

Requisito do Claudio: serviço de usuário com porta própria + entrada via nginx roteando + auth no banco. Sem porta aberta insegura.

1. **Atualizar VPS** v11.3.3 → v11.13.0 (traz F1 agent_id + tudo). Backup do 182MB antes.
2. **Serviço de usuário** memory-hub em porta própria localhost (ex: 8010, ou reusar 8000 reconciliado). systemd --user.
3. **nginx** `location /memory/` → auth_basic + `.htpasswd-memory` → `proxy_pass http://127.0.0.1:PORTA/`. TLS já existe (443).
4. **Auth no serviço:** verificar se o mcp-memory-service suporta API key nativa (além do auth_basic do nginx) — defesa em profundidade.
5. **agent_id no hub:** T'Pol=tpol, Scotty=scotty via MCP_AGENT_ID nos respectivos serviços/sessões.
6. **Consolidação:** só o hub roda MCP_CONSOLIDATION_ENABLED=true; pontas =false (F3 da spec).
7. **Sync das 3 máquinas Zero:** apontam para https://cfnarede.dev/memory/ (com credencial), topologia estrela.

Spec completa: `SPEC-hub-memoria-centralizada.md` (mesmo diretório).

---

## Referências
- SPEC: `SPEC-hub-memoria-centralizada.md`
- Runbook pilha PRs: `PILHA-PRs-runbook.md`
- Skill: `~/.kiro/skills/memory-service-maintainer/SKILL.md`, `tools-reference` (acesso VPS)
- PR #1278 (F1 agent_id, mergeado 19/set)
