# RETOMADA — negação × rerank (para 27/out/2026)

Sessão de 26/out/2026, sirdata. Tema: o upstream mediu a "resonance search" (PR #1673,
issue #1674, harness #1696) e ela não passou; nós tínhamos o mesmo problema resolvido por
outro caminho (#1602 / PR #1661). O número que faltava — negação contra o nosso rerank —
foi medido. Falta publicar.

## Estado: MEDIDO, NÃO PUBLICADO

## Fatos que não devem ser redescobertos

- **Rerank é nosso e está no upstream.** Issue #1602 (`filhocf`, 19/out) + PR #1661
  (`filhocf`, COLLABORATOR, mergeado 23/out 22:30 UTC) → `344f4ae1` em `upstream/main` →
  primeira release que o carrega: **v12.4.0** (26/out). O squash `344f4ae1` **não** está no
  `main` do nosso fork: lá o rerank entrou pelos commits originais (`f72a2b13` e seguintes).
  Não re-mergear sem tratar isso, senão duplica.
- **Ressonância é dele, não nossa.** #1673, #1674 e #1696 são todos do `doobidoo`. Resultado:
  `resonance` 0,62 / `phase` 0,60 / `hybrid` 0,61 em negação — nível do cosseno (0,63), e
  LoCoMo −0,5 p.p. Ficou experimental; nada no dashboard mudou. Não vale investir: score sem
  informação nova (fase derivada do mesmo embedding → monótona em cosseno, o próprio artigo
  admite $S=(1+\cos\theta)/2$ para vetor real) **e** 3,4 s p50 @20k contra 31 ms do KNN.
- **Nosso número de negação** (mesmo corpus dele, 115 memórias, 100 decisões): no índice dele
  (`all-MiniLM-L6-v2`) cosseno 0,63 → rerank 40 candidatos **0,87** (+24,0 p.p., IC95
  [+14,0, +34,0], 27 melhoraram / 3 pioraram, p50 257 ms); no nosso de produção
  (`paraphrase-multilingual`) cosseno 0,77 → **0,89** (+12,0 p.p., IC95 [+5,0, +19,0],
  13 melhoraram / 1 piorou). Explícita 0,88 → 1,00. **Implícita 0,32 → 0,48** no inglês (abaixo
  de 50%) e **0,28 → 0,56** no multilíngue.
- **Correção de 27/out:** o primeiro relato dizia que os números eram idênticos nos dois modelos.
  Errado — o storage recebe o modelo por construtor e o default é `all-MiniLM-L6-v2`, então as
  duas execuções mediam o índice inglês. Greptile P1 no PR #1697; corrigido. **Regra que fica:
  passar o modelo ao construtor e testar que ele chega lá, não exportar variável de ambiente.**
- **O baseline bateu dígito por dígito** (0,63 e 0,32) com o publicado no #1696. É o que
  autoriza a comparação; se algum dia divergir, o instrumento quebrou, não o resultado.
- **Teto de ganho**: subir de 40 para 115 candidatos rende só +1 p.p. O default de produção
  (`MCP_RERANK_CANDIDATES=40`) está no joelho da curva.
- **Acervo e versão**: serviço reporta 12.2.1 (fork); upstream em 12.4.0. Divergência
  acumulada ~309 arquivos / 52k linhas, boa parte estado interno de fork.
- **Lacuna real de upstream**: `memory_context` / injeção proativa existe no nosso fork e
  **não** no `upstream/main` (grep = 0). Issue #1566 aberta desde 16/out pedindo direção,
  sem resposta. ~975 linhas, delta-recall +0,558 [0,419, 0,698].

## Próximos passos, na ordem

1. **Publicar o comentário no #1696** (inglês, texto já redigido na sessão de 26/out; exige
   OK do Claudio e mostrar EN + PT-BR antes). Números: 0,87 vs 0,63, +24 p.p., IC +14/+34,
   257 ms, explícita 1,00, implícita 0,48. Sem reivindicar acervo real.
2. **Abrir PR com o script comparativo** (`bench_negation_rerank.py`) — o mantenedor pediu
   harness reproduzível no critério "done when" da #1674; entregar o nosso fecha o ciclo.
3. **Decidir o #1566**: submeter fatiado (base `memory_context` primeiro) ou arquivar.
4. **Mergear `upstream/main` 12.4.0 no fork** absorvendo `344f4ae1` sem duplicar o rerank.

## Como repetir a medição

```bash
cd ~/git/mms/bancada-negacao
BENCH_EMBED_MODEL=all-MiniLM-L6-v2 /home/claudio/git/mms/mms/.venv/bin/python bench_negation_rerank.py
BENCH_EMBED_MODEL=all-MiniLM-L6-v2 /home/claudio/git/mms/mms/.venv/bin/python verifica_pool.py
```

`negation_pairs.json` é cópia literal do upstream em `ef25b93d` — não editar.
Registro no acervo do mms: `fa5a90f6` (medição). Detalhe do método: `README.md` nesta pasta.
