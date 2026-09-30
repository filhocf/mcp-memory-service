# RFC: Quantização de Embeddings (int8 / binary vectors)

**Data:** 2026-09-13
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `feat/embedding-quantization` (a partir de `upstream/main`)
**Base:** `upstream/main` v11.11.0
**Versão:** 0.1 (draft)
**Inspiração:** Mnemosyne `binary_vectors.py` (MIB, arXiv:2601.11557) + sqlite-vec int8/bit nativo
**Reintegra:** —
**Status:** DRAFT — amadurecer localmente antes de virar issue/RFC para o Henry

---

## 1. Problema

O banco de produção cresce sem teto e os embeddings float32 são o terceiro maior consumidor de espaço, sem que a precisão float32 traga ganho de recall proporcional ao custo.

### Evidências (13/set/2026, banco de produção sirdata)

- Banco total: **457 MB**, 21.081 memórias.
- Composição (dbstat): `memory_content_fts_data` 142 MB (31%) · `memories` 101 MB (22%) · **`memory_embeddings_vector_chunks00` 82 MB (18%)** · `memory_graph` 51 MB + índices ~44 MB (21%).
- Embeddings: 384 dims × float32 = 1536 bytes/vetor × ~21k = ~32 MB de dados úteis, mas o chunk store ocupa 82 MB (overhead de layout vec0).
- Modelo atual: `paraphrase-multilingual-MiniLM-L12-v2` (384 dims), PT-BR, USE_ONNX=0.

### Causas (a confirmar no código)

1. **Sem opção de compressão.** O backend sqlite-vec grava vetores em float32; não há chave de configuração para int8 ou bit.
2. **Recall float32 é overkill para o caso de uso.** Retrieval de memórias de agente tolera perda pequena de precisão; a quantização int8 do sqlite-vec preserva recall quase intacto (Mnemosyne usa int8 como default).

### Risco

Sem compressão, o banco continua crescendo linearmente com o acervo. O sync via arquivo (Insync/hot-backup) transfere 457 MB a cada operação — custo que escala com o tamanho.

---

## 2. Objetivo

Reduzir o espaço de embeddings via quantização **configurável** (float32 → int8 → bit), preservando recall dentro de um limiar aceitável no corpus PT-BR real.

**Não-objetivos:** trocar o modelo de embedding; reescrever o backend de storage; comprimir FTS ou grafo (RFCs separadas).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1): prosa primeiro, EARS depois; uma ação por frase; sujeito = componente; SHALL=obrigatório; cada requisito origina teste G3 RED.

### Funcional

**R1**: O tipo de vetor é configurável por variável de ambiente.

> EARS: WHERE `MCP_MEMORY_VEC_TYPE` is set to `float32`, `int8` or `bit`, THE storage backend SHALL create the vec0 table with the corresponding column type.

**R2**: O padrão preserva o comportamento atual (não quebra bancos existentes).

> EARS: WHEN `MCP_MEMORY_VEC_TYPE` is unset, THE storage backend SHALL default to `float32`.

**R3**: A quantização int8 mantém recall dentro do limiar.

> EARS: WHEN retrieval runs against an int8-quantized store, THE system SHALL retain recall@10 within 5% of the float32 baseline on the PT-BR corpus.

**R4**: A busca por bit vectors usa distância de Hamming.

> EARS: WHERE `MCP_MEMORY_VEC_TYPE=bit`, THE storage backend SHALL rank candidates by Hamming distance and re-rank the top-K with a second-phase float comparison.

**R5**: A migração de um banco existente é explícita e reversível.

> EARS: WHEN a re-embedding migration is invoked, THE migration tool SHALL re-quantize all vectors into a new table and keep the original until the operator confirms.

### Não-Funcional

**R6**: A mudança é aditiva e não altera o contrato de recall existente por padrão.

> EARS: THE quantization SHALL only take effect when explicitly configured, leaving the default install unchanged.

**R7**: O ganho de espaço é medido e reportado.

> EARS: WHEN the migration completes, THE migration tool SHALL report bytes-before, bytes-after and the compression ratio.

---

## 4. Design

- Chave `MCP_MEMORY_VEC_TYPE` lida na inicialização do backend sqlite-vec (`storage/sqlite_vec.py`).
- Tabela vec0 criada com `float[384]` / `int8[384]` / `bit[384]` conforme a chave.
- `bit`: binarização por sinal (`value > 0 → 1`), 384 dims → 48 bytes (32x). Busca em 2 fases: Hamming (rápido, SQLite) → top-K re-rankeado por cosseno float (precisão).
- Migração: script que lê embeddings atuais, re-quantiza, escreve tabela nova; `VACUUM` obrigatório ao final para devolver páginas ao disco.

### Estimativa (dados reais)
- int8: 82 MB → ~21 MB (**−61 MB, −13% do banco**). Baixo risco.
- bit: 82 MB → ~3 MB (**−79 MB, −17%**). Exige validar recall PT-BR (R3/R4).

### ✅ G0 / validação de viabilidade (18/set/2026, sirdata)

Confirmado antes de implementar:
- `memory_embeddings_vector_chunks00` = **84 MB** real (dbstat) — bate com a estimativa.
- **sqlite-vec 0.1.9 suporta os 3 tipos nativamente**: `float[N]`, `int8[N]`, `bit[N]` (testado).
- vec0 atual: `content_embedding FLOAT[384] distance_metric=cosine, store TEXT partition key`.
- Criação da vec0 em DOIS pontos: `utils/db_utils.py:317` e `storage/mixins/migrations.py:281`.

**Achado que reposiciona o escopo:** trocar o tipo na criação (R1/R2) só afeta bancos NOVOS.
O ganho de −61 MB no NOSSO banco (22k vetores já em FLOAT[384]) exige a **migração
re-quantizadora (R5)** — é a parte que entrega o valor localmente, e a mais delicada
(mexe em 84 MB do serviço vivo). Ordem de implementação:
1. R1/R2: `MCP_MEMORY_VEC_TYPE` nos 2 pontos de criação + default float32 (aditivo, seguro).
2. R5: script de migração (lê FLOAT[384] → re-quantiza int8 → tabela nova → VACUUM → reporta bytes). Manter original até confirmar.
3. R3: validar recall@10 int8 vs float32 no corpus PT-BR real (rodar retrieval comparativo).
4. R4/bit: fase posterior, atrás de flag, só se recall int8 provar o caminho.
**Precisa sessão dedicada** (mexe no serviço vivo; fazer com backup do banco antes).

---

## 5. Fora de Escopo

- Compressão de FTS (142 MB) — ver RFC hygiene.
- Compressão do grafo (51 MB) — RFC futura.
- Troca de modelo de embedding.

---

## 6. Critérios de Aceite

- [ ] `MCP_MEMORY_VEC_TYPE=int8` cria store int8 e recall@10 fica dentro de 5% do baseline no corpus PT-BR.
- [ ] `MCP_MEMORY_VEC_TYPE` unset mantém float32 (nenhum banco existente afetado).
- [ ] Migração reporta bytes-before/after + ratio e roda `VACUUM`.
- [ ] `bit` implementa Hamming + re-rank 2-fases (feature-flagged, atrás de validação de recall).
