# Lote 01 — tornar o acervo utilizável como fonte primária

Data: 18/out/2026 · Papel: MANAGER (entrega) e CLIENT (consumidor do produto)
Bancada: `~/git/mms-lab-precisao` (branch `lab/precisao-recall`) · snapshot
`~/local-data/mcp/lab/snapshot-20261018.db` · régua `eval/recall_cases_v2.json` (120 casos)

## Definição de pronto (do ponto de vista do CLIENTE)

1. Pergunta em linguagem natural, **sem o jargão do documento**, e a memória que
   responde aparece no top-10 em pelo menos **metade** dos casos — medido por
   documento, não por termo solto.
2. Quando a memória não existe, o sistema permite concluir ausência sem três
   tentativas de busca.
3. Latência compatível com uso dentro de um turno (p95 < 500 ms).
4. Nenhuma memória entra no índice pela metade sem que isso seja sabido.

## Estado medido (o que já está feito)

| # | frente | estado | número |
|---|---|---|---|
| F1 | régua honesta | feito | 3 definições medidas; a do harness é a mais frouxa |
| F2 | consistência consulta↔índice | feito | 29,2% → **50,0%** (termo-any), 33,3% (documento) só usando o modelo que construiu o índice |
| F3 | representação (truncamento/chunking) | aberto | 50% dos documentos gold nunca chegam ao top-100 |
| F4 | ordenação (reranker) | aberto | teto = recall@100 por documento = 50,0% → ganho máximo +16,7 p.p. |
| F5 | sinal de ausência | aberto | sem medição; hoje é tentativa e erro |
| F6 | ruído e latência | medido, não é problema | p95 137 ms; 0,08 slots redundantes por top-10 |

## F1 — a régua: três definições e o que cada uma esconde

Mesma execução, mesmos 120 casos, modelo `all-MiniLM-L6-v2` (o que construiu o índice):

| definição | recall@10 | recall@100 |
|---|---|---|
| termo-any (o harness hoje: **qualquer** gold_term em **qualquer** resultado) | 0,500 | 0,758 |
| termo-all (todos os gold_terms no mesmo resultado) | 0,375 | 0,592 |
| documento (`gold_hashes`: a memória que responde) | **0,333** | **0,500** |

`termo-any` dá crédito a qualquer memória que mencione uma das palavras-chave; com
2–3 termos distintivos por caso, isso infla o número. Dos 120 casos, 11 recebem
crédito por termo sem o documento gold estar no top-100, e nenhum caso é o inverso.

Decisão: **documento é a métrica de decisão**; termo-all fica como métrica
secundária de diagnóstico; termo-any sai do painel (serve só para comparar com o
histórico já publicado, que usou essa régua).

## F2 — consolidação: um só modelo para consulta e índice

O serviço consulta com `paraphrase-multilingual-MiniLM-L12-v2` (env base
`memory-service.env`, comum às três máquinas) e o índice foi construído com
`all-MiniLM-L6-v2`. Forçar o modelo do corpus muda o resultado em +20,8 p.p.
Recall@10 sobe de 0,292 para 0,500 na régua do harness; 63 → 29 casos fora do top-100.

Duas saídas possíveis, ambas legítimas:
- **(a) alinhar a configuração ao índice**: `MCP_EMBEDDING_MODEL=all-MiniLM-L6-v2`.
  Ganho imediato, custo zero, sem re-embed. Contra: o acervo é majoritariamente PT e
  o modelo é monolíngue — a pergunta em PT é embedada em inglês-espaço.
- **(b) re-embedar o acervo com o modelo configurado** e então comparar. Custo:
  ~350 s de CPU por passagem + backfill de 20,3 mil memórias, com `embedding_version`
  por linha (ADR-0014).

Recomendação: (a) agora — é correção de configuração, não experimento, e devolve
+20,8 p.p. — e (b) como experimento de bancada com índice paralelo, medido por
**documento**, antes de decidir o modelo definitivo.

## F3 — representação: o que fazer com os 50% que nunca são candidatos

Hipótese: o corte em 128 tokens (A2) mutila justamente as memórias longas — mediana
do gold é 372 chars, máximo 3.505. O experimento anterior mediu chunking com cosseno
puro, sem agregação por documento, e chamou o resultado de negativo. Refazer com:
indexação por chunks + agregação **max-pool por documento** na hora de montar o
top-k, e medir recall por documento em @10 e @100.

## F4 — ordenação

Só depois de F3. Teto de reranking = recall@100 por documento (50,0% hoje): o
reranker pode mover 16,7 p.p., não mais.

## F5 — sinal de ausência

Medir a distribuição de score nos 120 casos (acertos vs erros) e verificar se existe
limiar que dê precisão alta para "não tenho isso". É o que transforma a memória em
fonte consultável com confiança em vez de fonte que exige três tentativas.

## Ordem de execução

F1 (feito) → F2 (medido, decisão pendente) → F3 → F4 → F5. F6 já medido.

## Revisão de estratégia (18/out, depois do diagnóstico de coortes)

O corpus está partido em três espaços vetoriais (35,8% all-MiniLM, 64,2% paraphrase,
~10,5% órfãos). Isso invalida a prática de medir e decidir sobre o banco vivo: todo
número produzido ali descreve o estado do índice, não o desenho do sistema. Mesmo
conteúdo, índice coerente: 0,8% → 59,2% por documento.

Passa a valer a separação em dois planos:

- **Plano A — bancada de referência**: corpus higienizado, um único modelo,
  `embedding_version` por linha. É aqui que se mede o sistema e se decide intervenção.
- **Plano B — banco vivo**: trabalho de migração com checkpoints (dedup, stores
  corrompidos, re-embed uniforme), não de pesquisa.

Regra: dado do plano A não julga o banco vivo; mudança no banco vivo não se valida
só nele.

## F3 — encerrada: chunking não é a intervenção

Índice uniforme em paraphrase, blocos de 126 tokens (stride 96), 36.830 blocos,
agregação max-pool por documento, régua por documento:

| cenário | @10 | @30 | @100 |
|---|---|---|---|
| índice simples (1 vetor por memória) | **0,592** | **0,708** | 0,767 |
| chunking + max-pool | 0,567 | 0,683 | **0,775** |

Chunking perde 2,5 p.p. em @10 e 2,5 em @30, ganha 0,8 em @100. O truncamento em
128 tokens **não** é o gargalo quando consulta e índice usam o mesmo modelo — a
hipótese que a noite deixou aberta está resolvida, com resultado negativo.
Artefato: `eval/lab_chunking_maxpool.json`.

Consequência: a ordem muda. Migração do acervo antes de qualquer outra
experimentação; reranker depois, com teto de 0,767.

