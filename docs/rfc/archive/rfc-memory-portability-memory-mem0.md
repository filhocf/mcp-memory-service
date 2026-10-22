# Anexo (memory-system): mem0 — rfc-memory-portability

> Anexo-memory da `rfc-memory-portability` (RFC-mãe). Lado "bring your memory" (§4.2).
> Base: análise do código em `~/git/_analise-terceiros/mem0` (4/out, indexado no codebase-memory).
> Relatório: `~/.kiro/tmp/caract-mem0.md`. Doc que norteia o `Mem0Importer` (rfc-importers).

## 1. Quem é
mem0 ("mem-zero", `mem0ai`, Apache-2.0) — memory layer popular para agentes. Par-alvo prioritário
da RFC-mãe (Claude Code ⊕ mem0). Apache-2.0 = ideias/código absorvíveis sem fricção de licença.

## 2. Storage model
**NÃO guarda chunks — guarda FATOS atômicos em linguagem natural, extraídos por LLM na escrita.** 3 camadas:
- **Vector store** (a memória viva): default Qdrant, ~25 backends plugáveis. Texto do fato em `payload["data"]` + `text_lemmatized` (BM25).
- **SQLite `history.db`** (storage.py): só **audit log append-only** (ADD/UPDATE/DELETE/NONE) + buffer das últimas 10 msgs. ⚠️ SQLite NÃO é a memória (diferente do nosso sqlite-vec).
- **Graph/entity store** OPCIONAL: entidades + triplas (Neo4j/Memgraph/Kuzu), dedup semântico ≥0.95.

## 3. Schema
`MemoryItem` (configs/base.py:24-33) + payload (main.py:1975-1992): `id`(uuid4), `memory`(=payload data), `hash`(md5), `created_at`/`updated_at`(ISO-UTC), `text_lemmatized`, `metadata`(livre), escopo protegido `user_id`/`agent_id`/`run_id`/`actor_id`/`role`, `expiration_date`, `immutable`. `categories` só na Platform (não no OSS core).

## 4. Features trazíveis (feature-parity R4 — o que mem0 faz e nós não)
1. ⭐ **Fact-extraction + dedup NA ESCRITA** (prompts.py:176+, main.py:933-1030): quebra a conversa em fatos e o LLM decide ADD/UPDATE/DELETE/NONE vs os top-10 existentes — na hora do store. **Nós só fazemos pós-hoc** (harvest/distill/consolidate). MAIOR ganho conceitual. Conecta com nossa destilação (L2) e com a RFC fact-extraction/mm-02.
2. **TTL `expiration_date` + `immutable`** como campos de 1ª classe — trivial, anti-acúmulo.
3. **Procedural memory** — resumo passo-a-passo de sessão inteira.
Bônus: reranker plugável, custom_instructions na extração. **NÃO absorver** os 25 backends (fora do nosso escopo leve). mem0 **NÃO tem** beliefs/mistake_notes/quarantine/dream — nosso diferencial.

## 5. Export path ("bring")
- OSS self-hosted: `Memory.get_all(filters={"user_id":"alice"}, top_k=N)`, `get(id)`, `history(id)`.
- Platform: `MemoryClient.get_all()` (API key).
Mapa mem0 → nosso: `memory→content`, `categories→tags` (+ tag obrigatória `imported:mem0`), timestamps ISO-UTC diretos, `agent_id→agent_id`, **recomputar hash** (não reusar md5), `expiration_date→metadata.expires_at`. Dedup 0.92 na entrada.

## 6. Direção p/ construção
`Mem0Importer(BaseImporter)`: fetch via get_all → to_memory (mapa §5) → run com dedup/proveniência. Esboço completo em `~/.kiro/tmp/caract-mem0.md §6`.
