# Reconciliação Fork ↔ Upstream — mcp-memory-service v11.10.0

**Data da análise:** 2026-09-03
**Analista:** arch-analyst (Kiro subagent)
**Repo:** `/home/claudio/git/mcp-memory-service`
**Upstream:** `v11.10.0` (Codeberg doobidoo, líder) + espelho GitHub
**Fork:** filhocf (Codeberg/GitHub)
**Método:** leitura de código + `git log` — read-only, sem modificação de código.

> Escopo: reconciliar o que já subiu ao upstream vs o que falta transportar do fork,
> após ~2 meses de afastamento. Cada afirmação abaixo cita `arquivo:linha`.

---

## Verificação dos dados de partida

| Dado de partida | Verificado? | Evidência |
|-----------------|-------------|-----------|
| Remotes: upstream=CB doobidoo, upstream-gh=GH doobidoo, codeberg/github=fork | ✅ | `git remote -v` |
| Branch `backup/main-fork-2026-09-02` preserva 29 commits | ✅ | `git log backup/... ^upstream/main --oneline` = **29** commits |
| `main` resetado para upstream/main (v11.10.0) | ✅ | `git describe` = `v11.10.0-15-ge5155b93`; `pyproject.toml` version = `11.10.0` |
| Ponto de fork (merge-base) | ✅ NOVO | `8e69f4fc feat(i18n): locale-aware NER + NLI via YAML plugins (#54)` (2026-07-26) |
| Tracker REFERENCE §12 desatualizado (diz v11.5.2, 22 PRs) | ✅ | `REFERENCE-MEMORY-PIPELINE.md:487` "Atualizado 20/jul/2026 … Upstream v11.5.2". Upstream real agora **v11.10.0**. |

**Nota crítica:** a branch `backup/main-fork-2026-09-02` NÃO nasceu de v11.5.2. Seu merge-base
com upstream é `8e69f4fc` (#54 locale-aware NER, 26/jul/2026), que é **posterior** ao v11.5.2.
Ou seja, boa parte do trabalho do fork (locale NER via YAML) **já entrou** no upstream via #54.
Isso muda materialmente a leitura do gap.

---

## A. MULTI-STORE (#62) no v11.10.0 — PRESENTE e MADURO (partição real)

O conceito de `store` **não é apenas parâmetro de tool** — é **partição real** com coluna
dedicada nas duas tabelas e partition key no índice vetorial.

**Schema (partição real):**
- `storage/mixins/migrations.py:329` → `ALTER TABLE memories ADD COLUMN store TEXT DEFAULT 'default'`
- `storage/mixins/migrations.py:288-291` → `CREATE VIRTUAL TABLE memory_embeddings USING vec0(content_embedding FLOAT[...] , store TEXT partition key)` — **partition key nativo do sqlite-vec (vec0)**
- `storage/mixins/migrations.py:305` → log "Multi-store migration complete: %s embeddings migrated"

**Escrita (store viaja até o INSERT):**
- `storage/mixins/store.py:83` → `async def store(self, memory, skip_semantic_dedup=False, store='default')`
- `storage/mixins/store.py` (INSERT memories) → coluna `store` no INSERT; `INSERT INTO memory_embeddings (rowid, content_embedding, store)`
- `storage/mixins/store.py:187` → `store_batch(..., store='default')` idem

**Leitura (retrieve aceita store na maioria dos backends):**
- `storage/mixins/retrieve.py:40` → `retrieve(..., store: Optional[str] = 'default')` (sqlite-vec)
- `storage/hybrid.py:1426` / `storage/cloudflare.py:713` / `storage/milvus.py:1611,2497` → todos aceitam `store`
- `storage/base.py:113` → assinatura abstrata **NÃO** tem `store` (ainda) ⚠️
- `storage/http_client.py:149` → **NÃO** tem `store` (ainda) ⚠️
- `count_all_memories(..., store='default')` em hybrid.py:1765, cloudflare.py:2219

**Tools (store exposto como parâmetro em várias tools):**
- `tools/registry.py:99-101,162-164,307-309,383-385,458-460,760-762,1327,1387` →
  `"store": {... "description": "Target store partition (default: 'default'). Use 'docs' for documents, 'all' for cross-store search."}`
- Suporta `store="all"` para **federation** (busca cross-store), conforme a spec.

**Conclusão A:** #62 está **PRESENTE como partição real** (coluna em `memories`, partition key
em `memory_embeddings`, parâmetro em store/retrieve/count e nas tools). A federação (`store="all"`)
já é anunciada nas tools. Ressalva: `base.py` (assinatura abstrata) e `http_client.py` ainda
não têm `store` em `retrieve` — daí a defensiva por `inspect.signature` (ver seção C).

---

## B. NER PLUGGABLE (#107) no v11.10.0 — PRESENTE (DomainExtractor via env var)

O mecanismo do #107 existe integralmente em `reasoning/entities.py`:

- `reasoning/entities.py:22-30` → `class DomainExtractor(Protocol)` com `def extract(self, content, metadata=None) -> list[Entity]`
- `reasoning/entities.py:47-49` → `EntityExtractor.__init__(self, domain_extractors=None)` (injeção por construtor)
- `reasoning/entities.py:110-155` → `load_domain_extractors()` lê `MCP_ENTITY_EXTRACTOR_MODULES`
  (formato `pkg.mod:Classe,outro.mod:Classe`), importa, valida `isinstance(instance, DomainExtractor)`, cacheia
- `reasoning/entities.py:157-166` → `get_domain_extractors()` (cache module-level `_DOMAIN_EXTRACTOR_CACHE`)
- `reasoning/entities.py:84-90` → termos custom globais via `MCP_ENTITY_CUSTOM_TERMS`
  (`from ..config import MCP_ENTITY_CUSTOM_TERMS`), match com word-boundary
- `config/quality.py:73-74` → `MCP_ENTITY_CUSTOM_TERMS = os.environ.get("MCP_ENTITY_CUSTOM_TERMS", "")`

Além do #107, o merge-base do fork (`8e69f4fc`, #54) trouxe **locale-aware NER/NLI via YAML plugins**:
- `extraction/ner_patterns/{en,pt_BR}.yaml`, `reasoning/nli_patterns/{en,pt_BR}.yaml` (patterns por locale)
- `extraction/multilingual.py`

**Conclusão B:** #107 (DomainExtractor plugável via `MCP_ENTITY_EXTRACTOR_MODULES`) está
**PRESENTE e funcional**. Também está presente o NER/NLI locale-aware por YAML (#54). O que
existe hoje: (1) patterns high-precision (@,#,url,path); (2) tags de metadata; (3) termos custom
**globais** (`MCP_ENTITY_CUSTOM_TERMS`); (4) extractors de domínio plugáveis por env var.

---

## C. GAP CENTRAL — `store` NÃO chega até a extração de entidades: AUSENTE

Rastreamento de **todos os callers** de `extract_entities` (grep):

| Caller | Linha | Assinatura da chamada | Passa `store`? |
|--------|-------|----------------------|----------------|
| `services/memory_service.py` | :771 | `extractor.extract_entities(memory.content, memory.metadata)` | ❌ |
| `server/handlers/graph.py` | :159 | `extractor.extract_entities(content, metadata)` | ❌ |
| `server/handlers/quality.py` | :568 | `extractor.extract_entities(content, extraction_input)` | ❌ |
| **Definição** | `reasoning/entities.py:51` | `def extract_entities(self, content, metadata=None)` | **não tem parâmetro `store`** |

O método `extract_entities` do upstream **não recebe `store`** e **nenhum** dos 3 callers o
propaga. Não existe `store_terms.json` nem `_load_store_terms` em lugar nenhum do código:
- grep por `store_terms|_load_store_terms` → **0 ocorrências em `src/`** (só `MCP_ENTITY_CUSTOM_TERMS`).

**Sinal explícito de que o scoping ainda não chegou ao retrieve** (comentário do próprio upstream):
- `server/handlers/graph.py:625-633` → wrapper `_retrieve_candidates` que passa `store` **só se**
  `inspect.signature(storage.retrieve)` tiver o parâmetro:
  > *"Passes `store` only if the active backend's `retrieve` accepts it, so this composes the
  > moment multi-store scoping reaches the retrieve path (#62) without breaking on backends that
  > do not yet support it."*
- `tools/registry.py:1282` → *"Read-only. Composes with `store` for multi-store scoping."*

Ou seja: o upstream **reconhece que o scoping por store ainda está em transição** — a
infraestrutura de partição existe (seção A), mas o `store` **ainda não é propagado até o ponto
de extração de entidades** nem uniformemente até o retrieve de todos os backends.

**Conclusão C:** a integração **store → entity-extraction** está **AUSENTE** no v11.10.0.
A partição de armazenamento existe (A) e o extractor plugável existe (B), **mas os dois não se
tocam**: `extract_entities` não conhece o `store` de destino, logo não há como aplicar
vocabulário por store no momento do `memory_store`. Este é exatamente o gap que a spec
`multi-store-domain-ner-spec.md` propõe fechar.

---

## D. Fork (store no extract_entities + store_terms.json) vs Upstream (DomainExtractor via env)

**Abordagem do fork (branch backup):**
- `extract_entities(content, metadata, store='default')` + `_load_store_terms(store)` lendo
  `data/store_terms.json` no formato `{store: {locale, terms[]}}` (spec §Vocabulário per-Store).
- Commits: `a5ba6c72 feat(entities): per-store domain terms`, `f1ed2596 feat(data): add docs-shared store`,
  `4358c29b feat(ner): PT-BR + EN DomainExtractors` — este **superseded** por
  `6bc9561e chore: remove superseded domain_pt_br.py + domain_en.py` (o próprio fork já abandonou
  os extractors hardcoded em favor do mecanismo plugável).

**Abordagem do upstream (v11.10.0):**
- `DomainExtractor` Protocol + `MCP_ENTITY_EXTRACTOR_MODULES` (classes plugáveis) + `MCP_ENTITY_CUSTOM_TERMS`
  (lista **global**, flat, sem noção de store). `extract_entities(content, metadata)` sem `store`.

**Diagnóstico:** a feature do fork é do tipo **(ii) absorvida de forma diferente/incompatível — parcial**:
- O **conceito extensível** (NER plugável) foi **absorvido** (via #107 DomainExtractor + #54 locale YAML).
- A **granularidade por store** (vocabulário per-store aplicado no momento do store) está **AUSENTE**:
  o upstream só tem termos globais (`MCP_ENTITY_CUSTOM_TERMS`), exatamente o problema que a spec
  descreve ("CAR" na curadoria vira link falso com Cadastro Ambiental Rural — spec §Problema).
- A assinatura `extract_entities(..., store=...)` do fork é **incompatível** com a do upstream
  (que padronizou em Protocol + env var). Reaplicar o patch do fork cru causaria divergência.

**Caminho de menor atrito (respeitando o mecanismo do upstream):**

1. **Implementar um `StoreTermsExtractor(DomainExtractor)`** — uma classe que satisfaz o Protocol
   `reasoning/entities.py:22`, lê `store_terms.json` (`{store:{locale,terms[]}}`) e, no `extract`,
   filtra pelos termos do store ativo. Zero mudança na assinatura pública do upstream.

2. **Levar o `store` até o extractor** — o gap real (seção C). Duas opções, em ordem de atrito:
   - **(preferida) via metadata:** injetar `store` dentro do `metadata` que já é passado a
     `extract_entities` (os 3 callers já têm o `store`/memory em mãos: `memory_service.py:771`,
     `graph.py:159`, `quality.py:568`). O `StoreTermsExtractor.extract(content, metadata)` lê
     `metadata.get('store')`. **Não altera a assinatura** — máxima compatibilidade, é a rota que
     o Protocol do upstream já habilita.
   - **(alternativa) evoluir a assinatura:** adicionar `store` opcional a `extract_entities` e ao
     Protocol. Maior atrito (toca contrato público + os 3 callers + testes) e contraria a defensiva
     `inspect.signature` que o upstream adotou justamente para evitar breaking changes.

3. **Registrar via env var** — `MCP_ENTITY_EXTRACTOR_MODULES=mcp_memory_service.extraction.store_terms:StoreTermsExtractor`
   e um caminho configurável para o JSON. Assim o vocabulário per-store vira "plugin zero" do #54,
   como a própria spec previu (§Sequenciamento passo 2).

4. **Fechar o retrieve** (opcional, escopo #57/#62 federation): adicionar `store` a
   `base.py:113` e `http_client.py:149` para o `_retrieve_candidates` (graph.py:625) parar de
   depender da introspecção — mas isto é feature separada, não bloqueia D.

Resumo: **não reaplicar o patch do fork**; **reescrever como `DomainExtractor`** que lê
`store_terms.json`, e **propagar `store` via `metadata`** (rota sem breaking change).

---

## E. Os 29 commits do fork — classificação

`git log backup/main-fork-2026-09-02 ^upstream/main --oneline` (mais recente → mais antigo).
Legenda: **JÁ-NO-UPSTREAM** (conceito absorvido) · **AUSENTE-TRANSPORTÁVEL** (falta e vale PR) ·
**FORK-ONLY** (não vai pro upstream).

> Nota: como o merge-base é `8e69f4fc` (#54), o upstream já contém #54/#107. Muitos commits do
> fork são refinamentos ou trabalho local que não precisam voltar.

| # | Commit | Classificação | Racional |
|---|--------|---------------|----------|
| 1 | `15820dda chore: publish codebase-memory index` | FORK-ONLY | Artefato/índice local (52K nodes). Não é código do produto. |
| 2 | `7d4c8dec fix(harvest): fallback path sessions root` | AUSENTE-TRANSPORTÁVEL | Fix de descoberta de sessões CLI+IDE. Candidato a PR pequeno. |
| 3 | `d017a1d4 feat(harvest): support Kiro IDE session format` | AUSENTE-TRANSPORTÁVEL | Parser `messages.jsonl` do Kiro IDE (`tests/test_kiro_ide_parser.py`). Feature — precisa OK Henry. |
| 4 | `b152a066 fix: resolve merge conflict server_impl.py` | FORK-ONLY | Resolução de conflito local, sem valor upstream. |
| 5 | `6bc9561e chore: remove superseded domain_pt_br/en.py` | FORK-ONLY | Limpeza interna (abandonou extractors hardcoded). |
| 6 | `bde5bf43 fix(ner): min 3 chars contextual uppercase` | AUSENTE-TRANSPORTÁVEL | Fix anti-falso-positivo ('de'). Pequeno, bom candidato. |
| 7 | `4358c29b feat(ner): PT-BR + EN DomainExtractors` | JÁ-NO-UPSTREAM (supersedido) | Conceito coberto por #107 + #54; o próprio fork removeu (commit 5). |
| 8 | `2e1978d5 feat: RFC-MM-01/02/03 gap/fact/feedback` | AUSENTE-TRANSPORTÁVEL | Features grandes (gap-detection, fact-extraction, feedback-loop) + testes (`test_gap_detection`, `test_fact_extraction`, `test_feedback_loop`). Precisa OK Henry (#67). |
| 9 | `00e9bdec docs: AGENTS.md link REFERENCE` | FORK-ONLY | Doc do fork. |
| 10 | `e5d9a794 docs: AGENTS.md fork workflow rules` | FORK-ONLY | Regras de workflow do fork (3-machine). |
| 11 | `0445eb02 feat(bootstrap): semantic search + noise filter` | FORK-ONLY | Marcado "(fork-only)" no próprio título. |
| 12 | `14b8adca feat(bootstrap): specificity filter + belief ranking` | FORK-ONLY | Marcado "(fork-only)". |
| 13 | `9438623f chore(fork): remove session-miner` | FORK-ONLY | Limpeza local. |
| 14 | `ad17ff34 feat(harvest): wire rewrite_batch 10-20x fewer LLM (#104)` | AUSENTE-TRANSPORTÁVEL | Otimização citando #104. `tests/test_harvest_rewrite_batch.py`. Bom candidato. |
| 15 | `53584bf6 feat(harvest): per-session tracker (#104)` | AUSENTE-TRANSPORTÁVEL | `tests/test_harvest_tracker.py`. Pareado com #14. |
| 16 | `5a932f75 test: xfail belief promotion test` | FORK-ONLY | Ajuste de teste local (noise filter). |
| 17 | `2ccd5778 [T'Pol] cleanup: remove 8 originais consolidados` | FORK-ONLY | Curadoria de docs local. |
| 18 | `fc213d50 [T'Pol] docs: consolidar RFCs em docs/rfc/` | FORK-ONLY | Docs/RFC do fork. |
| 19 | `b0803dd5 [T'Pol] cleanup: remover ANALISE.md e sdd/plans/` | FORK-ONLY | Docs local. |
| 20 | `35a32e01 [T'Pol] docs: preservar RFCs do fork` | FORK-ONLY | RFCs do fork (autolearn, autodream, etc). |
| 21 | `046cc5ca test(e2e): belief pipeline + NLI + memory_context` | AUSENTE-TRANSPORTÁVEL (parcial) | Testes EN+PT-BR. Úteis se as features associadas forem PR. |
| 22 | `cd86a4cb fix: self.storage BeliefService bootstrap_profile` | AUSENTE-TRANSPORTÁVEL | Bugfix pequeno. Candidato. |
| 23 | `775fc41d fix: memory_context dict access + beliefs` | JÁ-NO-UPSTREAM (provável) | REFERENCE §12 diz #120 memory_context dict bug resolvido em v11.5.0. Verificar duplicidade antes de PR. |
| 24 | `c097c1e7 test(memory_context): 4 unit tests` | AUSENTE-TRANSPORTÁVEL (parcial) | `tests/test_memory_context.py`. Acompanha #23. |
| 25 | `ff28cac4 feat(nli): LLM backend via harvest provider chain` | AUSENTE-TRANSPORTÁVEL | NLI cascade multi-provider. REFERENCE §12 marca como candidato ao **#116**. Melhor candidato a PR. |
| 26 | `53dc9559 feat(retrieve): temporal decay on relevance_score` | JÁ-NO-UPSTREAM (provável) | #123 temporal decay mergeada v11.5.0 (REFERENCE §12). Verificar se o do fork é além do mergeado. |
| 27 | `f1ed2596 feat(data): add docs-shared store + update store model` | AUSENTE-TRANSPORTÁVEL | Faz parte da feature multi-store-domain-NER (seção D). Transportar junto com o StoreTermsExtractor. |
| 28 | `a5ba6c72 feat(entities): per-store domain terms` | AUSENTE-TRANSPORTÁVEL | **O gap central da seção C/D.** Reescrever como DomainExtractor + store via metadata. |
| 29 | `2e39fafd docs: RFC config audit findings` | FORK-ONLY | Doc/RFC do fork. |

**Contagem:** FORK-ONLY = 13 · AUSENTE-TRANSPORTÁVEL = 13 · JÁ-NO-UPSTREAM = 3 (dois "prováveis"
a confirmar: #23, #26; um supersedido: #7).

---

## Tabela-resumo final

| Item | Estado no v11.10.0 | Evidência-chave | Ação |
|------|--------------------|-----------------|------|
| A. Multi-store #62 (partição) | **PRESENTE (partição real)** | `migrations.py:288-291,329`; `store.py:83,187`; `retrieve.py:40`; `registry.py:99-101` | Nada — usar. Opcional: `store` em `base.py:113`/`http_client.py:149`. |
| B. NER plugável #107 | **PRESENTE** | `entities.py:22-30,47-49,110-166`; `config/quality.py:73-74` | Nada — reusar mecanismo. |
| B'. NER locale YAML #54 | **PRESENTE** (é o merge-base do fork) | merge-base `8e69f4fc`; `ner_patterns/*.yaml` | Nada. |
| C. store → entity-extraction | **AUSENTE** | `entities.py:51` sem `store`; 3 callers sem `store`; `graph.py:628` "the moment scoping reaches…"; 0 `store_terms` | Fechar o gap (seção D). |
| D. Vocabulário per-store (fork) | **AUSENTE / absorvido diferente** | só `MCP_ENTITY_CUSTOM_TERMS` global | `StoreTermsExtractor(DomainExtractor)` + `store` via metadata. |
| E. NLI LLM cascade (#116) | AUSENTE-TRANSPORTÁVEL | commit `ff28cac4` | Melhor candidato a PR (Henry já sinalizou #116). |
| E. Harvest rewrite_batch/tracker (#104) | AUSENTE-TRANSPORTÁVEL | commits `ad17ff34`,`53584bf6` | Candidatos a PR de perf. |
| E. Kiro IDE session parser | AUSENTE-TRANSPORTÁVEL | commit `d017a1d4` | PR (feature — OK Henry). |
| Tracker REFERENCE §12 | **DESATUALIZADO** (v11.5.2/20-jul) | `REFERENCE-...md:487` | Atualizar p/ v11.10.0. |

---

## Recomendação — próximos passos (ordem de menor atrito / maior valor)

- **Atualizar o tracker REFERENCE §12** para v11.10.0 antes de qualquer PR: o merge-base do fork
  é #54 (26/jul), logo #54/#107/#62 já estão no upstream; a lista "5 issues abertas / 22 PRs" está
  obsoleta. Isto evita propor de novo algo já mergeado (#7 supersedido, #23/#26 prováveis-duplicados).

- **Fechar o gap C/D com um PR único e cirúrgico**: criar `StoreTermsExtractor(DomainExtractor)`
  que lê `store_terms.json` e propagar `store` **via `metadata`** nos 3 callers
  (`memory_service.py:771`, `graph.py:159`, `quality.py:568`). Sem alterar a assinatura pública —
  é a rota que o Protocol do #107 e a defensiva `inspect.signature` do upstream já habilitam.
  Reaproveitar o commit `a5ba6c72` reescrito (NÃO cherry-pick cru) + `f1ed2596` (docs-shared).

- **Oferecer o NLI LLM cascade (`ff28cac4`) como PR do #116**: o REFERENCE já identificou #116 como
  candidato aberto; é a contribuição de maior probabilidade de aceite. Escopo mínimo, 1 feature = 1 PR.

- **Agrupar os fixes pequenos transportáveis** em PRs independentes e de baixo risco:
  `bde5bf43` (min 3 chars NER), `cd86a4cb` (BeliefService bootstrap), `7d4c8dec` (harvest fallback path).
  Cada um sem depender de decisão de roadmap do Henry.

- **NÃO transportar os 13 FORK-ONLY** (bootstrap fork-only, docs [T'Pol]/RFC, cleanups, índice
  codebase-memory). E confirmar via `git log`/diff no upstream se `775fc41d` (memory_context) e
  `53dc9559` (temporal decay) já estão cobertos por #120/#123 antes de abrir qualquer PR — provável duplicidade.

---

*Análise read-only. Nenhum arquivo de código foi modificado. Evidências por `arquivo:linha` verificadas em `git describe = v11.10.0-15-ge5155b93`.*
