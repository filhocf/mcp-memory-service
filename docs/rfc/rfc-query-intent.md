# RFC: Query Intent Classification (ajuste de pesos por intenção)

**Data:** 2026-09-13
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `feat/query-intent` (a partir de `upstream/main`)
**Base:** `upstream/main` v11.11.0
**Versão:** 0.1 (draft)
**Inspiração:** Mnemosyne `query_intent.py` (classificação regex → ajuste vetor/FTS)
**Reintegra:** —
**Status:** DRAFT — amadurecer localmente antes de virar issue/RFC para o Henry

---

## 1. Problema

O retrieval usa pesos fixos entre similaridade vetorial e busca por palavra-chave (FTS), independentemente do tipo de pergunta. Uma query temporal ("o que aconteceu semana passada") e uma factual ("qual a senha do banco") têm necessidades opostas, mas recebem o mesmo balanceamento.

### Evidências

- O `memory_search` oferece modos (`semantic`/`hybrid`/`ranked`) mas o balanceamento vetor×FTS não se adapta ao tipo de query dentro do modo hybrid.
- Consultas temporais e de entidade ("o que Denis prefere") se beneficiam de mais FTS/entity; consultas procedurais ("como faço deploy") se beneficiam de mais semântica.
- Mnemosyne classifica a intenção por regex (temporal/factual/entity/preference/procedural/general) e ajusta os pesos — ganho barato, determinístico, sem tocar schema.

### Causas

1. **Peso fixo.** O hybrid usa uma proporção constante vetor/FTS.
2. **Sem sinal de intenção.** Nada inspeciona a query para inferir o que o usuário quer.

### Risco

Baixo. É uma melhoria de precisão de retrieval, não um risco estrutural. O custo de não fazer é retrieval subótimo em classes de query específicas.

---

## 2. Objetivo

Classificar a intenção da query (rule-based, zero LLM) e ajustar os pesos vetor/FTS/importância/recência por classe, dentro do modo hybrid.

**Não-objetivos:** classificação por LLM; alterar o schema; mudar os modos existentes.

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1).

### Funcional

**R1**: A query é classificada em uma intenção conhecida.

> EARS: WHEN a hybrid search runs, THE system SHALL classify the query into one of {temporal, factual, entity, preference, procedural, general} using rule-based patterns.

**R2**: Os pesos de scoring são ajustados pela intenção.

> EARS: WHEN a query is classified, THE system SHALL adjust the vector/FTS/importance/recency weights according to the intent profile.

**R3**: A intenção default preserva os pesos atuais.

> EARS: WHERE the intent is `general` or unrecognized, THE system SHALL use the current default weights.

**R4**: A classificação suporta PT-BR e EN.

> EARS: WHEN a query is in Portuguese or English, THE classifier SHALL recognize the temporal/factual/entity/preference/procedural cues in both languages.

### Não-Funcional

**R5**: A classificação é determinística e barata.

> EARS: THE intent classification SHALL run without any network or LLM call and add negligible latency.

**R6**: O ajuste é observável.

> EARS: WHERE debug is enabled, THE system SHALL report the detected intent and the applied weights.

---

## 4. Design

- `query_intent.py`: `classify_intent(query) -> Intent` (regex bilíngue PT/EN) + `adjust_weights(intent, base_weights) -> weights`.
- Integração no caminho hybrid do `memory_search` (antes do scoring).
- Perfis de peso por intenção (tabela configurável): temporal→+FTS/+recência; entity→+entity/+FTS; preference→+importância/−recência; procedural→+vetor/−recência.

---

## 5. Fora de Escopo

- Classificação por LLM (rule-based é suficiente e barato).
- Novos modos de busca.
- Reordenação multi-estratégia (ver possível RFC polyphonic recall).

---

## 6. Critérios de Aceite

- [ ] Query temporal/entity/preference/procedural é classificada corretamente em PT e EN.
- [ ] Pesos ajustados por intenção; `general` mantém default.
- [ ] Zero chamada de rede/LLM; latência adicional desprezível.
- [ ] Debug reporta intenção + pesos aplicados.
