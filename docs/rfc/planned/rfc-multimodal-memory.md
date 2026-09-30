# RFC: Multimodal Memory (imagem/vídeo/áudio → texto recallável)

**Data:** 2026-09-13
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `feat/multimodal-memory` (a partir de `upstream/main`)
**Base:** `upstream/main` v11.11.0
**Versão:** 0.1 (draft)
**Inspiração:** Mnemosyne `media.py` (RFCs 0002-0004: media_assets + media_moments, sem BLOB)
**Reintegra:** —
**Status:** DRAFT — amadurecer localmente antes de virar issue/RFC para o Henry

---

## 1. Problema

Memórias são só texto. Conteúdo visual/áudio relevante (diagramas, prints, frames, gravações) não é recallável — o agente tem que reabrir a mídia toda vez para consultar "o que está onde".

### Evidências (caso de uso ativo)

- **Infográfico do Debian em produção agora:** exige reabrir a imagem repetidamente para ver a disposição dos elementos. Não há como perguntar ao agente "onde está a timeline no infográfico".
- Prints de workshop (ex: slides da Kell/TLC), frames do Papo Saúde — todos conteúdo que hoje vive fora da memória.
- Mnemosyne resolve com provider de visão que descreve a mídia e grava a descrição como memória de texto normal (herda recall/decay/sync).

### Causas

1. **Sem ingestão de mídia.** Não há caminho para registrar uma referência de mídia e derivar texto recallável dela.
2. **Sem provider de modalidade.** Nenhum seam para chamar um modelo de visão/áudio.

### Risco

Baixo (feature aditiva). O custo de não fazer é trabalho manual repetido ao consultar conteúdo visual.

---

## 2. Objetivo

Permitir que imagem/vídeo/áudio virem **memórias recalláveis** via provider de modalidade que descreve a mídia em texto, sem armazenar bytes no banco (só referência + texto).

**Não-objetivos:** armazenar bytes no banco; embedding multimodal nativo; OCR próprio (delegado ao provider).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1).

### Funcional

**R1**: Uma referência de mídia pode ser ingerida.

> EARS: WHEN `remember_media(ref)` is invoked, THE system SHALL register the media reference and describe it via the configured modality provider.

**R2**: A descrição vira memória de texto recallável.

> EARS: WHEN a media description is produced, THE system SHALL store it as an ordinary memory that hybrid recall already understands.

**R3**: O banco não armazena bytes.

> EARS: WHEN media is ingested, THE system SHALL store only the reference and the derived text, never the raw bytes.

**R4**: A ingestão é idempotente.

> EARS: WHEN the same media is re-ingested, THE system SHALL not create duplicate assets or moments.

**R5**: A feature é off por padrão.

> EARS: WHERE `modality_enabled` is false, THE system SHALL behave exactly as a text-only install.

**R6**: A ingestão degrada em estágios sem falhar.

> EARS: WHERE no modality provider is configured, THE system SHALL register the asset as `unavailable` (a success) to be described later.

### Não-Funcional

**R7**: O provider é agnóstico de fornecedor.

> EARS: THE modality seam SHALL be named after the protocol (OpenAI-compatible endpoint), not a vendor.

---

## 4. Design

- Tabelas sidecar `media_assets` (referência) + `media_moments` (span descrito), criadas `IF NOT EXISTS`, sem BLOB, sem FK de schema (validação em app).
- Cada moment = uma `working_memory`/memory row normal → herda recall/decay/sync.
- `remember_media(ref) -> MediaIngestResult` (ok/partial/unavailable/refused).
- Provider seam: `MCP_MEMORY_MODALITY_BASE_URL`/`_API_KEY`/`_VISION_MODEL`/`_AUDIO_MODEL` (OpenAI-compatible).
- `doctor`: checagem de orphans de mídia.

### Caso de uso imediato
- Infográfico Debian: `remember_media(infografico.png)` → provider descreve layout → memórias recalláveis ("timeline no centro, versões à direita") → consulta via `memory_search` sem reabrir.

---

## 5. Fora de Escopo

- Embedding multimodal nativo (descrição textual é suficiente).
- Armazenar bytes.
- OCR/visão próprios (delegado ao provider).

---

## 6. Critérios de Aceite

- [ ] `remember_media(ref)` registra referência + descrição textual recallável.
- [ ] Zero bytes de mídia no banco.
- [ ] Re-ingestão idempotente.
- [ ] `modality_enabled=false` = install text-only intacto.
- [ ] Sem provider → asset `unavailable` (sucesso), descrito depois.
- [ ] Caso Debian: infográfico consultável via `memory_search`.
