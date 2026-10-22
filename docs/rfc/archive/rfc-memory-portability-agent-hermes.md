# Anexo (agente): Hermes Agent (Nous Research) — rfc-memory-portability

> Anexo-agente da `rfc-memory-portability` (RFC-mãe). Lado "use in any agent" (§4.1) + "bring" (§4.2).
> Base: análise do código em `~/git/_analise-terceiros/hermes-agent` (4/out, indexado no codebase-memory).
> Relatório: `~/.kiro/tmp/analise-hermes.md`. Ideias de loop (não-portabilidade): `rfc-learning-loop-hermes-ideas.md`.
> Doc que norteia a construção do adapter/importer Hermes. Estrutura espelha o anexo-agente Kiro.

## 1. Quem é o agente
Hermes Agent (Nous Research, MIT) — "o agente que cresce com você". Agente FULL (TS+Py, ~8k py +
3k ts, 17k arquivos), com learning loop built-in: cria skills da experiência, nudges de persistência,
busca sessões passadas, modela quem é o usuário. É MCP-capable (`mcp_tool_lifecycle`, `optional-mcps`).
Já roda no nosso ecossistema: T'Pol/Scotty na VPS cfnarede.dev.

## 2. Como tem memória hoje (caracterização §4.2)
**Loop maduro, store raso.** Três camadas:
- **(a) sessão:** SessionDB (sqlite) + compaction/trajectory_compressor. Busca de sessão por BM25 (keyword), não semântica.
- **(b) persistente:** DOIS arquivos .md roteados — `MEMORY.md` (ambiente/convenções, limite 2200 chars) + `USER.md` (persona/prefs, limite 1375 chars). **~3.5KB TOTAL.** Carregados inteiros no system prompt. **Sem embeddings, sem busca semântica, sem belief/confidence/decay/grafo.**
- **(c) skills:** `~/.hermes/skills/<cat>/<nome>/SKILL.md` + curator (consolidação umbrella).
- **Providers plugáveis:** builtin / Hindsight / Honcho / **Mem0** (padrão de memória plugável JÁ existe no Hermes — reforça viabilidade de plugar o nosso).

**Storage model p/ importer ("bring"):** SessionDB + os 2 .md. A issue upstream **#1095** pede um
"Hermes Agent `state.db` data source adapter (auto-harvest)" — é exatamente o export path a mapear.

**GARGALO (o que nos torna valiosos pra eles):** o teto de ~3.5KB + ausência de recuperação semântica.
Um usuário intenso satura MEMORY.md; o curator poda coisa útil pra caber. Se um fato não está nos
3.5KB carregados, o agente não acha. É o oposto da nossa força (24k mems, semântica, beliefs).

## 3. Como conectar
Hermes é MCP-capable → pode usar o mcp-memory-service como **provider de memória de longo prazo**
(complementar ao memory nativo de sessão). Decisão 17/set: Scotty/T'Pol JÁ usam via MCP genérico.
Caminhos de conexão:
- **Via MCP genérico (já funciona):** Hermes chama `memory_store`/`memory_search`/`memory_context` como tools MCP. É o que acontece hoje.
- **Via provider plugável (adapter nativo):** registrar o memory-service como um provider na arquitetura de providers do Hermes (builtin/Hindsight/Honcho/Mem0/**+nosso**) — integração mais profunda que tool genérica.

## 4. Como usar da melhor forma
O Hermes já tem os GATILHOS que o Kiro simula via steering — nativos no loop:
- **review a cada N turnos/iterações** (background_review fork) → decide persistir memória ou criar skill. Esse é o ponto de auto-capture ideal: redirecionar o "persistir memória" pro `memory_store` do nosso serviço (com proveniência `imported:hermes` / `agent_id`).
- **prefetch/injeção** (memory_provider) → onde o Hermes injeta memória no contexto. Um adapter apontaria o prefetch pro nosso `memory_context(task)` — resolvendo o teto de 3.5KB com recuperação semântica ilimitada.
- **sessão passada** (session_search BM25) → poderia usar nossa busca semântica em vez de BM25.

**Melhor forma (resumo):** manter o loop do Hermes (gatilhos, review, skills) e trocar o STORE raso
(3.5KB .md) pelo nosso store rico via provider/MCP. Hermes ganha capacidade semântica + ilimitada;
nós ganhamos um harness real usando o produto (dogfooding "use in any agent").

## 5. Direção p/ construção (bring + use)
- **Bring (importer):** adapter da fonte `state.db`/SessionDB + os 2 .md → nosso store, proveniência `imported:hermes` (issue #1095). Caracterização de schema: feita (SessionDB sqlite + .md plano char-limited).
- **Use (adapter nativo):** registrar memory-service como provider de memória do Hermes; apontar prefetch→memory_context e persist→memory_store nos gatilhos do loop deles.
- **Decisão aberta (p/ a RFC-mãe):** Hermes como par-alvo prioritário? Antes era "pergunta de refinamento" (linha 117 da mãe); com esta caracterização, a justificativa do adapter nativo é concreta (resolve gargalo real + Hermes já é MCP-capable).
