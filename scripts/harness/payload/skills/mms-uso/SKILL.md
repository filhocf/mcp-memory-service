---
name: mms-uso
description: "Como usar o mcp-memory-service (servidor memory-service em :3202) como memória primária no Kiro: quando buscar antes de agir, o que gravar, como etiquetar, e as armadilhas medidas. Complementa a skill mms-custo (orçamento de créditos)."
---

# mms-uso — operar o memory-service no Kiro

O `memory-service` está registrado em `~/.kiro/settings/mcp.json` (`http://localhost:3202/mcp`).
Este documento é a doutrina de uso. O orçamento está em `mms-custo`.

## 1. Antes de agir

| situação | ação |
|---|---|
| "como estamos", "o que decidimos", "onde paramos" | `memory_search` primeiro — **não** responda de memória |
| antes de repetir investigação | busque; se já foi medida, cite o número em vez de refazer |
| antes de propor procedimento (deploy, publicação, migração) | busque tags `procedimento` |
| pergunta conceitual ou código aberto na tela | **não** consulte |

Regra prática: pergunta sobre **estado** → mcp; pergunta sobre **conceito** → conhecimento próprio.

## 2. Como buscar

```
memory_search(query="<token distintivo>", limit=3, max_response_chars=2000)
```

- `limit` ≤ 3. Cinco resultados raramente mudam a decisão e custam 7× mais.
- Busque pelo **token mais distintivo e curto** (sigla, nome de produto, hash). Frase inteira
  raramente existe literalmente.
- `mode="exact"` exige substring **contígua** — duas palavras separadas devolvem vazio mesmo com a
  memória gravada.
- Se vier `Showing 0 of N results`, repita **sem** `max_response_chars`.
- Ausência na busca **não** é ausência no banco. Confirme por SQL antes de afirmar que não existe.

## 3. Store e tag

`store` é partição trancada, não pasta compartilhada: busca **sem** `store` devolve apenas
`default`. O inventário é **por host** e muda — medir antes de citar.

```bash
sqlite3 -readonly ~/local-data/mcp/sqlite_vec.db \
  "select store,count(*) from memories group by 1 order by 2 desc"
```

Para projeto específico, prefira `default` + tag (`<sigla>-sistema`) e `agent_id`.
`store: null` é **rejeitado** pelo schema — omita o campo em vez de mandar null.

## 4. O que gravar

Grave o que **economiza tokens no futuro**:

- decisão com o porquê, datada;
- medição com número e método (não "melhorou", mas "+10pp, IC95 [0,05 · 0,1583]");
- procedimento que funcionou (comandos exatos);
- armadilha: o erro, a causa e a correção.

Não grave: o que já está no repo/commit, o que está no transcript da sessão, opinião sem medição.

Etiquetas úteis: `procedimento`, `medido`, `<projeto>-sistema`, `armadilha`, `decisao`.

## 5. Armadilhas medidas neste host (20/out/2026)

- **`memory_context` não serve para estado de projeto.** Ele ranqueia por vizinhança semântica de
  crença: pedindo "Projeto MIR", o top-1 e top-2 vieram de RER e Core-API. Use SQL por tag.
- **`memory_context` devolve cada item duas vezes** (`items` e `beliefs`) e carrega ~9 KB fixos de
  metadados que o `budget_tokens` não conta.
- **`memory_list` custa ~4.875 tokens por chamada** — inventário se faz por SQL.
- **`memory_store` é barato** (~98 tokens). Gravar não é o problema; **ler** é.
- **Título de `memory_health`/`memory_stats` engana** quando há tombstones: conte vivas por SQL.

## 6. Autoria

`agent_id` deve vir do ambiente/hook do harness, não de invenção na chamada. Se a memória gravada
aparecer sem autor, o problema é o hook — não a tool.
