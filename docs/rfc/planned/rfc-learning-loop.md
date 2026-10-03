# RFC: Learning Loop — do colhedor ao aprendiz (closed-loop agent learning)

**Status:** planned (draft v0.1) · **Criado:** 2026-10-02 · **Fork-only (amadurecimento)**
**Autor:** Claudio + Zero · **Base:** v11.14.0+ (fork sincronizado 02/out)

> **A pergunta que origina esta RFC (Claudio, 02/out):** "De que adianta ficar
> colhendo memórias — e eu poder acessá-las — se isso não se consolida em
> CONHECIMENTO? E como fazer o agente APRENDER com isso?"

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
| L4 Feedback | a regra sobrevive por **mérito** (ajudou→sobe, atrapalhou→morre) | 🔴 inexistente |

**Não-objetivo (honestidade intelectual):** não mudamos os pesos do modelo
(fine-tuning). O "aprendizado" vive no **harness/serviço**, não no agente. O efeito
observável é indistinguível de aprender *dentro do contexto de cada sessão* — e é
isso que faz o sistema (não o modelo) ser mais útil a cada semana.

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

L1 feito. L2 infra existe mas ruidosa. L3 so pull manual. L4 zero. Caminho mínimo em §9.

## 8. Decisões abertas
- Injeção proativa: via tool `memory_context(task, budget)` evoluída (pull "gordo")
  ou via hook server-side (push)? Kiro não tem canal de pré-tool-context nativo
  confiável — talvez o máximo viável seja pull barato e automático por tema, não push real.
- Sinal de "uso": como o serviço sabe que uma injeção FOI usada? (rating implícito,
  eco no texto da sessão, harvest reverso). Elo mais incerto do R3.

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
