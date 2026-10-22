# Anexo (memory-system): Mnemosyne — rfc-memory-portability

> Anexo-memory da `rfc-memory-portability` (RFC-mãe). Lado "bring" (§4.2) + BENCHMARK do arco.
> Base: análise do código em `~/git/_analise-terceiros/mnemosyne` (4/out, indexado no codebase-memory).
> Relatório: `~/.kiro/tmp/caract-mnemosyne.md`. É o espelho do que QUEREMOS ser na portabilidade.

## 1. Quem é
Mnemosyne (`mnemosyne-oss`, MIT) — memory layer universal Hermes-first, **1 pip install + 1 SQLite,
zero infra** (1 dep de runtime: PyYAML). Lib-primeiro embarcável que também expõe MCP. É o **benchmark**:
faz as duas metades do arco (10 importers + adapters nativos) que nós não temos.

## 2. Storage model — BEAM (Bilevel Episodic-Associative Memory)
- **working_memory**: tier quente auto-injetado, TTL 168h / max 10k (beam.py:376).
- **episodic_memory**: long-term, busca híbrida 50% vetor + 30% FTS5 + 20% importance; vetor int8/float32/bit.
- **scratchpad**: efêmero.
- `sleep()` consolida working→episodic **aditivo** (não deleta, carimba consolidated_at). Degradação temporal 3-tiers. sqlite-vec + FTS5 com ladder de fallback. 36 tabelas, sem FKs.

## 3. Schema
(beam.py:1430-1460): id, content, source, timestamp, session_id, importance(0.5), metadata_json, veracity, memory_type, tier, created_at + identidade (author_id/type, channel_id). `remember()` (memory.py:541) tem `trust_tier='IMPORTED'` para bulk import.

## 4. Features trazíveis (o PONTO do benchmark)
**(a) ⭐ OS 10 IMPORTERS** (mnemosyne/core/importers/): mem0, letta, zep, cognee, honcho, supermemory, hindsight, **holographic (lê SQLite direto)**, **agentic (gera script p/ qualquer provider)**, file (JSON). Registry declarativo `PROVIDERS` (name/class/env_key/pypi/description). **Nós não temos NENHUM importer** — isto é o core do `rfc-importers`, copiar o padrão inteiro.
**(b)** adapters nativos por harness — referência pro lado "use".
**(c)** working/episodic tier — arco SEPARADO (nosso working-memory), fora de portabilidade.
**(d)** sync cripto — arco separado (delta-sync).

## 5. O que copiar do `BaseImporter` deles (referência direta pro rfc-importers)
`core/importers/base.py`:
1. **ABC** com `extract()/transform()/validate()` + `run()`.
2. **Pipeline run() em 4 fases**: extract → validate → transform → import (base.py:62-146); `dry_run` para em transform.
3. **`ImporterResult` dataclass**: provider/total/imported/skipped/failed/errors[cap20]/memory_ids[cap50] + to_json() — telemetria uniforme.
4. **transform() sempre produz o MESMO dict canônico** (content obrigatório + aliases content||memory||text).
5. **Preservar campos nativos** em `metadata._<provider>_*` — nunca perder origem.
6. **Write com bypass-dedup/IMPORTED**.
7. Registry PROVIDERS + import_from_file + modo agentic.

## 6. Export path (Mnemosyne → nosso store)
Fonte = 1 SQLite (`~/.hermes/mnemosyne/data/mnemosyne.db`). `MnemosyneImporter.extract()`: sqlite3.connect → UNION working+episodic → normalizar (content→content, metadata_json→tags+metadata, id→metadata._mnemosyne_id) → memory_store com conversation_id (bypass dedup) + tag `imported,mnemosyne`.

## 7. Direção p/ construção
Primeiro importer a construir = **MnemosyneImporter (SQLite direto)** — fecha o loop com o próprio benchmark e exercita o padrão BaseImporter que servirá a todos os outros. Priorização: importers = copiar agora; adapters/tiers/sync = arcos separados.
