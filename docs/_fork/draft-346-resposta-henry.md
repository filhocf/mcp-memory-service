# Draft — comentário para Discussion #346 (aguarda OK do Claudio antes de postar)

> Regra: comunicação externa = draft EN + tradução PT-BR completa + OK do Claudio → só então postar.
> Hook de enforcement bloqueia post sem flag `approved-post`. NÃO postar sem aprovação.

---

## 🇬🇧 VERSÃO EN (para postar na #346)

Great framing — the "map + territory" split is exactly right, and the 70%/30% read matches what I
see in the tree. One thing worth surfacing: on `main`, a good part of Phase 0–2 is **already in the
code**, not just on the roadmap. Pointers so others don't re-implement it:

**Phase 0 (Ontology) — largely present:**
- `models/ontology.py` — `BaseMemoryType` (12 base types), `TAXONOMY` (base→subtypes),
  `RELATIONSHIPS` (8 typed: causes/fixes/contradicts/supports/follows/related/derived_from/shares_entity)
  each with `valid_patterns`, and `SYMMETRIC_RELATIONSHIPS`. `validate_relationship` /
  `is_symmetric_relationship` are enforced at the edge write (`storage/graph.py`, `storage/milvus_graph.py`)
  and in the `Memory` constructor.
- `reasoning/inference.py` — `SemanticReasoner.infer_transitive` (A→B, B→C ⇒ A→C with per-hop decay),
  plus `detect_contradictions` / `find_fixes` / `find_causes`, exposed as MCP via `server/handlers/graph.py`.

**Phase 1 (Quality) — done:** the quality-model arc closed (quality split, retention periods,
`MCP_DECAY_ENABLED`, supersession-orphan fix).

**Phase 2 (Typed Relationships) — done and wired:** `consolidation/relationship_inference.py`
(`infer_relationship_type`, with the #541 typed-confidence/similarity guards and the #546 opt-out) is
called in the consolidation flow (`consolidator.py`) and persisted via `store_association(relationship_type=...)`.
The `relationship_type` column migration is already applied.

**Two honest caveats on Phase 0**, so I don't oversell it:
1. `valid_patterns` exist as *data* but are **not enforced** yet — the edge write validates the type
   name and symmetry, not whether the source→target pair matches the declared pattern. That pattern-
   consistency check is the piece of "reasoning" still missing.
2. `abstract_to_concept` (taxonomy climbing in the reasoner) is still a stub.

**Where I see the real gaps:**
- **Phase 3 (ontology-aware agentic RAG)** — we have the typed edges and the reasoner, but not the
  layer that routes a user's query intent into a graph traversal (e.g. "what caused X" → walk `causes`
  backward). That routing layer is genuinely absent.
- **Phase 4 (RDF/OWL/SKOS/SPARQL)** — zero today; agree it's "nice to have / future".

Separately, I've been actively building a few directions in my fork that are **adjacent to but not
covered by** this proposal — and these are already in code and validated end-to-end, not just design:
- **Learning-loop** — the service observes its own usefulness: usage telemetry (`usage_events`,
  migration 014), proactive context injection by topic (`memory_context` tool), and passive feedback
  that recalibrates `quality_score` from real reaccess instead of a schema we never fill. There's also
  an agent-assertiveness metric (re-query rate / injection coverage / lost-context) to answer "is the
  agent measurably better week over week?". This is the layer *above* the knowledge graph — organizing
  memory is necessary but not sufficient; the goal is to *learn from use*.
- **Per-agent pluggable ingestion** — harvest rules per agent as declarative YAML, with a session
  value-triage gate (drops low-value sessions before storing); 193 tests green.
- **Delta event-log sync** — a bidirectional delta transport for multi-machine (HLC ordering,
  idempotency, per-agent scope), to replace whole-DB file sync.

I think the knowledge-graph vision and the learning-loop are complementary: your ontology makes the
graph *structured*, the learning-loop makes it *earn its place from usage*. Happy to open focused
discussions on any of these if useful to the roadmap.

On your five questions: I'd lean **minimal-first** for ontology scope (types + relationships, which we
largely have), **gradual migration** for namespaces (lazy on access), and treating Phase 4 as future.
The pattern-consistency enforcement (caveat 1) feels like the cheapest high-value next step on the
ontology side.

---

## 🇧🇷 TRADUÇÃO PT-BR (parágrafo a parágrafo — para o Claudio conferir)

Ótimo enquadramento — a divisão "mapa + território" está certíssima, e a leitura de 70%/30% bate com
o que vejo na árvore. Vale levantar uma coisa: na `main`, boa parte das Fases 0–2 **já está no
código**, não só no roadmap. Ponteiros para que ninguém reimplemente:

**Fase 0 (Ontologia) — em grande parte presente:**
- `models/ontology.py` — `BaseMemoryType` (12 tipos base), `TAXONOMY` (base→subtipos),
  `RELATIONSHIPS` (8 tipados: causes/fixes/contradicts/supports/follows/related/derived_from/shares_entity),
  cada um com `valid_patterns`, e `SYMMETRIC_RELATIONSHIPS`. `validate_relationship` /
  `is_symmetric_relationship` são aplicados no write da aresta (`storage/graph.py`,
  `storage/milvus_graph.py`) e no construtor do `Memory`.
- `reasoning/inference.py` — `SemanticReasoner.infer_transitive` (A→B, B→C ⇒ A→C com decay por salto),
  além de `detect_contradictions` / `find_fixes` / `find_causes`, expostos como MCP via
  `server/handlers/graph.py`.

**Fase 1 (Quality) — feito:** o arco do quality-model fechou (split de qualidade, retention periods,
`MCP_DECAY_ENABLED`, fix do supersession-orphan).

**Fase 2 (Relacionamentos tipados) — feito e integrado:** `consolidation/relationship_inference.py`
(`infer_relationship_type`, com os guards de typed-confidence/similaridade do #541 e o opt-out do #546)
é chamado no fluxo de consolidação (`consolidator.py`) e persistido via
`store_association(relationship_type=...)`. A migração da coluna `relationship_type` já está aplicada.

**Duas ressalvas honestas sobre a Fase 0**, para eu não vender além do que é:
1. Os `valid_patterns` existem como *dado* mas **ainda não são enforçados** — o write da aresta valida
   o nome do tipo e a simetria, não se o par source→target bate com o padrão declarado. Essa checagem
   de consistência de padrão é a peça de "reasoning" que ainda falta.
2. `abstract_to_concept` (subir na taxonomia dentro do reasoner) ainda é um stub.

**Onde eu vejo os gaps reais:**
- **Fase 3 (agentic RAG ciente de ontologia)** — temos os edges tipados e o reasoner, mas não a
  camada que roteia a intenção da query do usuário para um traversal no grafo (ex.: "o que causou X"
  → percorrer `causes` para trás). Essa camada de roteamento está genuinamente ausente.
- **Fase 4 (RDF/OWL/SKOS/SPARQL)** — zero hoje; concordo que é "nice to have / futuro".

Em separado, venho construindo ativamente algumas direções no meu fork que são **adjacentes mas não
cobertas por** esta proposta — e já estão no código e validadas de ponta a ponta, não só design:
- **Learning-loop** — o serviço observa a própria utilidade: telemetria de uso (`usage_events`,
  migration 014), injeção proativa de contexto por tema (tool `memory_context`), e feedback passivo
  que recalibra o `quality_score` a partir de reacesso real em vez de um schema que nunca preenchemos.
  Há também uma métrica de assertividade do agente (taxa de re-query / cobertura de injeção /
  perda-de-contexto) para responder "o agente está mensuravelmente melhor semana a semana?". Esta é a
  camada *acima* do grafo de conhecimento — organizar a memória é necessário mas não suficiente; o
  objetivo é *aprender com o uso*.
- **Ingestão plugável por agente** — regras de harvest por agente como YAML declarativo, com um gate
  de triagem de valor de sessão (descarta sessões de baixo valor antes de gravar); 193 testes verdes.
- **Sync por event-log de deltas** — transporte bidirecional de deltas para multi-máquina (ordenação
  HLC, idempotência, escopo por agente), para substituir o sync de banco inteiro por arquivo.

Acho que a visão de grafo de conhecimento e o learning-loop são complementares: sua ontologia deixa o
grafo *estruturado*, o learning-loop faz ele *merecer seu lugar a partir do uso*. Fico à vontade para
abrir discussões focadas em qualquer uma delas, se for útil ao roadmap.

Sobre suas cinco perguntas: eu iria de **mínimo primeiro** no escopo de ontologia (tipos +
relacionamentos, que já temos em grande parte), **migração gradual** para namespaces (lazy no acesso),
e tratar a Fase 4 como futuro. O enforcement de consistência de padrão (ressalva 1) me parece o
próximo passo mais barato e de alto valor no lado da ontologia.

---

## Notas para o Claudio (decisão antes de postar)
- O tom é colaborativo e **credita o Henry** ("ótimo enquadramento"), mas corrige de leve: "já está no
  código, não só no roadmap" — sem soar como "você não conhece seu próprio repo". Posso suavizar ou
  endurecer.
- Mencionei nossos 3 arcos (learning-loop, ingestão, delta-sync) como oferta, não imposição. Se preferir
  NÃO expor o learning-loop ainda (está fork-only, maturando), corto esse parágrafo.
- As duas ressalvas honestas (valid_patterns, stub) nos protegem de prometer demais e mostram rigor.
- **Nada postado.** Aguardando teu OK (e eventual ajuste de tom) para criar a flag `approved-post` e publicar.
