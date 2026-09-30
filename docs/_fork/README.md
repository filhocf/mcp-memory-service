# `docs/_fork/` — INTERNO, FORK-ONLY

**Estes documentos NUNCA entram num PR para o upstream.** São o acompanhamento
interno do fork (filhocf): estado dos arcos, pilha de PRs, roadmap, referência
do pipeline, procedimentos multi-máquina.

- Vivem só na branch `main` do fork.
- Um pre-commit hook recusa staging de `docs/_fork/` em qualquer branch `pr/*`.
- `.gitattributes` marca a pasta como `export-ignore`.

> **Fonte única por informação (evita duplicata):** estado dos arcos → `ARCOS.md`(agente)+`ESTADO.md`(humano, gêmeos); backlog → `roadmap.md`; processo de PR → `pilha-prs-runbook.md`; arquitetura → `reference-pipeline.md`. Mexeu → atualiza SÓ o dono da informação.

## Índice
- **ARCOS.md** — mapa denso de arcos/sub-arcos → RFC → estado → próximo passo (para o agente carregar rápido).
- **ESTADO.md** — estado legível para o Claudio (árvore ASCII no topo + notas).
- **roadmap.md** — BACKLOG de épicos futuros (esforço×impacto+ordem). Não duplica estado.
- **pilha-prs-runbook.md** — PROCESSO de transporte fork→upstream (mecânica+disciplina). Não duplica estado.
- **reference-pipeline.md** — referência do pipeline de memória.
- **reconciliacao-v11.10.0.md**, **procedimento-multimaquina-hub.md**, **experimentos-exploratorios-D.md**.
