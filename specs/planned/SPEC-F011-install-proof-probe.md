# SPEC-F011 — Installation proof probe (write → read → delete)

## Problema

O instalador verifica o **efeito de configuração** (registro MCP, depósitos, bloco
gerenciado) mas não prova o **caminho do dado**: um serviço pode passar no health
check e ainda assim rejeitar escritas (401 em `/mcp`), ter embeddings quebradas
(store OK, search sem resultado) ou banco só-leitura. O gabarito Hermes
(`scripts/hermes/install.py`) não reporta sucesso sem uma sonda obrigatória:
grava, lê de volta e apaga. A RFC (D8, §13.2, §13.4) exige essa prova; o
instalador OpenCode não a faz — buraco apontado pela revisão adversarial de
28/out/2026 (achado 4, veredito **(b): spec nova**, não aditivo à F008 — a sonda
é comportamento de produção do instalador; o lab é a suíte de teste).

## Requisitos

**R1 — Sonda em toda instalação.**
A sonda usa o mesmo transporte que o harness usará (MCP streamable HTTP em
`/mcp`): armazena uma memória sonda, lê de volta por busca e a apaga por hash.

EARS: WHEN an install (not `--dry-run`, not `--uninstall`) runs without
`--skip-health`, THE installer SHALL store a probe (`install probe <token>`,
tag `mms-install-probe`, `agent_id` do instalador), read it back via
`memory_search` (`query` = token, `limit` 1), and delete it by `content_hash`.

**R2 — Token único por execução.**
Um token constante seria rejeitado como duplicata exata na segunda execução, e a
busca encontraria a sonda da rodada anterior em vez de exercitar a escrita atual.

EARS: THE probe SHALL carry a per-run unique token, and THE read-back SHALL be
required to contain THIS run's token.

**R3 — Sucesso condicionado ao round trip.**

EARS: THE installer SHALL NOT report success when the probe store, read-back,
or delete fails; THE exit code SHALL be 1.

**R4 — Delete que falha é ruidoso.**
Uma sonda órfã não pode sumir em silêncio no acervo do usuário.

EARS: IF the probe delete fails, THEN THE installer SHALL print the probe hash
and the reserved tag, and SHALL exit 1.

**R5 — Re-run idempotente também sonda.**
Fecha o §13.2 ("segunda execução produz diff zero **e ainda verifica** health +
round trip").

EARS: WHEN the install is a no-op rerun, THE installer SHALL still run the probe.

**R6 — Fora do manifest.**
O manifest registra estado dos depósitos; a sonda é efêmera.

EARS: THE installer SHALL NOT record the probe in the manifest.

**R7 — Skip explícito.**

EARS: WHERE `--skip-health` is set, THE installer SHALL skip the probe and print
that it did.

## Design

- `run_probe(port, agent_id)` em `installers/core.py`: RPC JSON-RPC sobre `/mcp`
  (`initialize` → `tools/call` ×3), resposta JSON única ou SSE (`data:`),
  `Authorization: Bearer` quando `MCP_API_KEY` existir. Os testes exercitam o
  fio real por HTTP contra um **FakeMMS** (`http.server` em thread), que também
  serve de semente para o lab da F008.
- Fio no `main()`: sonda por harness, após `verify()` e **antes** do manifest e
  do "OK" — sucesso só se reporta com o round trip provado; instalação nova e
  no-op rerun sondam (R5); dry-run, uninstall e rc≠0 não sondam.
- Falha de qualquer passo → `RuntimeError` → mensagem de erro + rc 1.

## Edge cases

| Caso | Comportamento |
|---|---|
| Token constante rejeitado como duplicata | resolvido por R2 (token por rodada) |
| Busca acha a sonda de rodada anterior | R2 exige o token da rodada no texto |
| Health OK mas escrita 401 | a sonda falha → instalação falha (R3) |
| Embeddings quebradas (store OK, search vazia) | R1/R3 pegam ("reachable but not retrieving") |
| DB só-leitura | store falha → R3 |
| Delete falha | R4: hash impresso, rc 1 |
| `--dry-run` | nenhuma sonda (nada é escrito) |

## Testes

`tests/harness/test_install_probe.py` — um **FakeMMS** (`http.server` em thread,
JSON-RPC roteado por tool, contagem de requisições) exercita o fio real por HTTP:
R1–R3 via instalação completa com `--root` isolado; R5 via segunda execução
(no-op + sonda); R4 via resposta de delete com falha; R6 via conteúdo do
manifest; R7 via ausência de requisição a `/mcp` com `--skip-health`.
