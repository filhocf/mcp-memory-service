# Índice de RFCs — mcp-memory-service (fork)

> Índice das specs de trabalho do fork. `implemented/` = entregue/mergeado ou gate executado; `planned/` = draft/futuro.
> Acompanhamento vivo (arcos, estado): `docs/_fork/ARCOS.md` (agente) e `docs/_fork/ESTADO.md` (humano).
> Atualizado: 2026-09-30. Regra: mudou → atualiza.

## implemented/ (entregue ou gate executado)

| RFC | Arco | Nota |
|-----|------|------|
| rfc-quality-model | Rating | #1349 mergeado — arco FECHADO |
| rfc-nli-cascade | Hub/reasoning | #1215 mergeado |
| rfc-harvest-provenance | Ingestão (transversal) | #1243 mergeado |
| rfc-agent-id-multi-agent | Hub | #1278/#1297 mergeados (F1/F2) |
| rfc-harvest-design-extraction | Ingestão C3 | ABSORVIDA → ingestão multi-agente; I0/I0-lang/I1 feitos |
| rfc-harvest-source-identity | Ingestão C1 | ABSORVIDA → ingestão multi-agente (camada 1) |
| rfc-harvest-kiro-sessions | Ingestão C2 | ABSORVIDA → ingestão multi-agente (camada 2) |
| rfc-g0-design-extractor-i2 | Ingestão C3 | gate G0 feito |
| rfc-g0-i1-toolresults-cli-kind | Ingestão C2 | gate G0 feito (I1 implementado) |
| rfc-g0-store-ner | NER | gate |
| rfc-inventario-sessoes-kiro / rfc-recuperacao-sessoes-kiro | Ingestão | levantamento de formatos |
| rfc-fact-extraction / rfc-mm-02-fact-extraction | Extração | trilogia RFC-MM |
| rfc-s2-belief-store / rfc-s6-anti-hallucination / rfc-s8-* / rfc-s9-split-config / rfc-s13-tool-registry-wiring | Infra | specs S* |
| rfc-i11-schema-versioning / rfc-multi-store-domain-ner | Infra/NER | |

## planned/ (draft / futuro)

| RFC | Arco | Nota |
|-----|------|------|
| **rfc-ingestao-multi-agente** (A CRIAR) | Ingestão multi-agente | guarda-chuva das 3 camadas |
| rfc-hub-memoria-centralizada | Hub | SPEC F0-F8 (estrela) |
| rfc-delta-sync | Hub | #1345, colab ducanhnguyen223 |
| rfc-sync-multi-agente | Hub | |
| rfc-memory-portability | Portabilidade | #1364 wiki; 5 camadas |
| rfc-importers | Portabilidade | mem0/letta/zep (#1390) |
| rfc-embedding-quantization / rfc-ranking-upgrades / rfc-query-intent / rfc-working-memory / rfc-persona-tier / rfc-multimodal-memory / rfc-memory-hygiene / rfc-skill-auto-generation / rfc-self-service-memory-intelligence | Diversos (retrieval/qualidade/infra) | backlog |
| rfc-config-audit-2026-07-10 / rfc-autolearn-autodream / rfc-pipeline-harvest-quality | Infra/harvest | |
| rfc-mm-01-feedback-loop / rfc-mm-03-gap-detection | Extração | trilogia RFC-MM |
| rfc-onboarding-discoverable / rfc-server-side-lifecycle / rfc-structural-improvements / rfc-kiro-headless-llm-provider | Diversos | |

## Convenções
- Nome: `rfc-<feat>.md` minúsculo. Ao entregar/implementar: `git mv planned/ implemented/`.
- Uma RFC absorvida por um guarda-chuva: manter o arquivo, marcar "ABSORVIDA → <arco>" no topo e aqui.
