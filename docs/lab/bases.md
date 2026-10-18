# Três bases, três papéis

| base | arquivo | modelo | idioma | ciclo | porta |
|---|---|---|---|---|---|
| pessoal | `~/local-data/mcp/sqlite_vec.db` | paraphrase-multilingual | PT | vivo | 3202 |
| bancada | `~/local-data/mcp/bench/bench-upstream.db` | all-MiniLM-L6-v2 | EN | congelado (SHA) | — |
| triagem | `~/local-data/mcp/bench/triagem-upstream.db` | all-MiniLM-L6-v2 | EN | vivo | 3205 |

Regra dura: um modelo de embedding por arquivo. Vetores de modelos diferentes não
convivem na mesma base — foi o que partiu o acervo pessoal em três espaços e custou
32,5 p.p. de recall por documento.

- Pessoal: uso diário e material de trabalho em PT-BR (store `mms`).
- Bancada: mede o produto. Régua `eval/recall_cases_bench_v1.json` (100 casos EN),
  baseline documento @10 = 0,81.
- Triagem: histórico do upstream, consultado por identificador (FTS/exact) e por
  tema (semântico). Importador: `scripts/ingest_github_triage.py`, idempotente por
  `sha256("gh:{repo}:{kind}:{n}")` + `gh_updated_at`.

Instância de triagem: `memory-service-triagem.service` + `deploy/triagem.env.example`.
Pitfall: no systemd `EnvironmentFile` vence `Environment=`; overrides precisam ser
arquivo próprio carregado por último.

## Pitfall: instância derivada não herda rotina do env compartilhado

A instância de triagem carrega `memory-service.env`, que traz
`MCP_CONSOLIDATION_ENABLED=true` e as agendas diária/semanal/mensal. Resultado
observado: a base de triagem recebeu 23.921 memórias do acervo pessoal (store
`default`) intercaladas com as do GitHub, contaminando qualquer medição.

`triagem.env` agora desliga consolidação, harvest e as três agendas. Regra: base
derivada declara explicitamente tudo que NÃO quer do env compartilhado.
