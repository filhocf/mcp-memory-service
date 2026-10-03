# Índice de RFCs — mcp-memory-service (fork)

> Specs de trabalho do fork. Classificação VERIFICADA contra o código (30/set): a feature está em `src/`? → `implemented/`; senão → `planned/`. NÃO pelo label do doc (muitos desatualizados).
> Acompanhamento vivo: `docs/_fork/ARCOS.md` (agente) e `docs/_fork/ESTADO.md` (humano).
> Regra: mudou → atualiza. Ao implementar: `git mv planned/ implemented/`.

## implemented/ (23 — feature presente no código, com evidência)

| RFC | Arco | Evidência / nota |
|-----|------|------------------|
| rfc-quality-model | Rating | #1349 mergeado — arco FECHADO |
| rfc-nli-cascade | Reasoning | #1215 mergeado (reasoning/nli.py) |
| rfc-harvest-provenance | Ingestão (transv.) | #1243 mergeado |
| rfc-agent-id-multi-agent | Hub | #1278/#1297 (F1/F2) mergeados |
| rfc-harvest-design-extraction | Ingestão C3 | ABSORVIDA; I0/I0-lang/I1 no código |
| rfc-harvest-source-identity | Ingestão C1 | ABSORVIDA (camada 1) |
| rfc-harvest-kiro-sessions | Ingestão C2 | ABSORVIDA (camada 2); #1378/#1379 mergeados |
| rfc-g0-design-extractor-i2 / rfc-g0-i1-toolresults-cli-kind / rfc-g0-store-ner | Ingestão/NER | gates G0 executados |
| rfc-inventario-sessoes-kiro / rfc-recuperacao-sessoes-kiro | Ingestão | levantamento feito |
| rfc-s2-belief-store | Infra | consolidation/belief_service.py + migration 012 |
| rfc-s6-anti-hallucination | Infra | consolidation/quarantine.py + contradictions.py + nli.py |
| rfc-s8-handler-extraction | Infra | server/handlers/*.py |
| rfc-s8-tool-registry | Infra | tools/registry.py |
| rfc-s9-split-config | Infra | config/ modularizado (15+ módulos) |
| rfc-s13-tool-registry-wiring | Infra | tools/routing.py + server_impl list_tools |
| rfc-i11-schema-versioning | Infra | storage/migration_runner.py + migrations/*.sql |
| rfc-multi-store-domain-ner | NER | reasoning/store_terms.py + ner_patterns/ |
| rfc-sync-multi-agente | Hub | scripts/sync/*.py + web/api/sync.py — OPERACIONAL |
| rfc-pipeline-harvest-quality | Ingestão | harvest/extractor.py (sentence + confidence gate) |
| rfc-config-audit-2026-07-10 | Infra | fixes aplicados (graph_only, store_associations, schema_version) |

## planned/ (23 — design/draft, sem código correspondente)

| RFC | Arco | Nota |
|-----|------|------|
| **rfc-learning-loop** | **Aprendizado (guarda-chuva do PORQUÊ)** | **do colhedor ao aprendiz; L1-L4 (memória→destilação→injeção→feedback); gargalo=sinal de uso. Conecta ingestão (input) + trilogia-MM + self-service + persona-tier (COMOs). Consolida autolearn-rfc (CdIA) + plano self-improvement.** |
| rfc-ingestao-multi-agente v0.1 | Ingestão multi-agente | guarda-chuva das 3 camadas |
| rfc-hub-memoria-centralizada | Hub | SPEC F0-F8 |
| rfc-delta-sync | Hub | #1345 (colab ducanhnguyen223) |
| rfc-memory-portability | Portabilidade | #1364 wiki; 5 camadas |
| rfc-importers | Portabilidade | mem0/letta/zep (#1390) |
| rfc-fact-extraction / rfc-mm-02-fact-extraction | Extração | design puro (grep vazio: fact_extractor, memory_extract_facts) |
| rfc-mm-01-feedback-loop / rfc-mm-03-gap-detection | Extração | trilogia RFC-MM, design |
| rfc-autolearn-autodream | Consolidação | pipeline server-side não existe (skills externas) |
| rfc-embedding-quantization / rfc-ranking-upgrades / rfc-query-intent / rfc-working-memory / rfc-persona-tier / rfc-multimodal-memory / rfc-memory-hygiene / rfc-skill-auto-generation / rfc-self-service-memory-intelligence | Diversos | backlog |
| rfc-onboarding-discoverable / rfc-server-side-lifecycle / rfc-structural-improvements / rfc-kiro-headless-llm-provider | Diversos | design |

## Convenções
- Nome: `rfc-<feat>.md` minúsculo. Implementou → `git mv planned/ implemented/`.
- Absorvida por guarda-chuva: manter arquivo, marcar "ABSORVIDA → <arco>" no topo + aqui.
- Classificação por EVIDÊNCIA de código, não por label do doc.
