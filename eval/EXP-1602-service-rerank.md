# EXP-1602: service-path reranker validation (spec G0)

## Context

Fork branch `feat/1602-rerank-flag` (rebased, suite green). Deposit-backed scope agreed in
issue #1602 comments (doobidoo, 20/out 15:44Z). Claudio's decision of 21/out: measure
through the SERVICE before opening the PR. This spec is the G0 artifact for that
experiment.

## Trilha (bench bench, frozen)

- Ruler: `eval/recall_cases_v3.json` — 120 cases, document-level metric (`gold_hashes`).
- Candidate dump: `/tmp/cands40.json` (120 × 40, `sha256` recorded in output).
- Index: `paraphrase-multilingual-MiniLM-L12-v2`, acervo pessoal (snapshot copy).
- Reference dump-based numbers (known): base 0.5667 @10 · bge +10.0 p.p. · ms-marco −8.3 p.p.

## Configs (serial, machine solo)

| config | rerank | model |
|--------|--------|-------|
| A base | off | — |
| B ms-marco | on | `Xenova/ms-marco-MiniLM-L-6-v2` `onnx/model_int8.onnx` |
| C bge | on | `Xenova/bge-reranker-base` `onnx/model_int8.onnx` |

- Instance: ephemeral service from the feature branch interpreter, work-copy db.
- Work copy per run (never the snapshot itself; never production db).
- Commit the bge-int8 registration into `SUPPORTED_MODELS` as config data before
  config C (that registration is the only code change beyond the flag).

## Acceptance (all must hold to declare the experiment closed)

1. Config A recall@10 within ±1 p.p. of 0.5667 (sanity: same corpus, same index).
2. Config C recall@10 > config A recall@10.
3. Config B recall@10 < config A recall@10 (reproduces the regression — a negative
   control is part of the design).
4. Config C p50 ≤ 2.5 s per query through the service.
5. RSS peak of config C ≤ 2.5 GB; instance memory returns after inference.
6. Fail-open probe: `MCP_RERANK_MODEL=does-not-exist` → baseline order, one warning,
   no error response.
7. Config B p50 ≤ 1.0 s through the service.

## Output artifact

`eval/lab_rerank_service_{base,msmarco,bge}.json` — recall@5/10/30, p50/p95, RSS peak,
effective env vars (`rerank_enabled`, `model`, `candidates`), machine-load note.
Committed in the bench repo; aggregated numbers cited in the gate.

## Publication gate

No PR, no upstream comment, no promotion to users before Claudio's explicit
acceptance of the final text.
