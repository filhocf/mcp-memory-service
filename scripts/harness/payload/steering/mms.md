# Memory service (mms) — uso e custo

<!-- mms:start -->
Você tem um servidor `memory-service` (mcp-memory-service) em `http://localhost:3202/mcp`.
Ele é sua memória de longo prazo: o acervo tem o histórico de decisões, medições e procedimentos
que **não cabem no contexto** desta sessão.

## Regra de ouro: buscar, não injetar

O serviço é um cliente pagante do seu contexto — cada chamada devolve texto que entra na janela e
**consome créditos do prompt**. Medido neste host (20/out/2026):

| operação | custo por chamada |
|---|---|
| `memory_search` limit=3 + `max_response_chars=2000` | ~500 tokens |
| `memory_search` default (limit=5) | ~3.450 tokens |
| `memory_context` (default) | ~10.650 tokens |
| `memory_list` | ~4.875 tokens |

**Use `memory_search` com `limit` ≤ 3 e `max_response_chars` ≤ 2000.** Se a resposta vier
`Showing 0 of N results`, repita **sem** `max_response_chars` — capa apertada zera resultado.

## Quando consultar antes de agir

- pergunta sobre **estado, pendência, decisão anterior ou "o que fizemos"** → busque no mms antes
  de responder;
- antes de repetir uma investigação que provavelmente já foi feita;
- antes de propor um procedimento (deploy, publicação, migração).

**Não** consulte para: pergunta conceitual, código que está aberto na tela, ou algo que o usuário
acabou de dizer.

## O que gravar

Grave **decisão, medição com número, procedimento e armadilha** — o que economiza tokens no futuro.
Não grave o que já está no repositório ou no transcript.

- `memory_store` com `tags` específicas (`procedimento`, `<projeto>-sistema`, `medido`);
- `agent_id` é carimbado pelo hook/ambiente — não invente identidade na chamada.

## Estado de projeto: SQL, não `memory_context`

`memory_context` ranqueia por vizinhança semântica de crença, não por escopo — já trouxe crença de
outro projeto como top-1. Para estado de um projeto nomeado:

```bash
sqlite3 -readonly ~/local-data/mcp/sqlite_vec.db \
  "select store,count(*) from memories where content like '%<SIGLA>%' group by 1"
```

## Custo do próprio hook

Execução de hook também consome créditos. Este arquivo é lido a cada prompt: mantenha-o curto.
<!-- mms:end -->
