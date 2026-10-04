> ⚠️ SUPERSEDED by rfc-mm-02-fact-extraction (mais maduro: batch 20x, incremental, dedup). Mantido como histórico. Ver docs/adr/README.md.

# Spec: Fact Extraction de Documentos (GAP H)

**Data:** 2026-06-12
**Status:** Draft
**Relacionado:** GAP H (Spock comparativo), OP-5, memory_distill, memory_ingest

## Problema

`memory_ingest` chunkeia documentos em blocos de ~1200 chars. Cada chunk é um pedaço de texto contínuo, não fatos atômicos. Resultado:
- Buscar "quais restrições o F008 verifica" retorna um bloco grande
- O agente precisa LER o bloco e inferir os fatos — em vez de receber fatos prontos
- Entity linking funciona no chunk inteiro mas não nos fatos individuais

## Solução: memory_extract_facts

Nova tool (ou extensão do `memory_distill`) que processa chunks já ingeridos e extrai fatos atômicos via LLM.

### Fluxo

```
memory_ingest(dir, store="mir")         → chunks brutos (hoje)
memory_extract_facts(store="mir")       → fatos atômicos (novo)
```

### Interface

```python
memory_extract_facts(
    store: str = "default",       # store dos chunks a processar
    tags: list = [],              # filtro opcional por tags
    max_chunks: int = 50,         # limite por chamada (batch)
    min_chunk_size: int = 200,    # ignorar chunks muito pequenos
    dry_run: bool = true          # preview antes de persistir
)
```

### Retorno

```json
{
  "processed": 50,
  "facts_extracted": 127,
  "facts_stored": 120,
  "duplicates_skipped": 7,
  "sample": [
    {"fact": "F008 verifica sobreposição com floresta tipo B via ST_Intersects", "source_chunk": "7ddb8e..."},
    {"fact": "Dados de TI vêm da FUNAI via WFS", "source_chunk": "589f60..."}
  ]
}
```

### Implementação

**Onde:** `src/mcp_memory_service/services/fact_extractor.py` (novo)

```python
class FactExtractor:
    """Extract atomic facts from document chunks via LLM."""
    
    PROMPT = """Extraia 3-10 fatos atômicos deste texto.
Cada fato deve ser:
- Auto-contido (entendível sem contexto adicional)
- Específico (não genérico)
- Curto (1-2 frases)

Texto:
{content}

Responda APENAS com JSON: [{"fact": "..."}, ...]"""

    async def extract_from_chunk(self, content: str) -> list[str]:
        """Call LLM to extract facts from a single chunk."""
        ...

    async def process_store(self, storage, store: str, tags: list, max_chunks: int) -> dict:
        """Process unextracted chunks in a store."""
        # 1. Query chunks sem flag 'facts_extracted' no metadata
        # 2. Para cada chunk: extract_from_chunk()
        # 3. Cada fato → memory_store(content=fact, store=store, 
        #    tags=original_tags+["fact"], metadata={"source_chunk": hash})
        # 4. Marcar chunk como processado (metadata update)
        ...
```

### LLM Provider

Usa o pipeline multi-provider existente (harvest/rewriter.py):
1. **Kiro CLI headless** (preferencial — $0, ver spec kiro-headless-llm-provider)
2. DeepSeek (fallback — barato, 128K context)
3. Groq (fallback rápido)
4. Ollama local (fallback offline)

### Dedup

- Fato similar a memória existente (cosine > 0.85) → skip
- Flag `metadata.facts_extracted = true` no chunk fonte → não reprocessar

### Entity Linking

Fatos extraídos passam pelo domain NER per-store automaticamente (já implementado).
Resultado: "F008 verifica floresta tipo B" → entity links: F008, floresta tipo B.

### Quando rodar

- **Manual:** `memory_extract_facts(store="mir")` após ingestão
- **Automático (futuro):** hook pós-ingestão no scheduler

## Impacto Esperado

Antes: buscar "restrições F008" → 1 chunk de 1200 chars
Depois: buscar "restrições F008" → 7 fatos atômicos individuais, cada com entity links

## Sequenciamento

1. Spec (este documento) ✅
2. Implementar FactExtractor + handler
3. Integrar com multi-provider LLM (ver spec kiro-headless)
4. Testar com store mir (788 chunks → ~2000-4000 fatos)
5. Propor ao upstream como extensão do memory_distill (pós-consolidation)
