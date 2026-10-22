# SPEC — Fase 0: perfil Kiro em YAML + triagem de sessão

**Deriva de:** `rfc-ingestao-multi-agente` v0.3 (camadas C2 + C3a)
**Data:** 2026-09-30 · **Status:** DRAFT (aguarda aval do design na discussion #1393)
**Escopo:** 1 incremento pequeno, refactor dado→config + gate de triagem. Sem mudança de comportamento de extração. Compat trivial.

> **Nota de sequência:** esta spec só deve virar código depois do Henry validar o design na #1393. É o "primeiro incremento" proposto lá. Escrita agora para estar pronta; o rumo pode ajustar conforme a resposta.

## 1. Objetivo
Extrair as regras hardcoded do parser específicas do Kiro para um perfil declarativo `harvest/agents/kiro.yaml`, e plugar a **triagem de sessão** (`harvest/triage.py`, já consolidada) como gate barato antes do parse/LLM. Integrar um agente novo passa a ser escrever um YAML + fixtures, não editar o parser.

## 2. O que sai do código para o YAML (dados, não lógica)
Do `parser.py`, viram dados declarativos em `agents/kiro.yaml`:
- `KIRO_KIND_MAP`, `PAYLOAD_ROLE_MAP` → `roles.by_payload_type`
- detecção de formato (1ª linha: `kind`/`payload.type`/`traceSchema`) → `detect.first_line`
- globs de `find_sessions` (`*/*/messages.jsonl`, `cli/*.jsonl`) → `discovery.globs` + `discovery.exclude` (`*(2).jsonl`)
- markers de `_is_injected_content` → `noise.injected_markers`
- cutoff de `_is_system_content` (10k) → `noise.system_cutoff_chars`
- assinaturas de teste + limiares de triagem → `triage.*`

Fica em **código** (hook nomeado, RC2.3): a navegação aninhada de `tool_result` (`_extract_toolresult_text`) — resíduo irredutível que YAML não expressa.

## 3. Schema do `harvest/agents/kiro.yaml` (esboço)
```yaml
agent: kiro
detect:
  first_line: { payload.type: [user, assistant] }   # vs kind (v3), traceSchema (openclaw)
discovery:
  globs: ["*/*/messages.jsonl", "cli/*.jsonl"]
  exclude: ["*(2).jsonl"]                            # sync-conflict dupes
  dedup_by: sess_uuid                                # RC3.7
roles:
  by_payload_type: { user: user, assistant: assistant, tool_result: assistant }
noise:
  injected_markers: ["<system-reminder>", "<command>", "<ide>"]
  system_cutoff_chars: 10000
  structural: { drop_if_starts_with: ["{", "["], max_structural_ratio: 0.30 }
tool_results:
  hook: kiro_toolresult_text                         # named code hook (RC2.3)
triage:                                              # camada C3a (RC3.5-3.10)
  threshold: 0.25                                    # tunable via MCP_HARVEST_TRIAGE_THRESHOLD
  test_signatures:                                   # language-agnostic intent
    - '^(hello|hi)\b'
    - '^respond with'
    - '^turn \d+\s*:'
    - '^list all (tools|mcp)'
    # ... (ver triage.TEST_SIGNATURE)
```

## 4. Requisitos (EARS)
- **S0.1** — THE loader SHALL carregar `agents/{agent}.yaml` espelhando `load_patterns` (fallback sem-PyYAML, resolução central).
- **S0.2** — WHEN o perfil Kiro é aplicado, THE parser SHALL produzir saída **byte-idêntica** à atual nas sessões reais (golden test via `coverage_report()`, #1350). Zero mudança de comportamento.
- **S0.3** — THE triagem SHALL rodar ANTES do parse por-bloco; sessões com `verdict=drop` não são parseadas nem enviadas ao LLM.
- **S0.4** — THE discovery SHALL deduplicar por `sess_uuid` e excluir `*(2).jsonl` conforme o perfil.
- **S0.5** — THE hook de tool-result SHALL ser referenciado por nome no YAML e resolvido no código (não inline no YAML).
- **S0.6** — WHERE `agents/kiro.yaml` estiver ausente, THE parser SHALL cair no comportamento hardcoded atual (compat / rollback trivial).

## 5. Golden test (não-regressão)
1. Rodar `coverage_report()` sobre o corpus real ANTES do refactor → baseline.
2. Aplicar o refactor (dados → YAML).
3. Rodar de novo → deve ser **byte-idêntico** ao baseline.
4. Triagem: os 11 retidos / 40 descartados do §8 devem reproduzir (fixture: `tests/harvest/test_triage.py`).

## 6. Fora de escopo (fases seguintes)
- Registro multi-fonte C1 (Fase 2). Aqui o discovery ainda é 1 fonte.
- LLM design-extractor (I2). A triagem prepara o terreno; o extractor é depois.
- Perfis de outros agentes (openclaw/hermes). Kiro primeiro, prova o mecanismo.

## 7. Peças já prontas
- `harvest/triage.py` + `tests/harvest/test_triage.py` (score calibrável, 193 testes verde) — a triagem já existe, falta plugar.
- `coverage_report()` (#1350) — o instrumento de golden test.
- Corpus curado em `~/local-data/kiro-harvest-curado/` (11 sessões) — fixture de validação.
