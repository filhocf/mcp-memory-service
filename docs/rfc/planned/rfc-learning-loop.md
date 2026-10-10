> 🟡 LOOP CLOSED IN CODE, MENSURÁVEL A PARTIR DE 10/out (não "pronto"). L1 memória · L2 destilação (belief store, ruído filtrado) · L3 injeção pull (memory_context) + push server-side (INC-2) — **confirmado disparando** em memory_search via /mcp (teste E2E 10/out) · L4 feedback agora **mensurável**: o fix de proveniência (injection grava source_hashes = derived_from do belief) destravou injection_coverage, que saiu de 0.0 estrutural → 0.013 no serviço vivo após 1 ciclo inject→use. Ver §13 (avaliação honesta 10/out) e §14 (o que falta — context precision / 4 dimensões). O ciclo roda; o que falta é o TIRO CERTEIRO (ranking) e as dimensões freshness/forgetting. Guarda-chuva. ADR-0003/0004/0005 + baseline LoCoMo 0.4140.

# RFC: Learning Loop — do colhedor ao aprendiz (closed-loop agent learning)

**Status:** planned (draft v0.2) · **Criado:** 2026-10-02 · **Rev:** 2026-10-10 · **Fork-only (amadurecimento)**
**Autor:** Claudio + Zero · **Base:** v11.14.0+ (fork sincronizado 02/out)

> **A pergunta que origina esta RFC (Claudio, 02/out):** "De que adianta ficar
> colhendo memórias — e eu poder acessá-las — se isso não se consolida em
> CONHECIMENTO? E como fazer o agente APRENDER com isso?"

## 0. A analogia que define o alvo (Claudio p/ Mari, 10/out)

> *"Você estuda fisioterapia. Aula 1, 2, …, N, cada uma gerando anotações. Na prova,
> quando precisa, você pega só o que é importante para AQUELE momento — diferente da
> IA, que pega TUDO, lê de 1 a N sessões, e só então separa o que precisa. Quero levar
> o que nós fazemos para o Zero fazer: **condensar conteúdo para tiro rápido e certeiro.**"*

Essa analogia É a especificação do loop, traduzida:
- **Aulas 1..N + anotações** = L1 memória (eventos brutos, 25k mems).
- **"na prova, pega só o que importa para aquele momento"** = o aprendizado humano:
  não se relê 40 aulas; tem-se a **condensação** (L2 destilação) e **puxa-se a certa,
  na hora certa** (L3 injeção com boa *context precision*).
- **"a IA pega TUDO, lê de 1 a N, e separa"** = o RAG ingênuo que estamos SAINDO —
  reler tudo a cada pergunta. O loop quer o oposto: destilado pronto + injeção cirúrgica.
- **"tiro rápido e certeiro"** = **rápido** (one-shot, sem rodadas de busca → L3 push, já
  feito) + **certeiro** (o item CERTO para aquele momento, não o genérico → *context
  precision*, o que AINDA FALTA — §14 frente A).

Onde estamos na analogia (honesto, 10/out): temos as anotações condensadas (L2 ✅) e a
entrega automática "junto" (L3 push ✅). Mas na "prova" ainda chega a anotação GENÉRICA
no topo ("sempre revise antes") em vez da ESPECÍFICA e decisiva ("neste caso, o músculo
X responde assim"). **Condensar: temos. Certeiro: é o próximo arco.**

## 1. Problema (em uma frase)

Hoje o serviço faz **recuperação**, não **aprendizado**. Colhe eventos, grava, e o
agente relê no startup. Colher mais sem fechar o ciclo é **encher um balde furado**:
mais memória episódica, zero consolidação em conhecimento, nenhuma mudança de
comportamento por mérito.

## 2. Distinção central: memória ≠ conhecimento ≠ aprendizado

| Camada | O que é | Temos hoje? |
|--------|---------|-------------|
| L1 Memória | fatos brutos recuperáveis (eventos, episódico) | ✅ (23.6k mems) |
| L2 Destilação | episódico → semântico (regra/crença: "quando X, causa costuma ser W") | 🟡 parcial, **ruidoso** (beliefs 107 active, conf máx 0.64) |
| L3 Conhecimento ativo | o destilado entra no contexto certo, no momento certo, **sem pull manual** | 🟡 só pull (startup/mistake_search manual) |
| L4 Feedback | a regra sobrevive por **mérito** (ajudou→sobe, atrapalhou→morre) | 🟢 no código (telemetria usage_events + recompute quality clampado [0,1] + sinal injected_then_used peso 2× reaccess). Medição com volume pendente. |

**Não-objetivo (honestidade intelectual):** não mudamos os pesos do modelo
(fine-tuning). O "aprendizado" vive no **harness/serviço**, não no agente. O efeito
observável é indistinguível de aprender *dentro do contexto de cada sessão* — e é
isso que faz o sistema (não o modelo) ser mais útil a cada semana.

## 2.1. Enquadramento: o MCP apoia uma LIMITAÇÃO (Claudio, 3/out)

Perder contexto **não é culpa do agente/LLM — é limitação do modelo.** O memory-service
existe para **APOIAR** nessa limitação: é a prótese de memória/aprendizado que compensa
o que o modelo não faz sozinho. As RFCs autolearn/autodream nasceram **das dores reais**,
não da teoria. E as 4 camadas não são escolha excludente — **são um conjunto**. A ordem
de ataque é tática; a definição de PRONTO é o ciclo fechado completo.

## 2.2. Valor de cada camada (por que cada dor importa — Claudio)

- **DESTILAÇÃO (L2):** *"não tem porque se afogar em memórias. O que é o destilado
  daquele tema? É o que você precisa."* → recebo conhecimento, não 40 eventos crus.
- **INJEÇÃO (L3):** *"te ajuda a ser mais assertivo porque não fica fazendo rodadas
  buscando a info certa — já chega de cara, one-shot."* → acerto na primeira.
- **FEEDBACK (L4):** *"te deixa mais efetivo, não erra tanto e não perde TEMPO. Imagina
  refazer todas as vezes porque tocou direto e não delegou. Tempo e recursos."* → não
  repito erros; economizo tempo e recursos.

Ironia que reforça a prioridade: otimizar a **busca** (ex: ranking keyword×semantic,
D3/query-intent) é afinar um comportamento que o objetivo final quer **reduzir** — se
destilação+injeção funcionam, eu **busco menos**, porque o conhecimento vem até mim.
Logo, melhorar busca é valor marginal perto de fechar o ciclo.

## 3. Por que do lado do SERVIÇO, não do agente

O agente é efêmero e troca de máquina (Zero×3 + Scotty + T'Pol). Se o aprendizado
morasse no agente, morreria com a sessão. **O serviço é o único substrato persistente
e compartilhado** — logo, o ciclo de destilação+validação+injeção TEM que ser
server-side. O agente é consumidor do conhecimento, não o guardião dele.

## 4. O ciclo fechado (a tese)

```
colher (limpo, Fase 0)
   → DESTILAR     episódico → crença/regra, confiança calibrada            [L2]
   → VALIDAR      feedback: a regra ajudou? sobe. atrapalhou? cai.         [L4]
   → INJETAR      push proativo no contexto certo (não pull manual)        [L3]
   → agente age melhor → nova evidência → recalibra ──┐
   └───────────────────────────────────────────────────┘
```

Hoje a 1a seta é forte; as outras 3 são fracas ou manuais. **Ciclo aberto.**

## 5. Requisitos (EARS)

- **R1 (destilação):** WHEN N>=2 observações independentes compartilham um padrão,
  THE sistema SHALL derivar uma crença com confiança = f(suporte, contradição, decay)
  e proveniência (quais memórias a sustentam).
- **R2 (anti-ruído):** THE destilador SHALL excluir memory_type em {session,
  checkpoint, milestone} e associações auto-geradas da derivação de crenças
  (fecha a dívida de beliefs ruidosas, task dc1c7756).
- **R3 (feedback):** WHEN uma crença/memória é injetada e a sessão a utiliza (sinal
  de uso) ou a contradiz (sinal negativo), THE sistema SHALL recalibrar a confiança
  dessa crença.
- **R4 (injeção proativa):** WHEN o agente inicia trabalho sobre um tema T, THE
  serviço SHALL retornar o conhecimento destilado relevante a T dentro de um budget
  de tokens, SEM depender de uma chamada de busca explícita do agente.
- **R5 (calibração honesta):** THE confiança injetada SHALL ser exposta ao agente
  (um conhecimento de conf 0.9 nao e um de conf 0.4), para o agente ponderar.
- **R6 (reversibilidade):** THE sistema SHALL preservar a cadeia crença->observações
  para que uma crença errada seja re-derivável/retratável, nunca um fato opaco.

## 6. O no duro: INJEÇÃO (R4) — "é adivinhação com base na pesquisa?"

Sim, parcialmente — e o truque é **transformar adivinhação em relevância medida**.
Três abordagens, da mais ingênua à desejável:

1. **Similaridade (hoje):** busca vetorial pelo texto do tema. Traz o parecido, não o
   que impede erro. Palheiro cresce com a colheita. INSUFICIENTE.
2. **Grafo + centralidade (parcial):** crenças ligadas por entidade/relação; injeta
   as mais centrais ao tema (memory_explore existe mas é pull). PARCIAL.
3. **Relevância causal validada (alvo):** injeta o que, no passado, **mudou o
   resultado** em contextos semelhantes (feedback-loop fecha isto). Deixa de ser "o
   que parece" e vira "o que historicamente ajudou aqui". ALVO.

A "adivinhação" nunca zera — e um problema de recuperação sob incerteza. Mas R3
(feedback) a transforma de chute textual em **aposta calibrada por histórico de
utilidade**. Essa é a diferença entre RAG-sobre-histórico (todo mundo faz) e um
motor de aprendizado (genuinamente novo).

## 7. Gap: de onde estamos -> onde queremos

**ATUALIZADO 09/out:** L1 feito. L2 destilação funciona (beliefs destiladas, não ruidosas após noise filter). L3 injeção pull (memory_context) + **push server-side** (INC-2: memory_search anexa contexto destilado, opt-in). L4 **fechado no código**: telemetria + recompute quality clampado + sinal **injected_then_used** (injetado e depois usado = utilidade qualificada, distingue de popularidade/reaccess). O ciclo colher→destilar→injetar→usar→recalibrar está COMPLETO mecanicamente. Falta o fechamento EMPÍRICO (MRR sobe vs 0.4140), que depende de volume de injeção+uso acumular — a flag INC-2 ligada agora gera esse volume. Caminho e medição em §9 + baseline em docs/_fork/benchmarks/.

## 8. Decisões abertas
- ~~Injeção proativa: via tool memory_context (pull) ou hook server-side (push)?~~ **RESOLVIDO (ver §3): server-side, não depende da disciplina do agente.** Como o Kiro não tem canal de pré-tool-context nativo, o push server-side se dá **anexando o contexto destilado relevante à resposta de uma operação que o agente JÁ faz** (ex: `retrieve`/`memory_search` devolvem, junto do resultado, o conhecimento destilado do tema). O agente não chama nada novo — busca como sempre e a injeção vem junto. Isso é server-side (§3), gera volume de injeção automático, e alimenta o sinal de uso do L4. O que NÃO é aceitável: depender de o agente lembrar de chamar `memory_context` (= rating manual que já falha). A tool `memory_context` continua existindo para pull explícito, mas NÃO é o mecanismo do push.
- Sinal de "uso": como o serviço sabe que uma injeção FOI usada? (rating implícito, eco no texto da sessão, harvest reverso). Elo mais incerto do R3 — mas o sinal NEGATIVO (contradição/retry) é barato e já prioritário (§11).

## 9. Caminho mínimo (incremental, não big-bang)
1. Limpar beliefs ruidosas (R2, task dc1c7756) — pré-requisito; destilar sobre ruído = mais ruído.
2. Destilação confiável (R1) — Trilogia C1 fact-extraction + confiança calibrada.
3. Feedback-loop (R3/R4) — o coração; sinal de uso -> recalibração.
4. Injeção proativa (R4) — memory_context por tema, budget, confiança exposta.

## 10. Relação com outras RFCs
Absorve/conecta: rfc-self-service-memory-intelligence (Trilogia C), rfc-mm-01-feedback-loop,
rfc-mm-02-fact-extraction, rfc-mm-03-gap-detection, rfc-persona-tier (identidade destilada),
rfc-ingestao-multi-agente (a colheita limpa é o INPUT deste ciclo). Esta RFC é o
**guarda-chuva do PORQUÊ** — as outras são os COMOs por peça.

## 11. O GARGALO REAL: o sinal de uso (feedback honesto)

O elo mais difícil do ciclo NÃO é colher nem destilar nem buscar — é **saber se uma
injeção foi útil**. O serviço é cego para o agente: injeta conhecimento, o agente age,
mas o serviço não vê se aquilo *mudou* o comportamento. Sem esse sinal, a injeção é só
adivinhação permanente (nunca calibra) e injetar adivinhação ruim é PIOR que não injetar
(polui contexto, gasta budget, distrai).

Opções de sinal, nenhuma perfeita (decisão de design aberta):
- **Rating implícito** — agente rateia o que ajudou. Frágil: depende de lembrar (é o que
  já falha hoje; steering pede >=3/sessão e não acontece).
- **Eco no texto** — harvest reverso detecta se o conhecimento injetado reapareceu na
  saída do agente. Automático, mas ruidoso (eco != uso causal).
- **Resultado da tarefa** — tarefa teve sucesso após injeção X -> X ganha crédito. Sinal
  distante, atribuição difícil (muitas injeções, um resultado).
- **Negative learning** (do autolearn-rfc) — contradição explícita é sinal forte e barato:
  se a sessão contradiz a crença injetada, confiança cai. Mais confiável que o sinal positivo.

TESE: resolver BEM o sinal de uso é o que separa "RAG sofisticado" (todo mundo) de
"motor de aprendizado" (novo). A recursão — o sistema aprendendo a errar menos a
adivinhação, a partir do próprio histórico de acertos/erros de injeção — É o aprendizado.
Priorizar o sinal NEGATIVO primeiro (mais confiável) antes do positivo.

## 12. Base de pesquisa (JÁ EXISTE — esta RFC consolida, não inventa)

Esta visão sintetiza pesquisa anterior nossa. NÃO recomeçar do zero:
- **CdIA `padroes/mcp-memory-autolearn-rfc.md`** (ago/2026, 28KB) — análise de 11 sistemas
  de memória para agentes (Mem0, Zep/Graphiti, Honcho, Hindsight/TEMPR, LanceDB, LangGraph,
  CrewAI, AutoGen, MemPalace, Kiro) + matriz comparativa + proposta 8 fases (auto-capture,
  correlação cross-session, **negative learning**, bootstrap profiles). É o estado-da-arte
  que embasa L2/L4.
- **plano-self-improvement-agente** (memória hash 42c8b68e) — 3 eixos (Verificação /
  Feedback Loop Fechado / Cross-Domain Transfer). Base: Karpathy Loop (700 experiments),
  Ralph Loop, HyperAgents (meta-cognitive self-modification), Addy Osmani (compound learning).
- **autolearn/autodream** (AGENTS.md) — autolearn = extrair padrões; autodream = consolidação
  periódica. Já conceituados, parcialmente implementados (harvest+distill+bootstrap).
- Pesquisa multi-IA (Gemini/Perplexity/DeepSeek) sobre hooks/loops (hash f2d63b7f).

AÇÃO: antes de implementar qualquer peça, reler o autolearn-rfc §2.2 (arquitetura) e
§2.4 (plano) — provável que o COMO de L2/L4 já esteja desenhado lá e esta RFC só precise
amarrar com o enquadramento do ciclo fechado + o insight do sinal de uso (§11).


## 13. Avaliação honesta (10/out) — medido no serviço vivo, não narrativa

Como CLIENTE (Zero usa isto todo dia) + MANAGER, com dados reais do sirdata:

- **L3 push DISPARA** (refutada a suspeita de que não): `memory_search` via /mcp anexa
  "Related distilled context" e grava o evento injection. Os "7 de 36.688" eram dados
  históricos pré-deploys de 10/out (socrates nem tinha a flag até então).
- **L4 estava CEGO** (bug estrutural, não falta de volume): `injection_coverage` e
  `injected_then_used` eram 0.0 porque a injeção gravava só `belief_hash` (sha256 do
  texto destilado) e a métrica correlacionava com `content_hash` de memória — namespaces
  que **nunca cruzam**. FIX (commit 63ddfaaa): injeção grava `source_hashes`
  (= `derived_from` do belief = content_hashes das memórias-fonte); telemetria correlaciona
  por eles. **Prova E2E viva: coverage 0.0 → 0.013** após 1 ciclo inject→use.
- Conceito formal (pesquisa 10/out): isto é **Context Utilization / Chunk Attribution** —
  "o agente de fato usou o contexto injetado?". Nosso proxy via proveniência é sólido
  sem LLM-judge, mas é indireto (mede "a fonte reapareceu", não "mudou a decisão").

## 14. O que falta — "tiro certeiro" (context precision) + 4 dimensões

A pesquisa de avaliação de memória de agente (FutureAGI 4-dimensões; Ragas context
precision/recall/faithfulness; chunk attribution) revelou que medimos ~1,5 de 4
dimensões. O loop RODA mas não é CERTEIRO. Frentes (candidatas a fatias desta RFC):

**4 DIMENSÕES de memória (score separado — hoje só recall parcial):**
1. **Recall** — fato certo surgiu (top-k hit-rate). 🟡 parcial.
2. **Freshness** — versão MAIS NOVA vence quando o fato tem updates (`valid_at`). 🔴
   não medido; busca por densidade de embedding pode entregar versão velha.
3. **Contradiction handling** — quando fatos discordam, o certo vence + decisão logada.
   🟡 NLI existe, não medido.
4. **Forgetting** — retratado/expirado some (recall vazio em tombstone). 🔴 não medido.
+ non-negotiables: slice de privacidade (memória cruzar agente/tenant = P0), scores no
  trace (mesma rubrica em CI e produção), adversarial set que retrata/atualiza fatos.

**5 FRENTES de melhoria (do olhar de cliente + pesquisa):**
- **A. Re-rank da injeção (CONTEXT PRECISION — o "certeiro" da analogia §0):** hoje
  relevância×confiança favorece belief GENÉRICO muito-reforçado sobre o ESPECÍFICO raro.
  É o específico raro que evita repetir erro. Investigar re-rank que valorize
  especificidade/raridade + match ao tema. **Maior retorno de cliente. Design aberto →
  candidato a pesquisa multi-IA.**
- **B. Sinal NEGATIVO (forgetting de beliefs inúteis):** injetado e nunca usado após N →
  rebaixar confiança / parar de injetar. Hoje só sinal positivo fraco. (conduzo sozinho)
- **C. Freshness na injeção:** versão nova de um fato vence a antiga. (conduzo sozinho)
- **D. Chunk attribution REAL:** medir se a injeção mudou a resposta, não só se a fonte
  reapareceu. Proxy heurístico vs LLM-judge — trade-off de custo. **Design aberto →
  candidato a pesquisa multi-IA.**
- **E. Eval set adversarial + MRR contínuo vs baseline LoCoMo 0.4140.** (conduzo sozinho)

**Método de ataque:** B/C/E são mensuração+heurística (interno, como o fix de 10/out).
A/D são design genuinamente aberto — reservar pesquisa multi-IA para eles. Prioridade de
cliente: **A primeiro** (é o que mais atrapalha o "tiro certeiro" hoje).

Refs: pesquisa consolidada em memória hash 915c9d31; CdIA (a criar) sobre RAG-eval/agent-memory.
