# RFC: Ranking — Weibull Decay + Polyphonic Recall

**Data:** 2026-09-13
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `feat/ranking-upgrades` (a partir de `upstream/main`)
**Base:** `upstream/main` v11.11.0
**Versão:** 0.1 (draft)
**Inspiração:** Mnemosyne `weibull.py` (decay por tipo) + `polyphonic_recall.py` (4 vozes + re-rank determinístico)
**Reintegra:** alinha com composite scoring upstream (issue #55, hop distance + centrality)
**Status:** DRAFT — amadurecer localmente antes de virar issue/RFC para o Henry

---

## 1. Problema

Duas fraquezas de ranking: (a) o decay temporal é uniforme (mesma taxa para todo tipo de memória), quando preferências deveriam decair devagar e eventos rápido; (b) o retrieval usa uma estratégia por vez, sem combinar sinais complementares (vetor, grafo, fato, tempo) num re-rank robusto.

### Evidências

- O modo `ranked` do `memory_search` aplica `time_decay` com meia-vida única — uma preferência estável ("Claudio prefere PT-BR") decai igual a um evento pontual ("deploy falhou terça").
- O retrieval combina semantic + quality, mas não faz recuperação multi-voz com re-rank determinístico + penalidade de diversidade (o que o polyphonic do Mnemosyne faz).
- Composite scoring upstream (#55) já caminha nessa direção (hop distance + centrality) — as duas ideias se somam.

### Causas

1. **Decay uniforme.** Uma única meia-vida (`MCP_MEMORY_RECENCY_HALFLIFE`) para todos os tipos.
2. **Retrieval mono-estratégia.** Sem orquestração de vozes complementares nem re-rank com diversidade.

### Risco

Médio-baixo. É melhoria de qualidade de retrieval. O polyphonic é maior em esforço; o Weibull é pequeno e isolável.

---

## 2. Objetivo

(a) Substituir o decay uniforme por **Weibull por tipo de memória**; (b) introduzir **polyphonic recall** — recuperação multi-voz (vetor/grafo/fato/temporal) com re-rank determinístico rule-based e penalidade de diversidade.

**Não-objetivos:** re-rank neural; substituir os modos existentes (adicionar, não trocar).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1).

### Funcional — Weibull decay

**R1**: O decay temporal varia por tipo de memória.

> EARS: WHEN temporal scoring runs, THE system SHALL apply per-type Weibull parameters (shape k, scale eta) instead of a single uniform half-life.

**R2**: Preferências/perfis decaem mais devagar que eventos.

> EARS: WHERE a memory is of type `preference` or `profile`, THE system SHALL use a decreasing-hazard Weibull (k<1); WHERE it is an `event`/`request`, THE system SHALL use an increasing-hazard Weibull (k>1).

**R3**: O comportamento atual é o default para tipos sem parâmetro.

> EARS: WHERE a memory type has no Weibull parameters configured, THE system SHALL fall back to the current exponential decay (k=1).

### Funcional — Polyphonic recall

**R4**: A recuperação combina múltiplas vozes.

> EARS: WHEN polyphonic recall is enabled, THE system SHALL query vector, graph, fact and temporal voices and combine their scores.

**R5**: O re-rank é determinístico e rule-based.

> EARS: WHEN combining voices, THE system SHALL apply fixed rule-based weights (no neural network) producing deterministic ordering.

**R6**: O resultado penaliza duplicatas.

> EARS: WHEN assembling the final list, THE system SHALL apply a diversity penalty so near-duplicate memories do not dominate.

**R7**: Polyphonic é opt-in.

> EARS: WHERE polyphonic recall is disabled, THE system SHALL use the current retrieval path unchanged.

### Não-Funcional

**R8**: As melhorias são mensuráveis contra o baseline.

> EARS: WHEN evaluated, THE system SHALL report recall@10 and precision deltas versus the current ranking on the PT-BR corpus.

---

## 4. Design

- `weibull.py`: `weibull_boost(age, mem_type)` + tabela `WEIBULL_PARAMS` por tipo; pluga no scoring do modo `ranked`.
- `polyphonic_recall.py`: 4 vozes (vector/graph/fact/temporal) → `RecallResult` por voz → re-ranker determinístico (pesos fixos) + diversity penalty; budget-aware.
- Ambos opt-in via env; default = comportamento atual.
- Aproveitar o entity graph e o fact/triple existentes para as vozes graph/fact.

---

## 5. Fora de Escopo

- Re-rank neural.
- Substituir modos `semantic`/`hybrid`/`ranked`.
- Composite scoring #55 (upstream; esta RFC soma, não substitui).

---

## 6. Critérios de Aceite

- [ ] Weibull por tipo aplicado; preferência decai mais devagar que evento; tipo sem parâmetro cai no exponencial atual.
- [ ] Polyphonic combina 4 vozes com re-rank determinístico + diversity penalty.
- [ ] Ambos opt-in; default = retrieval atual intacto.
- [ ] Deltas de recall@10/precisão reportados vs baseline PT-BR.
