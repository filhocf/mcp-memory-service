# RFC-MM-02: Fact Extraction (Batch, Incremental, RAG 3.0)

**Data:** 2026-07-20
**Status:** Draft
**Autor:** Claudio / Kiro

## Problema

`memory_ingest` chunkeia docs em blocos de ~1200 chars. Buscar "qual banco o RER usa"
retorna parágrafo inteiro. Entity graph tem edges genéricas (`has_entity`) sem semântica
relacional. Estamos em RAG 2.0 — falta navegação multi-hop tipada (RAG 3.0).

## Princípio

**Batch > unitário.** Mandar 20 chunks por call LLM economiza 20x em overhead.
**Incremental > full-scan.** Processar só chunks novos (nunca reenviar processados).
**Tripletos > texto.** Fatos atômicos (S→P→O) são navegáveis; chunks não.

## Solução

Pipeline batch que extrai tripletos de chunks não-processados via LLM.
Resultado armazenado como edges tipadas no memory_graph.

## Implementação

### 1. Flag incremental na tabela memories

```sql
ALTER TABLE memories ADD COLUMN facts_extracted_at TEXT DEFAULT NULL;
```

Chunks com `facts_extracted_at IS NULL` = pendentes de processamento.
Após processar batch → UPDATE com timestamp. Nunca reprocessa.

### 2. Batch prompt (20 chunks por call)

```
Extract atomic facts from these text chunks.
Return JSON: [{"chunk": N, "facts": [{"s": "subject", "p": "predicate", "o": "object", "confidence": 0.9}]}]
Only extract facts that are explicitly stated. Do not infer.

CHUNK 1: "..."
CHUNK 2: "..."
...
CHUNK 20: "..."
```

### 3. Provider

Usa `MCP_NLI_LLM_*` env vars (mesmo cascade do NLI: DeepSeek→Groq→Ollama).
Fallback: se LLM indisponível, marca batch como "retry" e segue.

### 4. Armazenamento

```sql
-- Reutiliza memory_graph com relationship_type tipado
INSERT INTO memory_graph (source_hash, target_hash, relationship_type, metadata)
VALUES ('entity:RER', 'entity:PostgreSQL', 'uses_database', '{"confidence": 0.9, "source_chunk": "abc123"}');
```

- source_hash e target_hash são entity IDs (não memory hashes)
- relationship_type = predicado do tripleto (normalizado)
- metadata = confidence + hash do chunk fonte (provenance)

### 5. Dedup

Antes de INSERT, verificar: mesmo (source, target, relationship_type) já existe?
- Se sim e confidence nova > antiga → UPDATE
- Se sim e confidence nova ≤ antiga → skip
- Se não → INSERT

### 6. Scheduler

```python
# Job: a cada 6h (ou sob demanda)
pending = SELECT content, content_hash FROM memories 
          WHERE facts_extracted_at IS NULL 
          LIMIT 200  # 200 chunks = 10 batches de 20

for batch in chunks(pending, 20):
    facts = llm_extract(batch)  # 1 call LLM
    store_facts(facts)          # INSERT/UPDATE memory_graph
    mark_processed(batch)       # UPDATE facts_extracted_at
    sleep(1)                    # throttle
```

- 200 chunks/rodada × 4 rodadas/dia = 800 chunks/dia
- 17K chunks existentes = ~21 dias para processar backlog completo
- Chunks novos (memory_store/ingest) → processados na próxima rodada (max 6h delay)

### 7. Impacto no retrieval

- `memory_explore`: mostra fatos atômicos por entidade ("RER → uses → PostgreSQL")
- `memory_graph(action="connected")`: navega por edges tipadas (multi-hop)
- Busca: "o que depende de PostGIS?" → segue edges `depends_on` → retorna entidades

## Economia

| Abordagem | Calls LLM | Tempo | Custo estimado |
|-----------|-----------|-------|----------------|
| 1 chunk/call | 17.000 | ~5h | ~$5-10 |
| 20 chunks/call (batch) | 850 | ~14min | ~$0.50-1.00 |

Batch é **20x mais eficiente** em tempo e custo.

## Acceptance Criteria

- [ ] Precision >80% em corpus PT-BR (100 chunks avaliados manualmente)
- [ ] `memory_explore` mostra fatos: "RER → uses → PostgreSQL + PostGIS"
- [ ] Zero reprocessamento (chunks processados nunca reenviam ao LLM)
- [ ] Dedup: 0 tripletos duplicados no graph
- [ ] Incremental: chunk novo ingerido hoje → fatos extraídos em <6h
- [ ] Graceful degradation: LLM offline → skip batch, retry na próxima rodada

## Métricas de Validação

| Métrica | Meta |
|---------|------|
| Precision | >80% (fatos corretos / total extraídos) |
| Recall | >60% (fatos extraídos / fatos reais no texto) |
| Throughput | 200 chunks/rodada, 4x/dia |
| Custo/rodada | <$0.15 (DeepSeek) |
| Backlog clearance | <21 dias para 17K chunks |

## Dependências

- LLM provider funcional (fork cascade OK, upstream precisa #116)
- memory_graph tabela existente (✅ já temos)

## Estimativa

3-4 dias implementação + 1 semana avaliação de precision/recall.
