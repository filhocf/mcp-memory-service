# RFC: OpenCode como cliente de primeira classe do memory-service

**Data:** 2026-10-28
**Autor:** Claudio + T'Pol (Manager + Client do mms)
**Status:** DRAFT v0.1 — proposta consolidada; decisões D1, D5 e D9 fechadas; D2–D4, D6–D8 especificadas na branch `feat/opencode-installer`
**RFC-irmã:** `rfc-hermes-first-class.md` (mesmo arco de portabilidade) — onde o Hermes tinha
que PROVAR que prefere este serviço à própria memória nativa, o OpenCode é o caso oposto:
**não tem memória nativa durável**, então a barreira não é convivência, é instalação e autoria.
**Relacionadas:** `rfc-agent-id-multi-agent` (autoria), `rfc-onboarding-discoverable` (descoberta),
`agents/README.md` (matriz das 5 camadas — linha OpenCode), `opencode/README.md` (plugin).
**Código existente:** `opencode/memory-plugin.js` na `main` (plugin V1/V2, inbox, TUI) e a
branch `feat/opencode-installer` (instalador + specs F001–F010) — ver §12.

---

## 1. Problema

A linha OpenCode na matriz (`agents/README.md`) marca camadas 1–3 ✅ e camadas 4–5 🔴.
Medido em 22–23/out (sessão de 360 mensagens) e 28/out, o que separa "conectado" de
"primeira classe":

- **Instalação manual**: nada instala o MCP nem o plugin — quem chega ao OpenCode edita
  `opencode.jsonc` à mão, sem idempotência, sem `--uninstall`, sem prova pós-escrita.
- **Shape de config ambíguo**: o OpenCode 2.x aceita o shape V1 (`mcp.<nome>`) por
  compatibilidade, mas o correto é V2 (`mcp.servers.<nome>`). O instalador de referência
  (`codebase-memory-mcp`) ainda grava V1 — não é gabarito para shape.
- **Autoria quebrada no build instalado**: o header `X-Agent-ID` NÃO é lido pelo
  memory-service v12.0.0 instalado (venv) — só pelo código-fonte atual
  (`src/mcp_memory_service/web/api/mcp.py`). Toda escrita do OpenCode cai no
  `MCP_AGENT_ID` do processo (aqui: `zero`). Medido em 19/out: antes do wrapper,
  `agent_id=zero`; depois, `agent_id=arch`.
- **Sem doutrina de uso (camada 5)**: nenhum skill ensina o agente OpenCode a buscar antes
  de responder, quando salvar, como taggear.
- **Trabalho feito mas não aterrissado**: 9 commits + specs F001–F010 moram na branch
  `feat/opencode-installer` (não pushada) com refactor não commitado — a sessão morreu em
  limite de provider, não por decisão técnica.

O objetivo desta RFC é fechar essa distância com decisões explícitas e critérios EARS
verificáveis, seguindo o modelo que funcionou para o Hermes (D1–D8 lá, D1–D10 aqui).

---

## 2. D1 — Modelo de convivência: FECHADO (mms é A memória)

O OpenCode **não tem memória nativa durável** comparável ao `MEMORY.md` do Hermes.
A sessão é efêmera; o que persiste entre sessões vem de fora.

**Decisão:** o memory-service é a fonte primária e única de memória entre sessões.
Não há conflito de preferência (camada 4) a resolver — a matriz passa a registrar a
camada 4 como ✅ "por arquitetura: não há store nativo que compita".

| Horizonte | Fonte | Mecanismo |
|---|---|---|
| Dentro da sessão | histórico da própria sessão | nativo do OpenCode |
| Entre sessões | memory-service via MCP + plugin | injeção no start, auto-capture, resumo no fim |

Consequência: o modo híbrido do Hermes NÃO se aplica aqui. O plugin com injeção e
captura ativas é o estado correto, não opcional.

---

## 3. D2 — Registro MCP em shape V2 — ESPECIFICADO (F001)

**Fatos medidos:**

- `opencode mcp add` escreve no config global resolvido por `HOME`/`XDG` — **não aceita
  `--root`** para sandbox de laboratório.
- **Não existe `opencode mcp remove`.** O undo é editar o arquivo.
- O config é JSONC (comentários + vírgulas à direita); um editor ingênuo de JSON corrompe.
- Config de projeto com precedência superior substitui o objeto inteiro do servidor com
  o mesmo nome (sem merge de campo).

**Decisão:** editor JSONC próprio (tokenizer com strings/comentários/vírgulas à direita,
escrita atômica, diff semântico), único caminho de código para install/uninstall/reinstall.
Shape alvo: `mcp.servers.<nome>` com `type: remote`, `url`, `oauth: false`.

EARS:

- THE installer SHALL registrar o servidor sob `mcp.servers.<nome>` em qualquer arquivo
  `opencode.json(c)` alvo, preservando comentários e formatação do restante do arquivo.
- THE installer SHALL executar com escopo isolado (`--root` de sandbox) sem tocar no
  config real do usuário.
- THE installer SHALL remover o registro na remoção (uninstall) sem corromper o JSONC.
- THE installer SHALL tratar `disabled: true` (não `enabled`) como o campo de estado.

---

## 4. D3 — Depósito do plugin — ESPECIFICADO (F002)

O plugin `opencode/memory-plugin.js` (dual-shape V1/V2: injeção no start, auto-capture
pelo hook `context`, resumo via `session.idle`, `/memory` registrado em `setup`,
inbox entre agentes, status file) é depositado como pacote local e carregado pelo
array `plugins` do config.

EARS:

- THE installer SHALL depositar o plugin em caminho XDG resolvido (`~/.config/opencode/plugins/`)
  ou referenciá-lo no array `plugins` com caminho absoluto, e registrar o que criou no manifesto.
- THE installer SHALL validar que o plugin carrega (prova de efeito: status file criado
  ou evento de sessão) antes de reportar sucesso.
- THE uninstall SHALL remover apenas os caminhos do manifesto.

---

## 5. D4 — Autoria por argumento explícito, não por header — ESPECIFICADO (F005)

**Fato medido (19/out):** o header `X-Agent-ID` funciona no transporte streamable-http
apenas no código-fonte atual; o build instalado (v12.0.0 no venv) não o implementa.
Correção server-side já mergeada no upstream (#1598) — mas "mergeado" não é "em produção"
(regra da RFC-irmã).

**Decisão:** a autoria no OpenCode NÃO depende de header. O plugin envolve as tools de
escrita (`memory_store`, `memory_store_session`, `mistake_note_add`) via transform e injeta
o argumento `agent_id` explícito (precedência máxima no serviço). Correlação de sessão usa
o `_meta["ai.opencode/sessionID"]` que o OpenCode já envia em toda tool call (request
metadata, não schema) — o serviço pode registrá-la como metadado de origem.

> **Emenda (28/out/2026, revisão adversarial):** a decisão D4 segue válida como alvo,
> mas o transform NÃO foi implementado — o payload depositado hoje só registra o header
> (inerte no build 12.3.1). A prova de efeito de autoria (§13.4) depende da sonda
> (SPEC-F011) e do transform. D4 permanece aberta até o transform existir; a F005
> carrega a nota de versão.

EARS:

- THE plugin SHALL injetar `agent_id` explícito em toda escrita de memória vinda do OpenCode.
- THE plugin SHALL NOT depender do header `X-Agent-ID` nem do `MCP_AGENT_ID` do processo.
- THE service SHALL registrar `_meta["ai.opencode/sessionID"]` como metadado quando presente.
- THE fallback SHALL ser documentado: sem argumento e sem header, a escrita cai no env de
  forma previsível, nunca por acidente.

---

## 6. D5 — Bloco gerenciado no `AGENTS.md` global — ESPECIFICADO (F003)

Instruções persistentes do harness vivem em `~/.config/opencode/AGENTS.md`.
**Decisão:** bloco delimitado por marcadores `<!-- mms:start -->` / `<!-- mms:end -->`,
idempotente, atualizável e removível sem tocar o resto do arquivo.

EARS:

- THE installer SHALL inserir/atualizar o bloco gerenciado preservando o conteúdo externo.
- THE installer SHALL ser idempotente: segunda execução produz diff zero no arquivo.
- THE uninstall SHALL remover exatamente o bloco e nada mais.

---

## 7. D6 — Instructions no `initialize` MCP — ESPECIFICADO (F006)

O OpenCode renderiza o campo `instructions` do handshake MCP como bloco
`<mcp_instructions>` no system prompt (comportamento nativo, verificado na doc V2).

**Decisão:** o mms anuncia as instruções de uso no `initialize` — quando buscar antes de
responder, como taggear, onde as tools vivem. Implementado na branch (`447ad26a`).

EARS:

- THE service SHALL anunciar instruções no campo `instructions` do `initialize`.
- THE instructions SHALL declarar o modo Code Mode: as tools são acessadas via
  `tools.mms.*` dentro do runtime de execução de código, descobertas por `search()`.
- THE OpenCode SHALL omitir as instruções se todas as tools do servidor estiverem negadas
  (comportamento nativo documentado) — o skill deve cobrir o caso de permissão restrita.

---

## 8. D7 — Skill de uso `mms-uso` — ESPECIFICADO (F004)

Camada 5: skill neutra de harness ensinando a doutrina (buscar antes de agir, tags,
quando salvar, como avaliar). Deposita em `~/.config/opencode/skills/mms-uso/SKILL.md`.
Já existe na branch (`e8519d93`), com payload compartilhado entre harnesses.

EARS:

- THE installer SHALL depositar a skill com frontmatter válido e descrição que provoque
  o gatilho correto.
- THE skill SHALL cobrir: busca prévia obrigatória, convenção de tags deste acervo,
  armadilha de store/partição (busca sem `store` vê só o default), e o regime de autoria.

---

## 9. D8 — Instalador de primeira classe — ESPECIFICADO (F007/F008)

Artefato: `memory install opencode` (CLI do pacote), módulos em
`src/mcp_memory_service/installers/` (refactor em curso na branch — ver §12).

Ordem de execução (checklist, gabarito `scripts/hermes/install.py`):

1. Resolver alvo (`--root` de sandbox ou config real por XDG).
2. Detectar OpenCode (binário, versão) e serviço (`/health`) **antes** de escrever.
3. Registrar MCP em shape V2 (editor JSONC de D2).
4. Depositar plugin (D3), bloco `AGENTS.md` (D5) e skill (D7).
5. Prova de round trip: gravar sonda, ler de volta, remover.
6. Manifesto gravando **estado** (não comandos de undo) para remoção cirúrgica.
7. Verificação pós-escrita com busca real de token conhecido.

**Lição incorporada (incidente 22/out):** o `codebase-memory-mcp uninstall` sem terminal
interpretou invocação sem flags como confirmação e desinstalou o produto. Portanto:

EARS:

- THE uninstall SHALL executar apenas com flag explícita e SHALL NOT inferir confirmação
  da ausência de TTY.
- THE installer SHALL abortar antes de escrever qualquer arquivo se o serviço não responder
  ao health check.
- THE installer SHALL ser idempotente: segunda execução em máquina configurada produz
  diff zero e ainda verifica health + round trip.
- THE installer SHALL reportar sucesso apenas se a sonda gravada for lida de volta.

Validação: laboratório isolado (F008) — `HERMES_HOME`-análogo: `XDG_CONFIG_HOME` de sandbox
+ porta efêmera + banco novo; uma execução deixa o agente respondendo busca real.

---

## 10. D9 — Code Mode: manter o padrão — FECHADO

O OpenCode expõe tools MCP por padrão via Code Mode (`codemode: true`): o modelo chama
`tools.mms.memory_search(...)` em runtime de código, com catálogo descoberto por `search()`.
**Decisão:** manter o default. Não expor as ~30 tools como nativas — isso incharia o
system prompt e perderia composição (múltiplas calls por bloco). As instruções do D6
devem ensinar o padrão de descoberta.

---

## 11. D10 — Porta e transporte

Fato: o default do projeto é **8000** (`MCP_HTTP_PORT`). Nesta máquina o serviço responde
em `http://127.0.0.1:8000/mcp` (health verificado em 28/out). O Hermes usa 3202 por
herança do SSE legado — decisão documentada na RFC-irmã.

**Decisão:** OpenCode nasce em 8000 (alinhado ao default), porta declarada em um lugar
(env por host), lida pelo instalador e passada via `--port`. Sem migração, sem salada.

---

## 12. Estado do código (relatório do Manager, 28/out — emendado pós-E2E e pós-revisão)

| Item | Estado |
|---|---|
| Branch `feat/opencode-installer` (worktree `~/git/mms/opencode-first-class`, registrado em `docs/_fork/worktrees.md` via `d620a615`) | 13 commits à frente, não pushada |
| Commits do arco | `37c4aba5` registro JSONC V2 · `fe1a103d` depósito do plugin · `b2f2b5e1` stamp de identidade · `e759923c` bloco `AGENTS.md` · `e8519d93` skill `mms-uso` · `447ad26a` instructions no initialize · `5f7725c5` docs first-class · `2a5947c5` instalador no pacote + CLI `memory install` (F007 GREEN) · `742706fc` fallback `/api/health` · `b36a5667` README first-class |
| Specs F001–F010 | `specs/planned/` na branch — revisão adversarial 28/out: 7 COVERED, F005/F010 divergências emendadas, F008/F009 com lacunas em tratamento |
| E2E clean-room (28/out) | **PASSOU**: wheel 12.3.1 + venv limpo + serviço `memory launch` :3999 (DB isolado, `MCP_ALLOW_ANONYMOUS_ACCESS=true`) + XDG sandbox — install 6 ações, idempotência diff zero, `opencode mcp list` conectado, round trip store/search/delete, uninstall cirúrgico |
| Pendências de §13 | sonda write→read (F011), docs de integração (F009 R4/R5/R7), lab automatizado (F008 — decisão pendente: implementar vs. evidência manual), prova de sessão nova (§13.5) |
| Na `main` | `opencode/` (plugin V1/V2 + README + tests), `agents/README.md` (matriz), `scripts/hermes/install.py` (gabarito) |
| Sessão de origem | `ses_e9ac45a56ffeDAIyVQJR4DCnf6` — terminou em limite de provider (não por decisão técnica) |

Nota de conformidade: este repositório é um fork — a RFC em `docs/rfc/` É a spec de
trabalho (AGENTS.md). As SPEC-F### da branch consolidam aqui; o código segue o fluxo de
PR do runbook quando aterrissar: `pr/<feat>` a partir de `upstream/main` limpo, sem
commits fork-only.

Parte upstreamável (após G5): `agents/opencode/` com `install.py` + testes + README
(decisão da discussão upstream #1614 — harness que instala ganha diretório), atualização
da linha OpenCode na matriz e do `opencode/README.md`.

---

## 13. Critérios de aceitação do arco

1. Em máquina limpa (XDG de sandbox + serviço novo), **uma** execução deixa o OpenCode
   respondendo busca real de memória — MCP conectado, plugin carregado, skill presente.
2. Segunda execução produz **diff zero** e ainda verifica health + round trip.
3. `--uninstall` remove exatamente o que o manifesto lista; config JSONC permanece válido
   e comentado.
4. Toda escrita de memória vinda do OpenCode carrega o `agent_id` correto — provado por
   sonda, sem depender de header.
5. Sessão nova do OpenCode injeta contexto relevante do acervo no start (prova de efeito).
6. Bloco gerenciado no `AGENTS.md` idempotente e removível com diff cirúrgico.
7. `memory install opencode` funciona com `--root` isolado sem tocar no config real.
8. Linha OpenCode na matriz passa a: 1 ✅ · 2 ✅ instalador · 3 ✅ · 4 ✅ (por arquitetura) · 5 ✅ skill.

## 14. Fora de escopo

- Alterar o regime de convivência do Hermes (RFC-irmã rege lá).
- Porta 3202 vs 8000 para o Hermes (D8 lá decide; aqui é 8000 e ponto).
- TUI/GUI parts do plugin (sidebar widget já existe; empacotamento vem depois do core).
- Autenticação OAuth no mms (serviço local, sem OAuth; `oauth: false` explícito).
- Providers de busca externa, delta-sync, arcos de learning-loop (pertencem às suas RFCs).

## 15. Próximos passos (ordem do método — emendada 28/out)

1. ~~Fechar o refactor não commitado~~ → **FEITO** (`2a5947c5`, F007 GREEN, 154 testes).
2. ~~E2E em ambiente limpo~~ → **FEITO e PASSOU** (28/out; bug do health fallback fixado em `742706fc`).
3. ~~Revisão adversarial por spec~~ → **FEITA** (28/out): 7 COVERED; sonda → F011; emendas aplicadas.
4. Fila em execução: emendas de specs/RFC → **SPEC-F011 (sonda write→read) RED→GREEN** → F009 (README raiz, `docs/integrations.md`, changelog, teste de docs) → decisão sobre o lab F008 (automatizar vs. evidência manual + follow-up).
5. Atualizar esta RFC com as evidências; mover para `implemented/` quando §13 fechar (falta: §13.2 round trip no re-run — F011, §13.4 autoria — F011 + transform D4, §13.5 sessão nova — fora do escopo do instalador, declarar no §14).
6. Só então abrir o fluxo upstream (`pr/<feat>` — docs + `agents/opencode/`); monitorar o PR2 de #1614 (mover `codex/`+`opencode/` para `agents/`) para rebasear paths.
