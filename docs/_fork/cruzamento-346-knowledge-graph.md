# Cruzamento: Discussion #346 (Knowledge Graph Evolution) × estado do fork

> **Criado:** 2026-10-05 · **Autor:** Zero (validado por subagent arch/seven lendo o código) · **Fork-only.**
> **Propósito:** cruzar a visão de 4 fases do Henry (#346) com o que o fork JÁ tem, para (a) evitar
> retrabalho (reimplementar o que existe) e (b) montar o draft de resposta ao Henry mostrando onde
> estamos. Evidência por `arquivo:linha` (grafo reindexado 05/out pós-merge; leitura confirmada pelo arch).

## A #346 em uma frase
Henry propõe transformar o serviço de "busca semântica" em "grafo de conhecimento verdadeiro"
adicionando a camada ontológica (os "30% que faltam"): vocabulário controlado, relacionamentos
tipados, validação de schema e camada de raciocínio. Roadmap: F0 Ontologia · F1 Quality · F2 Typed
Relationships · F3 Agentic RAG ontology-aware · F4 Open Standards (RDF/OWL/SKOS/SPARQL).

## Mapa Fase × estado do fork (VALIDADO no código)

| Fase #346 | Status no fork | Evidência (arquivo:linha) |
|-----------|----------------|---------------------------|
| **F0 Ontologia** (tipos formais + taxonomia + rel. tipados + reasoning) | **IMPLEMENTADO** (parcial no reasoning) | `models/ontology.py` — `BaseMemoryType` (12 tipos, L40-66), `TAXONOMY` (L67+), `RELATIONSHIPS` 8 tipos com `valid_patterns` (L170-203), `SYMMETRIC_RELATIONSHIPS` (L205), `validate_relationship`/`is_symmetric_relationship` (L497-608). Usado em `models/memory.py:24,68`, `storage/graph.py:37,221`, `storage/milvus_graph.py:51,325`, `relationship_inference.py:25-27,351`. `reasoning/inference.py:165-207` `infer_transitive` real + `detect_contradictions`/`find_fixes`/`find_causes`. |
| **F1 Quality System** | **IMPLEMENTADO** | Arco rating FECHADO (`ESTADO.md:9-13`): PRs #1349, #1368, #1391, #1404 merged. `rfc/implemented/rfc-quality-model.md`. |
| **F2 Typed Relationships** | **IMPLEMENTADO** (wired end-to-end) | `consolidation/relationship_inference.py:173-358` (`infer_relationship_type`, thresholds #541, opt-out #546). Fluxo real: `consolidator.py:244` instancia → `:1051` chama → `:1079-1086` persiste via `store_association(relationship_type=...)`. Migração de coluna: `scripts/migration/add_relationship_type_column.py`. |
| **F3 Agentic RAG ontology-aware** (query intent → graph traversal) | **AUSENTE** | ⚠️ NÃO confundir com `rfc-query-intent` (DRAFT, PAUSADA — `ESTADO.md:107`), que é tuning de peso vetor/FTS (§2 explicita: zero-grafo, zero-LLM). F3 = rotear intenção da query para traversal ontológico nos edges tipados. Temos as peças (edges + `SemanticReasoner`), falta a camada de roteamento. |
| **F4 Open Standards** (RDF/OWL/SKOS/SPARQL) | **AUSENTE** | 0 referências em `src/` (grep RDF/OWL/SPARQL/SKOS/rdflib/turtle/triplestore). 0 RFC. |

## Ressalvas de rigor (não superestimar ao Henry)
1. **`valid_patterns` NÃO são enforçados.** Existem como dado em `ontology.py:175-191`, mas nenhum
   consumidor os aplica. O write (`storage/graph.py:219-221`) valida nome-do-tipo e simetria, não a
   consistência do par source→target. Temos vocabulário controlado + validação de tipo/simetria;
   **não** temos validação de padrão (parte do "reasoning" que a #346 pede).
2. **`abstract_to_concept`** (`reasoning/inference.py:143-164`) é **stub** (`return None`). O reasoner
   não está 100%.

## Onde NÓS vamos ALÉM da #346 (ela não menciona)
- **Learning-loop** (`ESTADO.md:15-31`, `rfc/README.md` arco APRENDIZADO): telemetria `usage_events`
  (migration 014), injeção proativa `memory_context`, feedback passivo RFC-MM-01, métrica de
  assertividade (ADR-0005). A #346 organiza o grafo; não trata de **aprender com o uso**.
- **Ingestão multi-agente** (`ESTADO.md:40-58`): regras por agente plugáveis em YAML, `triage.py`
  (193 testes), RFC #1393. Ortogonal à #346.
- **Delta-sync** (ADR-0002, `rfc-delta-sync` #1345): sincronização multi-máquina. Fora do escopo da #346.
- **Portabilidade** (#1364, 5 camadas, aceita pelo Henry) e **hub multi-agente** (agent_id merged).

## Veredito
"Já temos quase tudo" é **verdadeiro para F0 (com ressalvas), F1 e F2 — implementados e wired, não
código morto**. É **falso para F3 e F4 — dois gaps reais, não um**. Além disso, três arcos nossos
(learning-loop, ingestão multi-agente, delta-sync) são camadas que a #346 nem toca.

## Plano de ação
1. **Responder a #346** (draft EN+PT-BR, aprovação do Claudio antes de postar): mostrar que F0-F2 já
   estão no código (apontar os arquivos), que F3/F4 são os gaps, e posicionar nossos arcos
   (learning-loop etc.) como camadas complementares. Tom: colaborativo, "já estamos 70% lá no código,
   não só no roadmap".
2. **F3** (se priorizado): desenhar RFC real de intent→graph-traversal (reusa `SemanticReasoner`).
   NÃO reaproveitar rfc-query-intent (é outra coisa).
3. **Enforcement de valid_patterns** (quick win de rigor): aplicar o par source→target no write do grafo.
4. **F4** fica como "nice to have" (a própria #346 marca como opcional/futuro).

## Referências
- Discussion #346 (doobidoo/mcp-memory-service) · issues relacionadas #91/#261/#175/#292/#86/#219
- Issues de hoje na mesma área: #1457/#1459/#1460 (thresholds e auto-supersede de relationship inference)
- `docs/rfc/README.md` (árvore de arcos) · `docs/_fork/ESTADO.md` · `docs/adr/0002-0005`
