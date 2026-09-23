# Auditoria — Macro-Mapa (visão de águia) do mcp-memory-service

Projeto: home-claudio-git-mcp-memory-service (52.798 nós). Repo: ~/git/mcp-memory-service (fork, main).
Data: 2026-09-23. Read-only. XL: 2080 arquivos, 254.799 LOC, ~9919 funções, ~967 classes.

## Ramos principais (4 eixos)

### storage/backends
- O QUE É: 4 backends de persistência+vetor (sqlite_vec via mixins, cloudflare D1/Vectorize/R2, hybrid=sqlite primário+cloudflare secundário assíncrono, milvus) atrás de MemoryStorage ABC.
- MATURIDADE: sólido — factory + ABC + testes densos (test_sqlite_vec 2353 LOC, test_hybrid 1200, test_cloudflare 1009, test_milvus 1373+); milvus.py é o maior arquivo (3652 LOC).
- SINAL: milvus é enorme e sozinho (505 score) — superfície de manutenção desproporcional; hybrid.py (2117 LOC) concentra lógica de sync frágil (fila, drift, tombstones).

### quality (scorer, ai_evaluator, implicit, metadata_codec, onnx_ranker, async_scorer)
- O QUE É: pontuação de qualidade de memórias (ONNX cross-encoder/classifier local, LLM providers Groq/Gemini/OpenAI, sinais implícitos de acesso) + codec p/ sync.
- MATURIDADE: sólido no core, parcial no uso — test_quality_system 977 LOC + 4 arquivos de teste dedicados; MUITO código de manutenção (scripts/quality: migrate_to_deberta, rescore, bulk_evaluate, reset_onnx).
- SINAL: MCP_QUALITY_BOOST_ENABLED=false por padrão (opt-in) — o "boost" na busca não roda salvo config; abundância de scripts de re-scoring sugere churn de modelos (deberta↔onnx) e migrações repetidas.

### consolidation (decay, forgetting, consolidator, scheduler, clustering, compression, associations, health)
- O QUE É: pipeline "dream-inspired" (relevância→clustering→associations→compression→forgetting) agendado via APScheduler.
- MATURIDADE: sólido em teste, MORTO por padrão — 14 arquivos + suíte enorme (test_consolidator 26k, test_forgetting 22k, test_compression 32k); MAS MCP_CONSOLIDATION_ENABLED=false por padrão.
- SINAL: gated OFF — todo o subsistema (2 dos maiores módulos: consolidator 1225 LOC, health 833 LOC) só liga com env var; sub-fases (decay/assoc/clustering/compression) default true MAS só sob o master flag off.

### harvest (auto_capture, bootstrap, LLM classifier, rewriter, parser, extractor)
- O QUE É: extrai memórias de transcripts de sessão (claude/kiro/openclaw), classifica/reescreve via LLM, deduplica e armazena.
- MATURIDADE: sólido — harvester 437 LOC, classifier 415, rewriter 434; testes (harvest_pipeline_v2, provenance, classifier_backoff, scheduled_harvest, reharvest).
- SINAL: forte acoplamento a provedores LLM externos (Groq/OpenAI-compat) — degradação silenciosa se sem chave; bootstrap_utils tem scoring próprio que duplica ranking de retrieval.

### beliefs + NLI (reasoning)
- O QUE É: derivação de crenças a partir de observações (belief_service/belief.py) + classificação de contradições NLI (heurística/LLM) + quarentena.
- MATURIDADE: parcial/frágil — testado (belief_store, belief_noise_filter, nli_llm 33k, bootstrap_beliefs) MAS triplo-gated OFF: MCP_BELIEFS_ENABLED=false, MCP_NLI_ENABLED=false, MCP_NLI_ON_STORE=false.
- SINAL: gated off em 3 flags + persona/bootstrap-rules já registram "beliefs ruidosas (107 active, conf máx 0.64)" — sinal de que a derivação produz ruído; backend NLI default = "heuristic" (não modelo).

### retrieval/ranking (hybrid RRF, ranked_search, multi_strategy, retrieve mixins)
- O QUE É: busca híbrida BM25+vetor com fusão (weighted_average default), rerank ponderado (ranked_search), mixin de retrieve por backend.
- MATURIDADE: MISTO — hybrid mixin + ranked_search sólidos e usados (MCP_HYBRID_SEARCH_ENABLED=true default); multi_strategy.py é ÓRFÃO.
- SINAL DIVERGÊNCIA FORTE: reasoning/multi_strategy.py (RRF, RFC #1008 §6) tem testes mas NENHUM caller de runtime (só definido + re-exportado no __init__) — código "construído e não plugado"; só cobre estratégias semantic+tag.

### entity/graph (extraction, memory_graph, explore, graph storage)
- O QUE É: extração de entidades (NER multilíngue + domain extractors YAML), grafo de associações/entidades (GraphStorage sqlite, MilvusGraphStorage), tools explore/subgraph/shortest-path.
- MATURIDADE: sólido — graph.py handler 1006 LOC, graph storage 990 LOC, testes (graph_traversal 19k, transitive_closure, entity_profiles, milvus_graph 19k); SemanticReasoner (infer/suggest/abduct) WIRED via routing.
- SINAL: MCP_TYPED_EDGES_ENABLED=true default mas inferência de tipo de relação (relationship_inference 676 LOC) é heurística pesada — risco de ruído em edges; scripts de backfill/update de relationship_type indicam retrabalho de dados.

### sync/multi-store (exporter, importer, litestream, hybrid sync service)
- O QUE É: export/import JSON, replicação litestream (S3/systemd/launchd), sync bidirecional sqlite↔cloudflare, detecção de drift.
- MATURIDADE: parcial — hybrid BackgroundSyncService testado; MAS litestream é config-gen (scripts shell) sem testes; muitos scripts de reparo (recover_timestamps, sync_status, check_drift, safe_cloudflare_update).
- SINAL: proliferação de scripts de conserto de sync/timestamp (>10) = sinal de que o sync diverge na prática; litestream é caminho "de papel" (gera config, não há teste E2E).

### web/API + OAuth
- O QUE É: FastAPI app (1156 LOC) + dashboard SPA (app.js 6960 LOC), API REST completa (memories/search/analytics/quality/consolidation/documents/backup/sync), OAuth2 server próprio (authorization code/refresh/client-credentials) + storage sqlite/memory.
- MATURIDADE: sólido — OAuth authorization 990 LOC + middleware 475 + rate_limit + testes de integração (test_api_with_memory_service 1124 LOC); release de segurança v11.7 (TLS bypass gates).
- SINAL: MCP_OAUTH_ENABLED=false e MCP_HTTP_ENABLED=false default — toda a superfície web/OAuth é opt-in; dashboard app.js (6960 LOC, 1 classe) é monólito sem testes unitários visíveis.

### MCP tools/server (registry, handlers, routing)
- O QUE É: servidor MCP (mcp_server.py FastMCP + server_impl.py MemoryServer 3129 LOC) com registry de tools (1402 LOC) e routing p/ handlers por domínio.
- MATURIDADE: sólido mas PESADO — server_impl.py é o maior módulo Python (666 score, 3129 LOC, ~130 handlers); testes de cobertura de handler (test_all_memory_handlers, tool_registry, unified_tools, validate_handler_coverage).
- SINAL: server_impl.py concentra ~130 handle_* num só arquivo (God object) — apesar da extração para server/handlers/, o server_impl ainda duplica muitos handlers; risco de drift registry↔handler↔routing.

## Ramos NÃO listados encontrados no grafo (surpresas)

- **ingestion/** (PDF, CSV, JSON, text, semtools loaders + chunker): pipeline de ingestão de documentos completo, testado, com API (documents.py 834 LOC). Ramo grande e maduro não mencionado.
- **claude-hooks/ + opencode/ + examples/http-mcp-bridge.js**: enorme camada JS de integração de cliente (session-start.js 74k, context-formatter.js 54k, memory-scorer.js 31k, opencode/memory-plugin.js 36k) — praticamente um segundo produto em JS, com testes próprios.
- **backup/ (scheduler + service)**: subsistema de backup agendado (MCP_BACKUP_ENABLED=true default) + integrity monitor (health/integrity.py). Maduro, ligado por padrão.
- **plugins/ (registry + audit-log + smart-tagger)**: sistema de plugins com hooks on_store/on_retrieve/on_consolidate + 2 exemplos. Extensibilidade real, pouco documentada.
- **discovery/ (mDNS)**: advertise/discover de serviço via zeroconf (MCP_MDNS_ENABLED=true default) + testes (test_mdns 791 LOC). Ligado por padrão, raramente citado.
- **bootstrap/ (formatter Kiro/Claude)** + **models/ontology.py** (taxonomia de 12 tipos base + subtipos, custom types): ontologia formal testada (test_ontology 636 LOC) — núcleo semântico não citado.
- **video/ (Remotion) + site/ + docs/statistics**: marketing/demo (WalkthroughVideo.tsx 662 LOC, site 700k+ HTML) — peso morto para o runtime.
- **api/ (client.py, operations.py, types.py)**: interface "code-execution" compacta (token-efficient) separada dos handlers MCP — camada paralela pouco óbvia.

## TABELA-RESUMO

| Ramo | O que é | Maturidade | Sinal |
|------|---------|-----------|-------|
| storage/backends | 4 backends atrás de ABC+factory | sólido | milvus 3652 LOC solo; hybrid sync frágil |
| quality | scoring ONNX+LLM+implícito | sólido/parcial | QUALITY_BOOST off default; churn deberta↔onnx |
| consolidation | pipeline dream-inspired agendado | sólido em teste, morto em runtime | CONSOLIDATION_ENABLED=false default |
| harvest | extrai memórias de transcripts via LLM | sólido | depende de chave LLM externa; degrada silencioso |
| beliefs + NLI | derivação de crenças + contradição | parcial/frágil | 3 flags off; beliefs ruidosas (107, conf 0.64) |
| retrieval/ranking | híbrido BM25+vetor RRF/ranked | misto | multi_strategy.py ÓRFÃO (testado, sem caller) |
| entity/graph | NER + grafo + reasoner infer/suggest | sólido | typed edges heurísticos; backfill recorrente |
| sync/multi-store | export/import + litestream + drift | parcial | >10 scripts de conserto; litestream sem teste E2E |
| web/API + OAuth | FastAPI + dashboard + OAuth2 server | sólido | HTTP+OAUTH off default; app.js 6960 LOC monólito |
| MCP tools/server | FastMCP + ~130 handlers + registry | sólido/pesado | server_impl.py God object 3129 LOC |
| ingestion (surpresa) | loaders PDF/CSV/JSON/text + chunker | sólido | pouco citado no macro |
| claude-hooks/opencode (surpresa) | camada JS de cliente | sólido | ~"2º produto" em JS, fora do core Python |
| plugins (surpresa) | hooks on_store/retrieve/consolidate | parcial | extensibilidade pouco documentada |

## TOP 5 ramos que MAIS merecem aprofundamento

1. **retrieval/multi_strategy (RRF)** — código órfão testado mas sem caller: é o cheiro mais forte de "construído, não plugado" (RFC #1008 §6 pela metade).
2. **beliefs + NLI** — triplo-gated off + evidência empírica de ruído (107 beliefs, conf máx 0.64): "não é" o que promete; investigar se derivação vale a pena ligar.
3. **consolidation** — subsistema gigante (14 módulos, testes 100k+) completamente OFF por default: alto custo de manutenção para código que não roda em produção.
4. **sync/hybrid** — proliferação de scripts de reparo de timestamp/drift = sync diverge na prática; hybrid.py (2117 LOC) e litestream sem E2E são o risco operacional real.
5. **MCP tools/server_impl.py** — God object de 3129 LOC com ~130 handlers duplicando server/handlers/: risco de drift registry↔routing↔handler; refatoração incompleta.

## Nota metodológica
- Verificado: estrutura via generate_codebase_overview + listagem; flags default via grep em config/; wiring de multi_strategy/reasoning/beliefs via grep de callers; ROADMAP.md.
- NÃO verificado (macro, não aprofundado): corretude de cada teste, se flags off refletem uso real do Claudio, cobertura numérica por ramo, comportamento runtime.
