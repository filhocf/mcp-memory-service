# Baseline LoCoMo — learning-loop INC-0 (09/out/2026)

Instrumento: `scripts/benchmarks/benchmark_locomo.py --mode ablation` contra o retrieval real (sqlite_vec), dataset `data/locomo/locomo10.json`.

## Baseline (retrieve puro, SEM quality)

| Métrica | Valor |
|---------|-------|
| MRR | 0.4140 |
| recall@5 | 0.4969 |
| recall@10 | 0.5624 |
| precision@5 | 0.1232 |
| precision@10 | 0.0725 |

Por categoria (recall@10): multi-hop 0.77 (forte) · open-domain 0.65 · single-hop 0.47 · temporal 0.37 (fraco) · adversarial 0.35 (fraco).

## ACHADO CRÍTICO (confirma a preocupação do Claudio 09/out)

`+quality_boost` e `+quality_w0.5` dão números **IDÊNTICOS** ao baseline (MRR 0.4140 = 0.4140, recall idêntico).

- `retrieve_with_quality_boost` EXISTE (base.py:161, over-fetch 3x + rerank composite) — NÃO é método ausente.
- O rerank por quality é **no-op** porque o quality não discrimina: INC-1 mostrou 89% das mems em quality 1.0 (reaccess satura o sigmoid). Rerank sobre quality uniforme = empate = ordem semantic pura = baseline.

## CONSEQUÊNCIA para o arco

1. INC-5 (quality no ranking) JÁ está implementado — mas INÚTIL até o quality discriminar. Não é trabalho de mecanismo.
2. O trabalho de maior valor é MELHORAR O SINAL (reaccess=popularidade → precisa sinal de utilidade: injeção→uso, §6/§11 RFC). 
3. Agora temos o instrumento: qualquer mudança de sinal/ranking é medida por delta de MRR/recall vs 0.4140. Sem mais "distribuição bonita = sucesso".

## Como re-rodar
```
.venv/bin/python scripts/benchmarks/benchmark_locomo.py --data-path data/locomo/locomo10.json --mode ablation --top-k 5 10 --markdown
```
