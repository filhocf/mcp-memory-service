# RFC: Persona Tier (identidade portável auto-gerada)

**Data:** 2026-09-13
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `feat/persona-tier` (a partir de `upstream/main`)
**Base:** `upstream/main` v11.11.0
**Versão:** 0.1 (draft)
**Inspiração:** Mnemosyne `persona.py` (extração rule-based → persona.md) + `canonical.py` (SSOT facts)
**Reintegra:** —
**Status:** DRAFT — amadurecer localmente antes de virar issue/RFC para o Henry

---

## 1. Problema

A identidade do agente (nome, tom, voz, fatos estáveis de si) vive hoje em arquivo de steering do harness (`persona.md`, mantido à mão). Isso acopla a identidade ao harness: trocar de harness (Kiro → opencode, p.ex.) exige recriar a persona, e a persona não evolui a partir das memórias.

### Evidências

- Nossa persona ("Zero") é um `persona.md` estático no steering do Kiro — escrito manualmente, versionado no ai-configs, não derivado das memórias.
- O bootstrap profile que já temos é **comportamental** (o que evitar, decisões consolidadas) — não é *identidade* (quem o agente é, como fala).
- Mnemosyne extrai a persona das memórias já classificadas (fontes `preference`/`persona`/`stated`, importância ≥0.7), rule-based, zero LLM no default; e mantém um canonical store de fatos "fonte única da verdade" com supersessão temporal.

### Causas

1. **Identidade fora do banco.** Persona vive no harness, não na memória — logo não é portável nem auto-atualizada.
2. **Sem canonical store.** Fatos estáveis de identidade ("meu nome é X") não têm garantia de unicidade; restatements acumulam duplicatas e um valor novo coexiste com o velho.

### Risco / motivação estratégica

Se trocarmos de harness, perdemos/recriamos a identidade manualmente. E a persona manual diverge das memórias reais ao longo do tempo. Uma persona derivada do banco é **portável** (Zero continua Zero em qualquer harness) e **consistente** (reconstruída dos próprios fatos).

---

## 2. Objetivo

Derivar e manter a **persona a partir das memórias** (rule-based, zero LLM default), com um **canonical store** para fatos de identidade únicos e versionados, tornando a identidade portável entre harnesses.

**Não-objetivos:** substituir o bootstrap profile comportamental (são complementares); gerar persona por LLM no caminho default; impor persona a quem não quer (opt-in).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1).

### Funcional

**R1**: A persona é extraída de memórias classificadas, sem LLM no caminho default.

> EARS: WHEN persona extraction runs, THE system SHALL derive the persona from memories sourced `preference`/`persona`/`stated` with importance ≥ threshold, using rule-based extraction and no LLM call.

**R2**: A persona é regenerada por gatilhos definidos.

> EARS: WHEN an explicit request, a cold start, a recovery, or a memory-count threshold occurs, THE system SHALL regenerate the persona artifact.

**R3**: Fatos de identidade são canônicos (fonte única).

> EARS: WHEN a canonical identity fact is restated with a new value, THE canonical store SHALL supersede the previous value instead of storing a duplicate.

**R4**: A persona é exportável como artefato portável.

> EARS: WHEN persona export is invoked, THE system SHALL emit a persona document consumable by any harness.

**R5**: A persona é opt-in e complementar ao bootstrap profile.

> EARS: WHERE the persona feature is disabled, THE system SHALL leave the behavioral bootstrap profile unchanged.

### Não-Funcional

**R6**: A extração é determinística.

> EARS: THE default persona extraction SHALL be deterministic and reproducible from the same memory set.

**R7**: O canonical store preserva histórico.

> EARS: WHEN a canonical fact is superseded, THE store SHALL retain the previous value as history rather than deleting it.

---

## 4. Design

- `persona.py`: extração rule-based → artefato (persona.md ou JSON) a partir de memórias `preference`/`persona`/`stated`.
- `canonical.py`: `CanonicalStore` owner-scoped, fatos únicos com `valid_until` (supersessão), reuso do padrão do TripleStore.
- Tools MCP: `persona_get`, `persona_export`, `canonical_set`, `canonical_recall`, `forget_canonical`.
- Gatilhos: request explícito / cold start / recovery / threshold de memórias.
- Complementaridade: bootstrap profile (comportamental) + persona (identidade) = perfil completo do agente.

---

## 5. Fora de Escopo

- Substituir o bootstrap profile comportamental.
- Geração de persona por LLM (opcional, fora do default).
- Multi-agente (RFC de sync).

---

## 6. Critérios de Aceite

- [ ] Persona derivada de memórias classificadas, determinística, zero LLM no default.
- [ ] Regeneração disparada por request/cold-start/recovery/threshold.
- [ ] Canonical fact superseded (não duplicado) ao ser restated; histórico preservado.
- [ ] Persona exportável como artefato consumível por outro harness.
- [ ] Feature off = bootstrap profile intacto.
