# Handoff — UIAA (use in any agent) do mms para o Hermes

Status: **ABERTO**. Fica com a sessão da T'Pol dedicada ao orc, quando a atualização
do orc terminar. Este documento é o ponto de partida; nada aqui foi executado.

Data: 18/out/2026 · origem: sessão de bancada (lote 01 de recall)

## O que já existe (verificado, não presumido)

1. **Capacidade em runtime.** O mms responde MCP em `127.0.0.1:3202` (acervo pessoal)
   e `:3205` (triagem). Qualquer cliente MCP consome: Hermes, Kiro, Claude Code.
2. **Integração com o Hermes.** Declarado à mão em `~/.hermes/config.yaml`
   (`mcp_servers.mms.url`). 53 ferramentas `mcp__mms__*` quando a sessão carrega.
3. **Fragilidade conhecida.** Parar o serviço derruba o registro das ferramentas na
   sessão; só volta com relogin do CLI. Observado em 18/out, durante a migração.

## O que falta

| # | item | depende de | critério de pronto |
|---|---|---|---|
| U1 | skill que ensina o uso (busca, stores, modos, pitfalls) | nada | qualquer agente instala e sabe usar sem ler código |
| U2 | robustez da conexão (reconectar sem relogin) | investigação | parar/religar o serviço não exige nova sessão |
| U3 | empacotar repo standalone (`mcp.json` + `skills/`) | U1 | `hermes plugins validate --install-deps` limpo |
| U4 | disclosure de coleta (lê `~/.hermes/state.db`, grava conversa) | U3 | declarado na entrada e no README |
| U5 | entrada no catálogo com SHA de 40 chars + capabilities + scan | U3, U4 | PR aceito no `plugin-catalog/` |

## Regras do catálogo que condicionam o desenho (lidas em `plugin-catalog/README.md`)

- entrada só entra por PR revisado por mantenedor; não há registro self-service;
- SHA exato de 40 caracteres, sem branch nem tag;
- proibido código que se auto-atualiza;
- `capabilities:` declarado tem de bater com o que o plugin registra;
- `hermes plugins validate` roda scan de segurança: `dangerous` bloqueia, `caution` avisa;
- **memory provider não entra no repo do Hermes** (CONTRIBUTING): tem de ser plugin
  standalone publicado pelo catálogo.

## Pergunta em aberto para o Claudio

O alvo do catálogo é publicar o **mms** (projeto do doobidoo, onde somos contribuidores)
ou publicar a **nossa integração/plugin**? A regra de autoria exige ser dono ou
contribuidor principal do repositório submetido.

## O que NÃO fazer

- não usar `get_onboarding_guide` interno como material de ensino: decisão do Claudio é
  ensinar por fora (skill/plugin), porque tool interna é redundante com skill;
- não empacotar antes de U1: o material que ensina é parte do pacote.
