# SPEC — Harness de Recall@k para `memory_search` com perguntas naturais (I2)

**Deriva de:** `docs/_fork/diagnostico-precisao-recuperacao.md` (medido 17-18/out)
**Data:** 2026-10-18 · **Status:** DRAFT G2 · **Classe:** FEATURE (fila serial)
**Worktree:** `~/git/mms-lab-precisao` branch `lab/precisao-recall` (laboratório, não produção)
**Escopo:** 1 incremento. Ferramenta de medição. Não altera o comportamento da busca.

---

## 1. Problema

O projeto mede recuperação com dois instrumentos e nenhum deles responde à pergunta do usuário:

- `eval/rerank_bench.py` mede `memory_context()` — a via de **beliefs** da injeção, não
  `memory_search`. Queries são palavras-chave de tema, não paráfrases (evidência: :246).
- `scripts/benchmarks/benchmark_locomo.py` mede `retrieve()` sobre **dataset sintético**
  (LoCoMo), útil para MRR comparativo, cego para o acervo real.

Resultado medido em 18/out: **Recall@10 = 20%** em 10 fatos verificados por SQL no acervo
vivo, com pergunta natural. Oito de dez fatos conhecidos não aparecem no top-10. Sem um
harness que meça isso, qualquer ajuste de ranking é otimização sem termômetro.

## 2. Objetivo e não-objetivos

**Objetivo:** um runner determinístico que, dado um dataset versionado de perguntas naturais
com gabarito verificado, reporte Recall@k e MRR@k de `memory_search` para os quatro modos
(`semantic`, `exact`, `hybrid`, `ranked`), contra um snapshot imutável do acervo.

**Não-objetivos:** alterar a busca; criar dataset sintético; avaliar `memory_context` (já
coberto pelo rerank_bench); rodar em CI ainda (primeiro rodar local e versionar baseline).

## 3. Requisitos (prosa + EARS)

**R1 — Dataset versionado e verificável.**
Casos em `eval/recall_cases.json`: `{id, pergunta, categoria, gold_terms[], gold_hashes[]}`.
`gold_terms` é o critério de acerto (o fato pode viver em mais de uma memória); `gold_hashes`
é informativo.

> EARS: The harness SHALL load cases from a versioned JSON file and SHALL validate that every case declares at least one gold_term.

**R2 — Verificação do gabarito antes de medir.**
O runner confirma por consulta direta ao banco que cada `gold_term` existe em ≥1 memória viva.
Caso não exista, o caso é reportado como `invalid_case` e excluído das métricas.

> EARS: WHEN a gold_term has zero matching live memories THE harness SHALL mark the case invalid and SHALL exclude it from recall computation.

**R3 — Quatro modos, mesma entrada.**
Para cada caso, executar os quatro modos com o mesmo `limit` e registrar posição do primeiro
acerto (por `gold_terms`, case-insensitive, dentro do conteúdo do resultado).

> EARS: The harness SHALL evaluate every case under semantic, exact, hybrid and ranked with identical inputs and SHALL record the rank of the first hit per mode.

**R4 — Métricas padronizadas.**
Recall@k e MRR@k por modo e por categoria, reusando `recall_at_k`/`mrr` de
`scripts/benchmarks/locomo_evaluator.py` quando compatíveis.

> EARS: The harness SHALL report recall@k and mrr@k per mode and per category, with k configurable (default 10).

**R5 — Determinismo.**
Execução contra snapshot do banco (`MCP_BENCH_DB`), nunca contra o acervo mutável por padrão;
saída JSON estável ordenada, adequada a diff entre execuções.

> EARS: WHEN a benchmark DB is provided THE harness SHALL read only from it and SHALL emit stable ordered JSON.

**R6 — Não escreve.**
Nenhuma chamada de gravação; nenhuma alteração de estado do acervo.

> EARS: The harness SHALL NOT issue store, update or delete operations.

**R7 — Comparação A/B entre execuções.**
Subcomando que compara dois relatórios e reporta delta de recall/MRR por modo e os casos que
mudaram de posição.

> EARS: WHEN two report files are given THE harness SHALL emit per-mode deltas and the list of cases whose rank changed.

## 4. Design

```
eval/recall_cases.json ─┐
                        ├─► validar gabarito (SQL, ro) ─► executar 4 modos ─► métricas ─► report.json
MCP_BENCH_DB (snapshot) ┘                                        │
                                                                 └─► compare report_a report_b
```

- **Dataset inicial:** os 10 casos já verificados no diagnóstico (§2.1), cobrindo
  importador, LIA, belief, delta-sync, HCSO, hackathon. Meta: 30 casos para estabilidade.
- **Acerto:** substring de `gold_term` no bloco do resultado (o mesmo critério do diagnóstico,
  que já se mostrou robusto contra o falso-negativo de hash único).
- **Saída:** `{"meta": {...}, "modes": {"semantic": {"recall@10": 0.2, "mrr@10": 0.125, "positions": {...}}}, "invalid_cases": [...]}`.
- **Reúso:** `recall_at_k`, `precision_at_k`, `mrr` de `locomo_evaluator.py:11-40`; padrão de
  `MCP_BENCH_DB` de `rerank_bench.py:208-209`.

## 5. Casos de erro e bordas

| Caso | Comportamento |
|---|---|
| `gold_term` inexistente no snapshot | `invalid_case`, excluído; contagem no topo do relatório |
| término de busca vazio | erro claro, exit ≠ 0 |
| snapshot ausente | erro claro sugerindo `MCP_BENCH_DB` |
| modo indisponível no backend | registra `unavailable`, não quebra os demais |
| resultado truncado pelo servidor | detectar `[!] RESPONSE TRUNCATED` e registrar aviso |

## 6. Critérios de aceitação

| # | Critério | Verificação |
|---|---|---|
| CA1 | Reproduz o baseline medido (semantic R@10 = 20% no dataset de 10) | rodar contra snapshot do dia |
| CA2 | Determinismo | duas execuções seguidas produzem JSON idêntico |
| CA3 | Relatório por modo e categoria | estrutura do JSON |
| CA4 | Gabarito verificado | `invalid_cases` correto em teste com termo inexistente |
| CA5 | Zero escrita | spy/mock: nenhuma chamada de store |
| CA6 | `compare` calcula deltas corretos | teste com dois relatórios sintéticos |
| CA7 | Tempo de execução < 90 s para 10 casos × 4 modos | medição |

## 7. Testes RED previstos

1. `test_dataset_valida_gold_terms` — caso sem `gold_terms` é rejeitado.
2. `test_gold_term_inexistente_vira_invalid_case` — e sai das métricas.
3. `test_recall_e_mrr_por_modo` — dataset sintético com gabarito controlado (2 hits em posições conhecidas).
4. `test_posicao_por_termo_nao_por_hash` — duas memórias contendo o termo: acerto na primeira que aparecer.
5. `test_determinismo_saida_ordenada` — duas execuções, JSON idêntico.
6. `test_nenhuma_escrita` — transporte/armazenamento com spy.
7. `test_compare_deltas` — relatório A vs B.

Red-on-main: todos falham hoje (módulo não existe), e devem falhar por comportamento após o
primeiro GREEN parcial (teste 3 e 4 travam lógica real, não import).

## 8. Diário de gate

**Decisões fixadas:** acerto por `gold_term` (não por hash único) · snapshot via `MCP_BENCH_DB` ·
quatro modos sempre · dataset começa com os 10 casos do diagnóstico · nenhuma escrita.

**Comandos canônicos (no worktree do lab):**
```
cd ~/git/mms-lab-precisao
.venv/bin/python -m pytest tests/test_recall_harness.py -q
.venv/bin/python -m ruff check <arquivos>
.venv/bin/python -m scripts.benchmarks.recall_harness --db <snapshot> --out /tmp/r1.json
```

**Histórico:** G0 (arquiteto) mapeou default semântico em 3 pontos, hybrid com FTS5+RRF
existente, chunking único em `handlers/memory.py:563-585`, ausência de expansão de query, e
que `locomo_evaluator.py` já tem as métricas. G2: esta spec.

**Pendências:** gerar snapshot imutável do acervo · ampliar dataset para 30 casos · decidir se
roda em CI.

## 9. Riscos

- **Gabarito mal curado** invalida o harness. Mitigação: R2 (verificação por SQL) e revisão
  humana dos termos.
- **Acoplamento ao acervo vivo**: o snapshot é obrigatório justamente para evitar que o
  número mude sem que ninguém saiba por quê.
- **Falso conforto**: alto recall com ranking ruim ainda entrega o fato na posição 8. Por isso
  MRR@k junto com Recall@k.
