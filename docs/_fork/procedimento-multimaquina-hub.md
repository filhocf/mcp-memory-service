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
   git fetch upstream --tags
   git merge upstream/main --no-edit
   ```
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

| Máquina | Versão serviço | F1 agent_id | MCP_AGENT_ID | ONNX-only | Status |
|---------|---------------|-------------|--------------|-----------|--------|
| DNBSCDC289 | v11.14.0 | ✅ F1+F2 | ✅ zero | ✅ | FEITO 28/set: rebase main→github/main (v11.13→11.14, era behind 75); venv recriado `[sqlite,nli]` ONNX-only (⚠️ NÃO usar `uv sync --frozen`: remove ML; reinstall = `VIRTUAL_ENV=.venv uv pip install -e . --no-deps`); serviço reiniciado, health `/health` 200; banco 22.325 mems (limpeza 147 frags harvest). Health mudou `/api/health`→`/health` na 11.14 |
| sirdata | v11.14.0 (código) | ✅ F1+F2 | ✅ zero | ✅ (GTX1050Ti ONNX) | main mergeada 25/set; ⚠️ serviço systemd NÃO reiniciado pós-merge (produção, aguarda OK) |
| socrates | verificar | ? | ❌ ADICIONAR zero | ✅ (CUDA abandonado 21/set) | PENDENTE: **só update LOCAL** (passos 1-7 abaixo) + restore banco (task f5f2a801). **NÃO virar ponta-estrela ainda** (ver nota) |
| VPS (hub) | v11.14.0 | ✅ | tpol/scotty | ✅ | ✅ FEITO 25/set (hub A0-A3): banco autoritativo corrigido (sqlite_vec.db 19.585), consolidação só no hub, sync 401 corrigido |

> **⚠️ ESCOPO PARA AS PONTAS (socrates/sirdata/DNBSCDC289) — leia antes de mexer:**
> Este procedimento cobre o **update LOCAL** do serviço (subir v11.14.0 + F1/F2 + `MCP_AGENT_ID=zero` + restaurar banco via `restore-db-from-sync.sh`/task f5f2a801). Isso deixa o MCP **funcionando localmente** — é o que o socrates precisa AGORA.
> **NÃO conectar a ponta ao hub-estrela ainda.** O passo 7 ("apontar para cfnarede.dev/memory/") e a topologia estrela (SPEC-hub §F3/F4: desligar consolidação nas pontas + reapontar sync) são **trabalho futuro NÃO executado** — o hub existe mas as pontas ainda não foram religadas a ele. Enquanto F4 não roda, cada máquina segue no modelo local (banco local + hot.db via OneDrive). A deriva atual (hosts pararam de subir hot.db ~10 dias) é justamente o que F4 vai eliminar; não é bug do update local.
> **Resumo socrates:** faça passos 1-7 (update local) + restore banco. Pare aí. Ponta-estrela = depois, com OK do Claudio.

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
