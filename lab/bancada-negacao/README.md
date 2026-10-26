# Negação × rerank — o número que faltava

Medição nossa (26/out/2026, sirdata) do conjunto de pares de negação do PR #1696 do
upstream contra o nosso rerank de segunda etapa (#1602 / PR #1661, embarcado na v12.4.0).

## O que foi medido

Mesma construção de corpus do benchmark do mantenedor: 50 pares mínimos (afirmação /
negação) + 15 distratores = **115 memórias** em sqlite-vec isolado. Cada par é consultado
duas vezes (`q_pos` espera `pos`; `q_neg` espera `neg`), total de **100 decisões**.
Métrica de manchete: *pairwise accuracy* — o membro certo ranqueia acima do outro.

Três condições, no mesmo store:

- `cosine` — similaridade sobre todas as linhas (exato). Equivale ao baseline do mantenedor.
- `rerank40` — nosso estágio: cross-encoder `Xenova/bge-reranker-base` (int8) sobre os 40
  melhores por cosseno. É o default de produção (`MCP_RERANK_CANDIDATES=40`).
- `rerank_all` — teto: cross-encoder sobre o corpus inteiro (115).

## Calibração do instrumento

O baseline `cosine` **reproduz exatamente** os números publicados no #1696:
`pairwise_all` 0,63 e `neg_implicit` 0,32. Sem essa coincidência a comparação não valeria.

## Resultado (`all-MiniLM-L6-v2`, igual em `paraphrase-multilingual-MiniLM-L12-v2`)

| condição | pairwise_all | pos | neg | neg_explicit | neg_implicit | top1_pos | top1_neg | p50 |
|---|---|---|---|---|---|---|---|---|
| cosine | 0,63 | 0,66 | 0,60 | 0,88 | 0,32 | 0,66 | 0,60 | — |
| **rerank40** | **0,87** | 1,00 | 0,74 | 1,00 | 0,48 | 1,00 | 0,70 | 257 ms |
| rerank_all | 0,88 | 1,00 | 0,76 | 1,00 | 0,52 | 1,00 | 0,70 | 805 ms |

Bootstrap pareado (10.000 reamostragens sobre as 100 consultas):

- cosine → rerank40: **+24,0 p.p.**, IC95 [+14,0, +34,0]; 27 consultas melhoraram, **3 pioraram**
- cosine → rerank_all: +25,0 p.p., IC95 [+15,0, +35,0]; 28 melhoraram, 3 pioraram

Referência do mantenedor no mesmo conjunto: `resonance` 0,62 / `phase` 0,60 / `hybrid` 0,61
— todos no nível do cosseno.

## Limites honestos

- Corpus sintético de 115 memórias, não o acervo real. O ganho aqui é maior que o do
  #1602 (+10 p.p.) porque a tarefa é mais fácil: ambos os membros do par estão sempre
  dentro do top-40 do cosseno (mediana do pior posto = 2, máximo = 36 — ver
  `verifica_pool.py`), então o cross-encoder só decide entre duas frases quase idênticas.
  Verificado: `pares_no_pool` = 100/100 é medido, não suposto.
- **Negação implícita continua abaixo de 50%** mesmo com rerank (0,48): quando a consulta
  pede o fato negado sem usar "not", o cross-encoder ainda erra mais que acerta. É a
  fronteira que ninguém fechou — nem nós, nem a ressonância.
- 3 das 100 consultas pioraram com o rerank. Não é "zero regressões": é +24 p.p. líquidos.

## Como repetir

```bash
cd ~/git/mms/bancada-negacao
BENCH_EMBED_MODEL=all-MiniLM-L6-v2 /home/claudio/git/mms/mms/.venv/bin/python bench_negation_rerank.py
BENCH_EMBED_MODEL=all-MiniLM-L6-v2 /home/claudio/git/mms/mms/.venv/bin/python verifica_pool.py
```

`negation_pairs.json` é cópia literal do `scripts/benchmarks/negation_pairs.json` do
upstream em `ef25b93d` — não editar, senão o número deixa de ser comparável.
