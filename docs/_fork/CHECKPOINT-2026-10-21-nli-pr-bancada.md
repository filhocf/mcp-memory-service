# Checkpoint — 21/out/2026 (sessão T'Pol, host DNBSCDC289)

## Entregas do dia

| item | prova |
|---|---|
| aba/sessão renomeada | `hermes sessions rename` → "mms: retomada 21/out" |
| **4 PRs mergeados no upstream** | #1617 (docs agents index), #1616 (terceiro), #1541 (terceiro), #1627 (distill: JSON+SSE, MCP_HTTP_PORT, Bearer, fail em credencial rejeitada) — merged 17:20Z, sha 66d14e2d |
| limpeza de branches | 65 → 15 locais, 77 → 32 remotas; 12 worktrees removidos; main sincronizada (0 atrás) |
| bancada de latência | `scripts/bancada/{snapshot_db,medir_store}.py` + `docs/_fork/benchmarks/latencia-store-nli-20261021.md` |
| issue upstream | **#1630** — NLI on-store bloqueia a escrita (25–27 s) |
| fix | **PR #1633** aberto (budget 2 s + teto de crenças + WARNING de truncamento + async opt-in) |

## O achado (medido, não deduzido)

`handle_store_memory` → `check_beliefs_on_store` → `for belief in beliefs[:20]: classify(...)` →
`_llm_classify` → `HarvestRewriter._call_llm` → `HARVEST_LLM_PROVIDERS` (deepseek/groq/ollama).
Com 625 crenças elegíveis e ~1,2 s por chamada: **27 s por gravação**. `MCP_NLI_LLM_*` **não** é o
caminho lido — instrumentar aquela URL dá zero chamadas e parece refutar o bug.

Bancada, mesma base e mesma máquina: **0,527 s** (check off) · **27,26 s** (on) · **2,57 s** (budget
2 s) · **0,62 s** (async).

## Configuração da instância

`MCP_NLI_ON_STORE=false` (remendo aplicado) **até o merge** do #1633. Depois: `MCP_NLI_ON_STORE=true`
+ `MCP_NLI_ON_STORE_ASYNC=true`, orçamento default 2 s. Risco conhecido do async: sem semáforo, lote
de gravações gera rajada de tasks — limitar concorrência antes de usar com harvest.

## Erros do dia (para não repetir)

1. **PR #1632 nasceu da `main` do fork** → 130 commits e 100+ arquivos no diff. Fechado; refeito como
   #1633 a partir de `upstream/main` (4 arquivos). O gate é o comando, não a leitura:
   `git diff --stat upstream/main...HEAD` antes de abrir PR.
2. **`Changed tests fail without the change`**: todo teste novo precisa falhar na base. Dois dos
   meus assertavam comportamento inalterado e passavam antes — removidos; restaram 8, e os 8 falham
   no main e passam com o fix.
3. **Release no meio do ciclo:** a v12.2.0 (#1631) saiu depois do rebase e o CI instalou o pacote
   publicado contra o código antigo → 15 falhas que não eram do PR. Sempre rebasear após release.
4. **O instrumento mentiu** com env parcial (faltava `MCP_NLI_BACKEND` do env base): 0,46 s falso.
   Bancada agora registra `nli_effective`/`nli_backend` e aceita `--env-file` múltiplo.

## Fila

1º **#1633** (aguardando Greptile). Depois **#1505** (capability handshake, livre). Fora: #1602 (outra
sessão nossa), #1599/#1560/#1526/#1464/#1459/#1146 (com assignee), #1555 (`claim-pending`).

## Atualização — review do Greptile no #1633 (18:43Z, COMMENTED, 4 achados)

Todos aceitos, um com ressalva registrada no código:

1. **orçamento não cobria o pós-contradição.** Ressalva: o orçamento governa a fase de
   comparação (rede); quarentena iniciada é concluída, porque abortar deixaria metadata/edges
   inconsistentes. Estouro agora loga WARNING explicando.
2. **background sem limite.** `MCP_NLI_BACKGROUND_CONCURRENCY` (default 2), vaga reservada na
   admissão (create_task só roda depois — sem isso duas chamadas seguidas furam o limite),
   excesso descartado com WARNING.
3. **resultado do background sumia.** Agora loga hash + status, inclusive `status="error"`.
4. **stop reason mentia.** Estados: `completed`, `max-beliefs`, `budget`, `timeout`,
   `contradiction`; cap por contagem emite WARNING nomeando `MCP_QUARANTINE_MAX_BELIEFS`.

Prova: **12 testes novos, 12 falham no `main`, 12 passam com o fix**; suíte de consolidação
**469 passed, 1 skipped, 7 xfailed**. 4 threads resolvidas (abertas = 0). Commit `f8eba0fc`.

Nota de leitura: a review do Greptile é `COMMENTED`, **não** `APPROVED` — o PR segue
`REVIEW_REQUIRED` até ele re-revisar o commit novo.

## Rodada 2 do Greptile (18:51Z e 18:53Z) — commit 6c0b8f13

1. **CodeQL "unused global"** em `_background_active`: o contador virou objeto
   `_BackgroundState` (atributo `active`), sem `global` mutável.
2. **"Dropped checks look scheduled"**: `schedule_on_store_checks` agora retorna `bool`; o handler
   mostra "skipped: background capacity is full" quando o trabalho é descartado, em vez de afirmar
   que foi agendado. Aviso no log não chega ao caller — a resposta tinha de dizer a verdade.

12 testes; threads resolvidas (0 abertas). PR #1633 segue `REVIEW_REQUIRED` com auto-merge ON.
Pendência declarada: se o CodeQL voltar a apontar o contador, trocar o objeto por uma fila com
semáforo (`asyncio.Semaphore`) em vez de contador manual.

## #1633 MERGEADO — 2601f088

O fix do NLI on-store entrou no upstream. **Religar a instância (próxima sessão):**

```bash
cd ~/git/mms/mms && git fetch upstream && git merge upstream/main --no-edit && git push github main
# no env por-host: MCP_NLI_ON_STORE=true e MCP_NLI_ON_STORE_ASYNC=true
systemctl --user restart memory-service && curl -s localhost:8000/health
```

Esperado: gravação em ~0,6 s (era 27 s) com a verificação rodando em background; log mostra
`NLI background belief check (<hash>): status=...`. Orçamento default 2 s; concorrência 2.
