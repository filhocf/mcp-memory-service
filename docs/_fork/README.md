# `docs/_fork/` — INTERNO, FORK-ONLY

**Estes documentos NUNCA entram num PR para o upstream.** São o acompanhamento
interno do fork (filhocf): estado dos arcos, pilha de PRs, roadmap, referência
do pipeline, procedimentos multi-máquina.

- Vivem só na branch `main` do fork.
- Um pre-commit hook recusa staging de `docs/_fork/` em qualquer branch `pr/*`.
- `.gitattributes` marca a pasta como `export-ignore`.

## Índice
- **ARCOS.md** — mapa denso de arcos/sub-arcos → RFC → estado → próximo passo (para o agente carregar rápido).
- **ESTADO.md** — estado legível para o Claudio (árvore ASCII no topo + notas).
- **roadmap.md** — roadmap de épicos.
- **pilha-prs-runbook.md** — estado operacional da pilha de PRs.
- **reference-pipeline.md** — referência do pipeline de memória.
- **reconciliacao-v11.10.0.md**, **procedimento-multimaquina-hub.md**, **experimentos-exploratorios-D.md**.
