---
source: internal
created: 2026-06-04
status: implementing
depends_on: none (independent)
---

# §9 — Split config.py by Domain

## Objetivo

Decompor `config.py` (1327 linhas, monolítico) em módulos focados por domínio, mantendo backward compatibility total via re-export.

## Módulos

| Módulo | Conteúdo |
|--------|----------|
| `config/base.py` | Helpers, .env loading, BASE_DIR, SERVER_NAME/VERSION |
| `config/storage.py` | Backend selection, SQLite path, Cloudflare, Milvus, content length limits |
| `config/transport.py` | SSE/HTTP, CORS, heartbeat, timeout, mDNS, peer SSL |
| `config/oauth.py` | OAuth, RSA keys, JWT functions, DCR, issuer, validate |
| `config/embedding.py` | EMBEDDING_MODEL_NAME, USE_ONNX, ONNX_MODEL_CACHE |
| `config/consolidation.py` | CONSOLIDATION_ENABLED, CONFIG dict, SCHEDULE, archive |
| `config/quality.py` | Quality system, boost, retention, maintain, insight cards, entities |
| `config/search.py` | Hybrid search, RRF, weights, mistake note dedup |
| `config/graph.py` | GRAPH_STORAGE_MODE, associations, typed edges |
| `config/documents.py` | LlamaParse, chunk size/overlap |
| `config/backup.py` | Backup enabled/interval/retention |
| `config/__init__.py` | Re-export all (backward compat) |

## Constraints

1. `from .config import X` deve continuar funcionando (51 consumidores)
2. Import order: base → storage → embedding → resto
3. Side effects (makedirs, logger.info, validate) na mesma ordem
4. 0 mudanças de comportamento
5. Testes existentes devem passar sem modificação

## doobidoo alignment

Issue #7: "§9 split config.py: yes, please. Pure-mechanical, no-API-change wins."
