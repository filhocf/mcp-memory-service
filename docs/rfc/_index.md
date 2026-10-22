# Indice de RFCs — mcp-memory-service (fork)


> Specs de trabalho do fork. Classificacao VERIFICADA contra o codigo: a feature esta em `src/`? -> `implemented/`; senao -> `planned/`.
> Navegacao por arcos: `docs/rfc/README.md`. Decisoes de arquitetura: `docs/adr/`. Acompanhamento: `docs/_fork/ESTADO.md`.
> Auditoria que moveu estes arquivos: `docs/_fork/AUDITORIA-rfcs-2026-10-21.md`. Regra: mudou -> atualiza.


## implemented/ (30)

| RFC | Arco | Evidencia / nota |
|-----|------|------------------|
| rfc-agent-id-multi-agent | agent-id | RFC: agent_id em todas as memórias + resolução de conflito c |
| rfc-config-audit-2026-07-10 | rating-quality | RFC: Configuration Audit & Optimization — filhocf fork |
| rfc-delta-sync | delta-sync | RFC: Delta Event-Log Sync (malha de memória multi-agente) |
| rfc-fact-extraction | backlog-ideias | Spec: Fact Extraction de Documentos (GAP H) |
| rfc-harvest-provenance | harvest | RFC: Harvest Provenance & Safe Re-harvest |
| rfc-hybrid-http-secondary | hub-sync-legado | RFC: hybrid self-hosted secondary (http) — pluggable sync se |
| rfc-i11-schema-versioning | rating-quality | Spec: #11 Schema Versioning + Migration Registry |
| rfc-inventario-sessoes-kiro | harvest | Inventário Completo de Sessões Kiro + Estratégia de Resgate  |
| rfc-multi-store-domain-ner | multi-store | Spec: Multi-store Domain NER (Entity Linking por Domínio) |
| rfc-multi-store-partition | multi-store | RFC: Multi-Store Partition |
| rfc-nli-cascade | rating-quality | RFC — NLI Cascade Backend (LLM-based contradiction detection |
| rfc-pipeline-harvest-quality | harvest | Pipeline: Harvest Pipeline Quality Fix |
| rfc-quality-model | rating-quality | RFC: Quality Model — computed score vs human rating |
| rfc-recuperacao-sessoes-kiro | harvest | Recuperação de Sessões Kiro — Estado da Arte + Plano de Colh |
| rfc-s6-anti-hallucination | rating-quality | Spec: §6 Anti-Hallucination (Belief Quarantine + LLM NLI) |
| spec-agent-id-streamable | hermes/UIAA | spec-agent-id-streamable — autoria por header no transporte  |
| spec-d3-mms-doctor | hermes/UIAA | SPEC — D3: `mms-doctor` — diagnóstico, degradação e prova po |
| spec-d7-instalador | hermes/UIAA | SPEC — D7: instalador de primeira classe (um comando, idempo |
| spec-d8-porta-transporte | hermes/UIAA | SPEC — D8: porta e transporte declarados num único lugar |
| spec-delta-sync-1522-fixes | delta-sync | SPEC — delta-sync audit fixes (#1522): tombstone, bootstrap  |
| spec-delta-sync-fase1 | delta-sync | SPEC — Delta-Sync Fase 1: event-log local (sqlite_vec, sem t |
| spec-delta-sync-fase2 | delta-sync | SPEC — Delta-Sync Fase 2: ordenação determinística (HLC + re |
| spec-delta-sync-fase3 | delta-sync | SPEC — Delta-Sync Fase 3: consistência de embedding (§8.3) |
| spec-delta-sync-fase4a | delta-sync | SPEC — Delta-Sync Fase 4a: transporte PULL (feed + apply + c |
| spec-delta-sync-fase4b | delta-sync | SPEC — Delta-Sync Fase 4b: orquestração do PULL (sync_from_p |
| spec-delta-sync-fase4c | delta-sync | SPEC — delta-sync Phase 4c: outbound push (spoke → hub) |
| spec-delta-sync-fase4d | delta-sync | SPEC — delta-sync Phase 4d: scheduled sync cycle (pull + pus |
| spec-delta-sync-fase5 | delta-sync | SPEC — delta-sync Phase 5: bootstrap + event version negotia |
| spec-fase0-kiro-yaml-triagem | harvest | SPEC — Fase 0: perfil Kiro em YAML + triagem de sessão |
| spec-store-visibility | backlog-ideias | spec-store-visibility — busca padrão enxerga todos os stores |

## planned/ (39)

| RFC | Arco | Evidencia / nota |
|-----|------|------------------|
| rfc-autolearn-autodream | learning-loop | Plano: Tornar Autolearn e Autodream Produtivos |
| rfc-belief-synthesis | belief | RFC: Belief Synthesis — derive_beliefs must distill, not cop |
| rfc-dreaming-loop-inc1-distill-specific | dreaming | RFC: Dreaming-Loop Inc 1 — Distill the recent SPECIFIC (make |
| rfc-dreaming-loop | dreaming | RFC: Dreaming-Loop — consolidação, grafo heterogêneo e naveg |
| rfc-embedding-quantization | backlog-ideias | RFC: Quantização de Embeddings (int8 / binary vectors) |
| rfc-harvest-sessoes | harvest | RFC — Arco Harvest de Sessões (learning de colheitas) |
| rfc-hermes-first-class | hermes/UIAA | RFC: Hermes como cliente de primeira classe do memory-servic |
| rfc-importers | portabilidade | RFC: Memory Importers (portas de entrada + vetor de adoção) |
| rfc-ingestao-multi-agente | ingestao-multi | RFC: Ingestão multi-agente (arquitetura guarda-chuva do harv |
| rfc-inter-agent-inbox | inbox-inter-agente | RFC: Inter-agent inbox — reliable delivery over a server-sid |
| rfc-kiro-headless-llm-provider | backlog-ideias | Spec: Kiro CLI Headless como LLM Provider |
| rfc-learning-loop-a-rerank | learning-loop | RFC: Learning-Loop Frente A — Re-rank for Context Precision  |
| rfc-learning-loop-graph-proximity | learning-loop | RFC: Learning-Loop — Graph-Proximity signal in context injec |
| rfc-learning-loop | learning-loop | RFC: Learning Loop — do colhedor ao aprendiz (closed-loop ag |
| rfc-mcp-hostname-stamping | backlog-ideias | RFC: hostname automático no store MCP (server-side host stam |
| rfc-memory-hygiene | backlog-ideias | RFC: Memory Hygiene — Noise Audit & Safe Cleanup |
| rfc-mm-01-feedback-loop | learning-loop | RFC-MM-01: Feedback Loop Automático (Server-Side, Zero Disci |
| rfc-mm-02-fact-extraction | learning-loop | RFC-MM-02: Fact Extraction (Batch, Incremental) |
| rfc-mm-03-gap-detection | learning-loop | RFC-MM-03: Gap Detection Proativa |
| rfc-multimodal-memory | backlog-ideias | RFC: Multimodal Memory (imagem/vídeo/áudio → texto recalláve |
| rfc-onboarding-discoverable | backlog-ideias | RFC: Onboarding Discovery Protocol — Agent-Native MCP Usage  |
| rfc-persona-tier | backlog-ideias | RFC: Persona Tier (identidade portável auto-gerada) |
| rfc-query-intent | backlog-ideias | RFC: Query Intent Classification (ajuste de pesos por intenç |
| rfc-ranking-upgrades | backlog-ideias | RFC: Ranking — Weibull Decay + Polyphonic Recall |
| rfc-s2-belief-store | belief | Spec: §2 Belief Store (Incremental Approach) |
| rfc-server-side-lifecycle | learning-loop | RFC: Server-Side Lifecycle — Mover autolearn/autodream/harve |
| rfc-skill-auto-generation | backlog-ideias | RFC: Skill Auto-Generation Pipeline |
| rfc-working-memory | backlog-ideias | RFC: Working Memory Layer (contexto quente auto-gerenciado) |
| spec-belief-quality-camada1 | belief | SPEC: Belief quality — Camada 1 (higiene de belief: eliminar |
| spec-dreaming-inc2-consolidate-theme | dreaming | SPEC — Dreaming INC 2: consolidação por tema (`memory_consol |
| spec-dreaming-inc3-heterogeneous-graph | dreaming | SPEC — Dreaming INC 3: grafo heterogêneo tipado |
| spec-dreaming-inc4-associations-injection | dreaming | SPEC — Dreaming INC 4: associações→injeção (navegação por te |
| spec-dreaming-inc5-hebbian-reweight | dreaming | SPEC — Dreaming INC 5: loop sono→acordado (reweighting Hebbi |
| spec-dreaming-inc6-importance-trigger | dreaming | SPEC — Dreaming INC 6: gatilho por importância por tema (loo |
| spec-dreaming-inc7-explore-reflection | dreaming | SPEC — Dreaming INC 7 (opcional): memory_explore unificado + |
| spec-hermes-state-db-importer | hermes/UIAA | SPEC — Importador do state.db do Hermes Agent (bring your me |
| spec-learning-loop-b-negative-signal | learning-loop | SPEC-B: Negative use-signal — demote injected-but-unused bel |
| spec-learning-loop-c-freshness | learning-loop | SPEC-C: Freshness — the newest version wins in injection |
| spec-learning-loop-e-eval-mrr | learning-loop | SPEC-E: Adversarial eval set + continuous MRR |

## archive/ (20) — absorvidas, superseded ou artefato de gate (historico)

| RFC | Arco | Motivo |
|-----|------|--------|
| rfc-g0-design-extractor-i2 | gates-G0 | artefato de gate |
| rfc-g0-i1-toolresults-cli-kind | gates-G0 | artefato de gate |
| rfc-g0-store-ner | gates-G0 | artefato de gate |
| rfc-harvest-design-extraction | harvest | absorvida pela ingestao multi-agente (C3) |
| rfc-harvest-kiro-sessions | harvest | absorvida pela ingestao multi-agente (C2) |
| rfc-harvest-source-identity | harvest | absorvida pela ingestao multi-agente (C1) |
| rfc-hub-memoria-centralizada | hub-sync-legado | superseded por rfc-delta-sync |
| rfc-learning-loop-hermes-ideas | learning-loop | absorvida pelas specs do learning loop |
| rfc-memory-portability-agent-hermes | portabilidade | anexo de sistema de terceiros (wiki no upstream) |
| rfc-memory-portability-agent-kiro | portabilidade | anexo de sistema de terceiros |
| rfc-memory-portability-memory-mem0 | portabilidade | anexo de sistema de terceiros |
| rfc-memory-portability-memory-mnemosyne | portabilidade | anexo de sistema de terceiros |
| rfc-memory-portability | portabilidade | absorvida pela portabilidade 5 camadas (#1364) |
| rfc-s13-tool-registry-wiring | estrutura-refactor | refactor entregue |
| rfc-s8-handler-extraction | estrutura-refactor | refactor entregue |
| rfc-s8-tool-registry | estrutura-refactor | refactor entregue |
| rfc-s9-split-config | estrutura-refactor | refactor entregue |
| rfc-self-service-memory-intelligence | ingestao-multi | absorvida |
| rfc-structural-improvements | estrutura-refactor | guarda-chuva generico, sem criterio nem dono |
| rfc-sync-multi-agente | hub-sync-legado | superseded por rfc-delta-sync (ADR-0002) |
