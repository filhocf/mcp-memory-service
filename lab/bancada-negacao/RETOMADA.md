# RETOMADA — negação × rerank (para 27/out/2026)

Sessão de 26/out/2026, sirdata. Tema: o upstream mediu a "resonance search" (PR #1673,
issue #1674, harness #1696) e ela não passou; nós tínhamos o mesmo problema resolvido por
outro caminho (#1602 / PR #1661). O número que faltava — negação contra o nosso rerank —
foi medido. Falta publicar.

## Estado: PUBLICADO — PR #1697 aberto, aprovado, aguardando o mantenedor

`gh pr view 1697`: `OPEN`, `MERGEABLE`, **`review=APPROVED` (Greptile)**, 18 checks
`SUCCESS` + 2 `SKIPPED`, head `b2b719c`, e as três threads de revisão `resolved=true/outdated=true`.


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

1. ~~**Publicar o comentário no #1696**~~ **FEITO** (26/out 23:36 UTC) — tabela do índice inglês.
   Correção publicada em seguida (23:58) quando o erro de modelo apareceu: no índice multilíngue
   o cosseno é 0,77 e o rerank leva a 0,89 (+12,0 p.p.), não os 0,87 da tabela inglesa.
2. ~~**Abrir PR com o script comparativo**~~ **FEITO** — PR #1697, aprovado pelo Greptile.
3. **Decidir o #1566**: submeter fatiado (base `memory_context` primeiro) ou arquivar.
4. **Mergear `upstream/main` 12.4.0 no fork** absorvendo `344f4ae1` sem duplicar o rerank.
5. **Opcional, se o mantenedor pedir**: rodar o mesmo conjunto no acervo real (não sintético) —
   é a lacuna honesta que o PR declara.

## O que o Greptile pegou (e o que isso ensinou)

P1: `--embedding-model` só exportava `MCP_EMBEDDING_MODEL`, mas `SqliteVecMemoryStorage` recebe o
modelo por **argumento de construtor** (default `all-MiniLM-L6-v2`). As duas execuções construíam
o índice inglês: a afirmação "idêntico nos dois modelos" media um modelo duas vezes. Corrigido
(`a71475f4`) passando o modelo ao construtor, com teste que falha se o argumento parar de ser
repassado. Regra que fica: **configuração de instância se fixa no construtor e se prova por teste,
não por variável de ambiente exportada antes do import.**


## Como repetir a medição

```bash
cd ~/git/mms/bancada-negacao
BENCH_EMBED_MODEL=all-MiniLM-L6-v2 /home/claudio/git/mms/mms/.venv/bin/python bench_negation_rerank.py
BENCH_EMBED_MODEL=all-MiniLM-L6-v2 /home/claudio/git/mms/mms/.venv/bin/python verifica_pool.py
```

`negation_pairs.json` é cópia literal do upstream em `ef25b93d` — não editar.
Registro no acervo do mms: `fa5a90f6` (medição). Detalhe do método: `README.md` nesta pasta.
