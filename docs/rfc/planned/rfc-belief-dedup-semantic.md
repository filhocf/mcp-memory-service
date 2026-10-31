# RFC: Dedup semântico de beliefs (embedding belief↔belief)

**Data:** 2026-10-31
**Autor:** Zero (Manager + Client do mms) — G0 por Seven (arquiteto)
**Status:** DRAFT v0.1 — G0 fechado (desenho medido), pronto para G3 (RED)
**Arco:** ARCO SÍNTESE / higiene de corpus de beliefs (irmã de `rfc-belief-synthesis.md`)
**Relacionadas:** PR #1727 (meta-ruído no `_is_noise` — contaminante #1); item Orc `8d99cb9f`.
**Código existente:** `consolidation/belief_service.py` — `sweep_degenerate_beliefs` (precedente
de sweep flag-gated), `_create_belief`/`_compute_belief_embedding` (coluna `beliefs.embedding`,
migração 021), `_find_belief_by_provenance` (stable-identity por `derived_from`), `_update_belief`.

---

## 1. Problema

Investigação do corpus de beliefs (31/out, mem `be32aea0`) fechou o arco 14/out medindo DUAS
raízes do gargalo de recuperação. A raiz **A (cobertura)** foi resolvida pelo R1 ontologia; a
raiz **B (precisão do topo)** tem dois contaminantes:

1. **Meta-ruído** — `[GAP]/[PATTERN]/[TREND]/[MINED:]` + estatísticas de tag. **RESOLVIDO** pelo
   PR #1727 (`_is_noise` rejeita na derivação + `_is_meta_statistic` exclui na leitura) e pelo
   purge de 422 beliefs (4053→3631).
2. **Duplicação semântica** — a MESMA lição re-derivada em sessões diferentes vira N beliefs com
   conteúdo quase-idêntico, fraseado distinto. **ESTE é o alvo desta RFC.**

### Medição (corpus vivo, 31/out)
- 151 grupos de prefixo-55 idêntico; 51 com 3+ membros; ~398 beliefs = **~13%** do corpus
  active+candidate.
- Piores: "Post/PR no GitHub sempre EN+PT-BR com OK do Claudio" = **13 variantes**; "antes de
  abrir PR verificar colisão" = **12 variantes**.
- **0 byte-idênticos** — são variações, não cópias literais.
- **Descartado por medição:** `MCP_BELIEF_STABLE_IDENTITY` (overlap de `derived_from` ≥0.6)
  colapsaria só **12/151** grupos, porque cada variante tem fonte distinta (uma memória-fonte
  por sessão). Dedup por proveniência NÃO resolve. **Precisa ser por SIMILARIDADE DE EMBEDDING.**

O impacto: duplicatas ocupam vagas do top-k da injeção que deveriam ser conhecimento único —
rich-get-richer semântico.

## 2. Proposta

Um passo de consolidação **separado** `dedup_beliefs()`, modelado no precedente exato
`sweep_degenerate_beliefs` (flag-gated, cap, supersede-não-delete, per-row try/except). NÃO na
derivação (slice posterior) — o que resolve o backlog de 151 grupos já no banco é um sweep.

- **Similaridade:** cosseno sobre o BLOB `beliefs.embedding` JÁ persistido (migração 021). Não
  recomputar. Beliefs sem embedding (NULL) são pulados (não deduplicáveis por este caminho).
- **Threshold:** `MCP_BELIEF_DEDUP_THRESHOLD=0.90` — mais estrito que o 0.85 de observations,
  porque o custo de um falso-positivo aqui é fusão destrutiva de dois beliefs distintos.
- **Canônico (determinístico):** maior `confidence` → maior `|derived_from|` → `updated_at` mais
  recente → `belief_hash` (tie-break estável). `utility_prior` NÃO entra no critério (evita
  rich-get-richer: o mais-usado não vence por ser mais usado).
- **Merge preservando sinal** (`_merge_into_canonical`, transação única): une
  `derived_from`/`contradicted_by` dos perdedores no canônico, RECOMPUTA `utility_prior` a partir
  dos contadores agregados (nunca soma de proporções nem max), soma os feedback counters, mantém
  o `confidence` do canônico, e SÓ ENTÃO marca os perdedores como `superseded` (não deleta).
- **Flag:** `MCP_BELIEF_DEDUP` default OFF (padrão do fork); `+_THRESHOLD`, `+_CAP` (anti-flood),
  `+_SCHEDULE` (quando B.2c).
- **Dry-run obrigatório** (B.2a): mede sem escrever — nº de grupos (151→X), redução de active
  (~−13%), e serve para corroborar os números ao Henry ANTES de qualquer PR (muda ranking de todos).

## 3. Fatiamento (empilha — não é 1 PR)

- **B.2a — dry-run read-only:** `dedup_beliefs(dry_run=True)` detecta os grupos e RELATA (sem
  escrever). Risco zero, G3 RED limpo, corrobora os números. **Esta RFC entrega o B.2a.**
- **B.2b — apply:** `_merge_into_canonical` + supersede em transação. Fork-only, maturar no vivo.
- **B.2c — scheduler/prevenção:** job periódico + (opcional) dedup na derivação.

## 4. Requisitos (EARS)

- **R1** — THE belief_service SHALL expor `dedup_beliefs(dry_run: bool)` que, quando
  `MCP_BELIEF_DEDUP` está desabilitado, retorna `{"evaluated": 0, "groups": 0}` sem ler o corpus
  (byte-idêntico ao comportamento atual: nenhum efeito colateral).
- **R2** — WHEN `MCP_BELIEF_DEDUP` está habilitado AND `dedup_beliefs(dry_run=True)` é chamado,
  THE belief_service SHALL agrupar beliefs active/candidate cuja similaridade de cosseno sobre
  `beliefs.embedding` seja ≥ `MCP_BELIEF_DEDUP_THRESHOLD`, SEM escrever no banco.
- **R3** — THE belief_service SHALL pular beliefs cujo `embedding` seja NULL (não deduplicáveis
  por embedding), contando-os em `skipped` no relatório.
- **R4** — WHEN um grupo de duplicatas é detectado, THE belief_service SHALL eleger o canônico por
  `confidence` desc, depois `|derived_from|` desc, depois `updated_at` desc, depois `belief_hash`
  — determinístico e independente de `utility_prior`.
- **R5** — THE belief_service SHALL respeitar `MCP_BELIEF_DEDUP_CAP` (default 1000), interrompendo
  após esse número de grupos e sinalizando `capped: true` no relatório.
- **R6** — THE dry-run SHALL NÃO alterar `status`, `content`, `metadata` nem contagem de nenhum
  belief (verificável: contagem total e por-status idênticas antes/depois).

## 5. Blast radius / risco

- Muda o ranking de TODOS os consumidores de belief (injeção, `get_beliefs`) — Henry corrobora
  os números (dry-run) ANTES de PR. Fork-first.
- Interage com `stable-identity`: o dedup é mais eficaz com `MCP_BELIEF_STABLE_IDENTITY` ON (evita
  ressurreição de duplicata na re-derivação).
- Guardas: `embedding` NULL/dim≠384; atomicidade do merge (supersede sem migrar sinal = perda
  permanente — por isso transação única em B.2b).
- B.2a (esta fatia) é read-only → risco de dados ZERO.

## 6. Critério de aceite

Dry-run relata, no corpus vivo, ≥ 50 grupos com 2+ membros (medição 31/out: **208 grupos,
459 beliefs colapsáveis, −15%**). Testes G3 cobrem R1–R6 + guard de apply (B.2b NotImplementedError)
+ estabilidade de ordem, com fixtures sintéticas (embeddings controlados), incluindo flag-OFF (R1)
e embedding-NULL (R3). 10 testes, suíte belief 214 passed.

## 7. Nota de performance (medida 31/out, G5 tuvok P3)

O agrupamento é O(n²) em Python puro sobre active+candidate (3058 beliefs no vivo),
com cosseno sobre 384 dims por par. Medido: o sweep completo sem cap estoura 120s —
**aceitável para B.2a (dry-run manual, offline, não hot-path)**, mas o **B.2b/B.2c
devem usar o KNN nativo do sqlite-vec** (`vec0`/MATCH) em vez do laço O(n²), ou um cap
operacional. Prova funcional com `MCP_BELIEF_DEDUP_CAP=20`: 20 grupos, 103 colapsáveis,
`capped=true` — o cap corta corretamente. Não wired em nenhum caminho de request (só
sob flag, chamada manual).

## 8. Grouping é aproximação (greedy single-linkage)

Cada belief posterior é testado contra o SEED do grupo, não contra todos os membros —
uma cadeia A~B, B~C com A≁C agrupa {A,B} e deixa C singleton. É intencional (não
clustering exato). Estável entre execuções porque o SELECT é `ORDER BY belief_hash`
(sem isso, a contagem dependeria da ordem física das linhas — SQLite não garante ordem).
A eleição do canônico (R4) é determinística DENTRO do grupo.
