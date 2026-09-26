# RFC: Harvest Design-Extraction (colher análise longa + ToolResults ricos)

**Data:** 2026-09-26
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** `feat/harvest-design-extraction` (a partir de `upstream/main`)
**Base:** `upstream/main` v11.14.0
**Versão:** 0.1 (draft)
**Inspiração:** diagnóstico #1100 (13/set) + discussion #1287 (beacon loop) + #1103 (LLM summarization, VijaySreekar)
**Reintegra:** o GAP DE PRODUTO deixado aberto pela RFC-harvest-provenance (que resolveu proveniência+tracker, NÃO cobertura de conteúdo rico)
**Status:** DRAFT — amadurecer localmente antes de virar issue/RFC para o Henry

---

## 1. Problema

**"Sessões riquíssimas, colheita pobre."** O harvest atual é estruturalmente incapaz de colher o conteúdo mais valioso das sessões: **análise de design/arquitetura longa** e **ToolResults ricos**. O prato principal é jogado fora; sobram fragmentos.

### Causa raiz (estrutural, não bug pontual)

Duas limitações compostas no pipeline de harvest:

1. **Extractor prioriza frases-gatilho curtas.** O extractor casa padrões como "decidi", "bug era", "causa raiz", "confidence gate 0.6". Análise de design extensa — o formato de trabalho de RFC/arquitetura — **não casa esses padrões e é descartada**. O raciocínio ("*por que* decidimos X") se perde; na melhor hipótese sobra a conclusão seca ("decidiu X").

2. **Parser ignora ToolResults por completo.** `harvest/parser.py:32` — `KIRO_KIND_MAP = {"Prompt": "user", "Response": "assistant", "AssistantMessage": "assistant"}`. A linha 137 (`role = self.KIRO_KIND_MAP.get(kind)`) retorna `None` para `ToolResult` → descartado. Todo dado analítico que embasou decisões (queries de banco, saídas de investigação, diffs, contagens) nunca entra no harvest.

### Evidência decisiva (caso #1100, memória-âncora `241248324`)

As sessões do design do #1100 (agent_id) continham **23 análises de design longas (>400 chars)** em AssistantMessage + **72 linhas de dados analíticos** em ToolResults. O harvest capturou **"1 memória"**. Exemplo real perdido — insight de design puro, não frase-gatilho:

> "A grande maioria não tem identificação do agente. Dos 18.067 ativos: 2.679 têm agent no metadata (~15%)..."

O conteúdo **não se perdeu do disco** (está nas sessões em `ai-backup/kiro-sessions-cli/`), mas **nunca virou memória navegável**.

### O que este RFC NÃO é (desfazendo a contradição do piloto R10)

O piloto R10 (memória `9f490378`, 13/set) mediu que das ~6.929 memórias **já colhidas**, só ~302 eram cruas → **recolheita em massa do que já está no banco = desperdício**. Correto, e **não conflita com este RFC**. São perguntas diferentes:

| Universo | Veredito |
|----------|----------|
| Já colhido (6.929 mems) | Não re-processar em massa — o que virou memória presta (R10) |
| **Nunca colhido (design longo + ToolResults nas sessões)** | **Gap real e aberto — é o que este RFC ataca** |

O argumento "o miner só acha sobras" (jimy-r, #1287) vale para agentes que checkpoint-am bem no momento. O caso #1100 **refuta isso para o nosso uso**: o design substantivo NÃO foi escrito no momento — viveu nas análises longas e ToolResults, e foi descartado por limitação estrutural. Não era sobra; era o prato principal.

### Risco de não fazer

Toda sessão de design denso (como a própria sessão de 26/set: análise do auto-supersede, investigação do `_store_associations_in_graph_table`, raciocínio da Opção 1 no #1318) perde o *porquê* das decisões. O banco acumula conclusões sem fundamentação → o agente futuro repete a investigação do zero.

---

## 2. Objetivo

Adicionar um **modo de extração de design** ao harvest que capture análise longa e (opcionalmente) ToolResults ricos, produzindo memórias densas e navegáveis — sem inundar o banco de ruído.

**Não-objetivos:** recolheita em massa do corpus já colhido (R10 refutou); substituir o extractor de frase-gatilho (coexistem); mineração de transcript cru em busca de "sobras" (#1287 mostrou yield baixo).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1): uma ação por frase, sujeito = componente, testável.

### Funcional — captura de conteúdo rico

- **R1** — THE parser SHALL incluir `ToolResult` no mapeamento de tipos, preservando o conteúdo (com truncagem configurável para saídas volumosas).
- **R2** — WHERE um bloco de AssistantMessage excede um limiar de comprimento (`MCP_HARVEST_DESIGN_MIN_CHARS`, default a definir), THE extractor SHALL tratá-lo como candidato a design-extraction em vez de descartá-lo por não casar frase-gatilho.
- **R3** — THE design-extractor SHALL usar o LLM (cadeia de provider existente) com um prompt específico para extrair decisões de arquitetura, trade-offs e o *porquê* — não apenas a conclusão.
- **R4** — THE design-extractor SHALL preservar proveniência (RFC-harvest-provenance): `harvest:method:llm` + `harvest_model`, mais uma marca de modo (`harvest:mode:design`).

### Funcional — controle de ruído (lição do R10 + #1287)

- **R5** — THE design-extraction SHALL ser opt-in por configuração (`MCP_HARVEST_DESIGN_ENABLED`), default off até validação de yield.
- **R6** — THE design-extraction SHALL registrar uma taxa de adoção desde o dia um (candidatos gerados vs. memórias que sobreviveram ao dedup), para distinguir "yield real" de "gate morto" (lição #1287: yield tem que ser contado).
- **R7** — WHERE um candidato de design é ≥ `similarity_threshold` de uma memória existente, THE ingest SHALL evoluí-la (versioned) em vez de duplicar.

### Não-funcional

- **R8** — THE modo design SHALL rodar preferencialmente server-side no scheduler sobre sinais implícitos (convergência do #1287: capacidade que depende do agente lembrar de chamar não roda), não como ação manual.
- **R9** — THE truncagem de ToolResult SHALL ter teto configurável para não estourar o contexto do LLM nem o custo.

---

## 4. Experimento exploratório necessário ANTES de implementar

Espelhando a disciplina do R10 (pilotar + medir antes de rodar em massa):

1. Selecionar 5-10 sessões de design denso conhecidas (ex.: #1100, #1318, auto-supersede 26/set).
2. Rodar o design-extractor protótipo (prompt LLM "extraia decisões de arquitetura + porquê + trade-offs") contra elas.
3. **Medir:** quantas memórias densas prestáveis por sessão vs. ruído. Comparar com o que o harvest atual capturou dessas mesmas sessões.
4. **Gate de decisão:** só vale implementar em produção se o design-extractor recuperar substancialmente mais conhecimento navegável que o extractor atual, sem inflar ruído. Se o yield for baixo (como o miner do #1287), reavaliar.

---

## 5. Relação com outros itens

- **#1103** (LLM summarization, VijaySreekar) — vizinho temático (resumir memórias via LLM). Este RFC é sobre *extrair* de sessões, não resumir memórias existentes. Coordenar se convergir.
- **RFC-harvest-provenance** — este RFC herda a proveniência dela; é a Fase seguinte ("cobertura de conteúdo" após "proveniência + tracker").
- **#1287** (beacon loop) — a filosofia server-side + implícito + yield-contado vem de lá.
- **Session Miner** (task-orch `89feeabc`, done) — o protótipo standalone que originou o harvest de produção; este RFC reabre a dimensão "conteúdo rico" que o miner não resolveu.

---

## 6. Estado

DRAFT — amadurecer localmente. Antes de virar issue para o Henry: rodar o experimento §4 e trazer números (o padrão que funcionou nos PRs anteriores — negative/positive result com medição).
