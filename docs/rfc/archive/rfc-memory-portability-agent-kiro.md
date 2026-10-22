# Anexo (agente): Kiro CLI — rfc-memory-portability

> Anexo-agente da `rfc-memory-portability` (RFC-mãe). Caracteriza UM harness para o lado
> "use in any agent" (§4.1). Kiro é o **espelho de referência**: o harness que JÁ usa o
> memory-service bem — os outros anexos de agente miram esta forma.
> Doc que norteia a construção do adapter. Estrutura: (1) quem é · (2) como tem memória ·
> (3) como conectar · (4) como usar da melhor forma.

## 1. Quem é o agente
Kiro CLI — assistente de código em terminal (CLI). Multi-sessão (3-4 sessões simultâneas por
máquina; 3 máquinas: DNBSCDC289/sirdata/socrates). Sessão efêmera; a continuidade entre sessões
e máquinas vem de fora do agente. Config em `~/.kiro/` (steering, skills, agents, settings/mcp.json).

## 2. Como tem memória hoje
Kiro **não tem memória persistente própria** — o contexto da sessão morre ao fechar. A persistência
é inteiramente delegada a MCPs externos:
- **mcp-memory-service** (este projeto) — memória de longo prazo: fatos, decisões, beliefs, checkpoints. 24k memórias no banco vivo, busca semântica + FTS + grafo + belief store.
- **task-orchestrator** — estado de trabalho (WorkItems, notas, dependências).
- **codebase-memory** — grafo estrutural do código (efêmero por projeto).
Ou seja: Kiro é um harness de "memória zero nativa + MCP como substrato". É o caso de uso ideal
do memory-service — o agente é passageiro, o serviço é a prótese persistente.

## 3. Como conectar
- **Descoberta de MCP:** `~/.kiro/settings/mcp.json` (stdio/HTTP). memory-service entra como server MCP; as tools (`memory_store`, `memory_search`, `memory_context`, `get_bootstrap_profile`...) ficam disponíveis.
- **Autenticação:** local (loopback), sem auth no uso pessoal.
- **Multi-máquina:** o banco é sincronizado entre as 3 máquinas (hoje via OneDrive — a ser trocado por delta-sync, ADR-0002). `agent_id` separa autoria.

## 4. Como usar da melhor forma (o padrão a espelhar)
O que torna o uso do Kiro "rico" (vs. harvest genérico) são os **hooks de steering always-on** que
disparam as tools do serviço nos momentos certos — é isso que um adapter nativo de outro harness
deveria replicar:
- **startup-hook** → no início: `memory_search(time_expr="last 3 days")` + `get_bootstrap_profile` + `mistake_note_search` → injeta contexto da sessão anterior. (É o "push proativo" que queremos automatizar — ver learning-loop N2.)
- **pré-tarefa** → antes de agir: `memory_search(mode=hybrid)` + `memory_context(task)` → traz o relevante ao tema (injeção por tema, L3).
- **checkpoint periódico** (45min/milestone) → `memory_store` com tags controladas.
- **shutdown-hook** → no fim: `memory_harvest` + checkpoint final + commit session.
- **feedback** → rating de memórias úteis (hoje manual; a RFC-MM-01 quer tornar passivo).

**Lição do espelho:** o valor não é "ter acesso ao MCP" — é o harness **chamar as tools certas
nos gatilhos certos** (startup/pré-tarefa/checkpoint/shutdown). Hermes faz isso nativamente com
seu loop de review a cada N turnos (ver anexo-agente Hermes); Kiro faz via steering hooks. Um
adapter nativo = codificar esses gatilhos pro harness, não só expor o server.

## 5. Gaps do Kiro (candidatos a adapter nativo)
- Hooks de steering são **config manual** (steering .md), não um adapter versionado como `claude-hooks/`.
- Injeção proativa (startup) depende do agente lembrar/seguir o hook — não é push automático do serviço (learning-loop N2 resolve).
- Sem lifecycle rico (Claude Code tem 29 eventos de hook; Kiro tem pre/post parcial).
