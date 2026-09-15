# RFC: Memory Importers (portas de entrada + vetor de adoção)

**Data:** 2026-09-13
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `feat/importers` (a partir de `upstream/main`)
**Base:** `upstream/main` v11.11.0
**Versão:** 0.1 (draft)
**Inspiração:** Mnemosyne `core/importers/` (mem0, letta, zep, honcho, hindsight, supermemory, cognee, holographic, agentic)
**Reintegra:** —
**Status:** DRAFT — amadurecer localmente antes de virar issue/RFC para o Henry

---

## 1. Problema

Não há caminho para trazer memórias de outros sistemas para o memory-service. Isso fecha duas portas: (a) enriquecer nosso acervo com conhecimento de sistemas que experimentamos; (b) reduzir a fricção de migração para quem quer adotar o projeto (relevante como OSS).

### Evidências

- O único caminho de entrada hoje é `store_memory` / harvest de sessões Kiro. Nada importa de mem0/letta/zep/etc.
- Mnemosyne trata importers como **estratégia de adoção**: 9 importers + keywords dos concorrentes no pyproject ("venha, trazemos suas memórias").
- Caso relevante para nós: importer `holographic` (Hermes Holographic Memory) — se T'Pol/Scotty usam a memória holográfica do Hermes, um importer puxa tudo para o store unificado.

### Causas

1. **Sem seam de import.** Não há interface base para adaptadores de sistemas externos.
2. **Sem adaptadores.** Cada sistema tem modelo de dados próprio; não há tradução para o nosso schema.

### Risco / motivação estratégica

Valor duplo: interno (entrada de conhecimento) + externo (adoção — suporte amplo remove fricção de migração e traz gente para o projeto).

---

## 2. Objetivo

Fornecer um **seam de import** com adaptadores por sistema externo, priorizando os de maior valor para nós (holographic/Hermes, agentic), traduzindo para o nosso schema com dedup e proveniência.

**Não-objetivos:** migrar PARA outro sistema (só importamos); suportar todos os 9 de uma vez (priorizar).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1).

### Funcional

**R1**: Existe uma interface base de importer.

> EARS: WHEN a new importer is added, THE system SHALL expose it through a common `BaseImporter` interface returning an `ImporterResult`.

**R2**: A importação traduz para o schema nativo.

> EARS: WHEN an external memory is imported, THE importer SHALL map it to the native memory schema (content, tags, importance, timestamps).

**R3**: A importação registra proveniência.

> EARS: WHEN a memory is imported, THE importer SHALL tag it with the source system (`imported:<system>`) and set veracity tier `imported`.

**R4**: A importação deduplica contra o acervo existente.

> EARS: WHEN an imported memory is similar (>= threshold) to an existing one, THE importer SHALL skip or evolve it instead of creating a duplicate.

**R5**: A importação suporta dry-run.

> EARS: WHERE `dry_run=true`, THE importer SHALL report what would be imported without writing.

### Não-Funcional

**R6**: A importação respeita pacing.

> EARS: WHILE importing a large dataset, THE importer SHALL honor rate/backoff pacing.

**R7**: Os adaptadores são independentes.

> EARS: THE importer for one system SHALL not depend on the SDK or availability of another.

---

## 4. Design

- `core/importers/base.py`: `BaseImporter` + `ImporterResult`.
- Adaptadores priorizados: `holographic.py` (Hermes — maior valor para a tripulação), `agentic.py` (LLM-guided). Demais (mem0/letta/zep/honcho/hindsight/supermemory/cognee) conforme necessidade.
- Dedup: reuso do path de embedding + similaridade (>=0.85 → skip/evolve).
- Proveniência: tag `imported:<system>` + veracity `imported` (alinha com futura RFC de veracity, se adotada).
- Tool MCP: `memory_import(system, source, dry_run)`.

---

## 5. Fora de Escopo

- Exportar/migrar PARA outro sistema.
- Suportar os 9 adaptadores simultaneamente (priorizar holographic + agentic).
- Sync contínuo com o sistema externo (import é pontual).

---

## 6. Critérios de Aceite

- [ ] `BaseImporter`/`ImporterResult` como seam comum.
- [ ] Import mapeia para schema nativo com tags/importance/timestamps.
- [ ] Proveniência `imported:<system>` + tier `imported`.
- [ ] Dedup skip/evolve contra acervo existente.
- [ ] `dry_run=true` reporta sem escrever.
- [ ] Adaptador `holographic` (Hermes) funcional como primeiro caso.
