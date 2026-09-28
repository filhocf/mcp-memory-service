# RFC: Memory Portability — "Bring Your Memory" ⊕ "Use in Any Agent"

**Data:** 2026-09-28
**Autor:** Claudio + Zero (Kiro CLI)
**Branch de código:** — (RFC-mãe / guarda-chuva; código vive nas RFCs-filhas)
**Base:** `upstream/main` v11.14.0+ (agent_id fases 1+2 mergeadas: #1278/#1297)
**Versão:** 0.1 (draft)
**Inspiração / benchmark:** Mnemosyne (MCP concorrente, Hermes-first, com importers de 8 sistemas + adapters nativos) — visto em Workshop TLC. Comparativo e ideias adotáveis já levantados: `conhecimentos-de-ia/pesquisa/comparativo-mnemosyne-vs-memory-service.md` + `mnemosyne-ideias-adotaveis.md` (13/set). `claude-hooks/` (upstream) é o único adapter rico que JÁ temos.
**Fato de base:** Hermes (T'Pol/Scotty) JÁ usa este memory-service como memória de conhecimento duradouro (complementar ao Hermes memory nativo de sessão) — decisão 17/set. O dogfooding "use in any agent" para Hermes já existe via MCP genérico; o arco pergunta o que ganharíamos com adapters *nativos* por harness (como o Mnemosyne tem).
**Status:** DRAFT v0.1 — Discussion ABERTA 28/set: https://github.com/doobidoo/mcp-memory-service/discussions/1364 (1º comentário=arco, 2º=matriz). Aguarda leitura de escopo do Henry.
**RFCs-filhas candidatas:** `rfc-importers` (D9 — o "bring"). NOTA: persona-tier/delta-sync/working-memory (D5/D6/D7) foram, no levantamento de 13/set, marcadas "não vale" como features internas isoladas (temos bootstrap profile / Insync / context-injection). Sob a ótica de ADOÇÃO deste arco, só `importers` se re-habilita claramente; as demais NÃO são peças deste arco (são retrieval/arquitetura interna, arco distinto).

---

## 1. Problema

O memory-service é hoje um excelente **destino** de memória, mas a jornada de adoção real de um usuário tem duas pontas que o projeto não trata como um todo coeso:

1. **"Bring your memory"** — o usuário já tem memória em algum sistema (mem0, letta, zep, Mnemosyne/Hermes, honcho, cognee, supermemory...). Migrar para cá é hoje inexistente fora de `store_memory`/harvest.
2. **"Use in any agent"** — o usuário roda um harness (Claude Code, Kiro, OpenClaw, Cursor, Continue, Hermes...) que precisa usar o store como memória **nativa** (descoberta, auto-capture, injeção de contexto, lifecycle). Hoje só Claude Code tem isso (`claude-hooks/`).

O ponto central desta RFC: **essas duas pontas só entregam valor quando conciliadas por PAR (harness × memory-system).** O caso concreto: *"alguém usa Claude Code + mem0"* exige duas ações encadeadas — (a) **migrar** a memória do mem0 para o store, e (b) **integrar** o store como memória nativa do Claude Code. Uma sem a outra é meia-solução.

### Evidências

- `docs/rfc/rfc-importers.md` cobre só o import pontual (metade "bring"), sem o lado adapter nem a conciliação por par.
- `claude-hooks/` (upstream) é o único adapter rico; Kiro/OpenClaw/Cursor/Hermes não têm equivalente.
- O Mnemosyne (benchmark) já faz as duas metades (8 importers + Hermes-first nativo); nós não. É o gap estratégico de adoção OSS.
- agent_id (#1278/#1297) já entregou a **fundação** (identidade portável) sem que o arco que ela serve estivesse nomeado.

### Causa

Falta um **modelo de portabilidade** que (1) nomeie as duas metades, (2) defina o método de investigação de dois lados (entender o harness E o memory-system concorrente), e (3) priorize os pares.

---

## 2. Objetivo

Estabelecer o **arco de portabilidade de memória** como linha de trabalho de primeira classe do projeto, conciliando as duas metades por par, com base no gap de adoção que o Mnemosyne expõe (ele faz; nós não).

Entregas conceituais desta RFC-mãe:
1. **Modelo das duas metades:** `import` (bring) ⊕ `adapt` (use), conciliadas por par.
2. **Método de investigação de dois lados** (matriz harness × memory-system) — ver §4.
3. **Feature-parity study:** comparar funcionalidades dos memory-systems concorrentes → identificar o que vale trazer (eleva o nível do projeto). É trabalho de pesquisa que precede o código.
4. **Priorização de pares:** primeiro par de adoção externa = **Claude Code ⊕ mem0** (harness + memory-system mais populares). Hermes já usa o serviço (não é par a construir); Mnemosyne é benchmark, não algo que rodamos.

**Não-objetivos:** implementar todos os pares; substituir as RFCs-filhas (esta as orquestra, não as reescreve); federated retrieval multi-server (#57, fora de escopo).

---

## 3. Requisitos (Prosa + EARS)

> Convenção EARS (DEVELOPMENT-STANDARDS §8.4.1). Requisitos de arco (alto nível); os detalhados vivem nas RFCs-filhas.

**R1**: A jornada de adoção é conciliada por par.

> EARS: WHEN a user adopts the service for a given harness that already uses an external memory system, THE project SHALL provide both an importer for that memory system AND a native adapter for that harness.

**R2**: Cada memory-system alvo é caracterizado antes de codar.

> EARS: WHEN a memory-system is targeted for import, THE arc SHALL first produce a characterization of its storage model, schema, feature set, and export path.

**R3**: Cada harness alvo é caracterizado antes de codar.

> EARS: WHEN a harness is targeted for a native adapter, THE arc SHALL first produce a characterization of its MCP discovery, hook/lifecycle model, auto-capture points, and context-injection path.

**R4**: O estudo de paridade alimenta o backlog de features.

> EARS: WHEN the feature-parity study finds a capability in a competing system worth adopting, THE arc SHALL record it as a candidate feature with rationale, not silently copy it.

**R5**: A proveniência de origem é preservada ponta a ponta.

> EARS: WHEN a memory is imported, THE system SHALL preserve `imported:<system>` provenance so the adapter side can reason about origin (aligns with rfc-importers R3).

### Não-Funcional

**R6**: Os pares são independentes.

> EARS: THE work for one pair SHALL not depend on the availability of another pair's harness or memory-system SDK.

**R7**: A fundação já existente é reusada, não duplicada.

> EARS: THE arc SHALL build on agent_id (#1278/#1297) for portable identity and delta-sync (#1345) for synchronization rather than introducing parallel mechanisms.

---

## 4. Design — método de investigação de dois lados

O núcleo do arco é uma **matriz N harnesses × M memory-systems**. Para cada célula que vira par priorizado, dois levantamentos precedem o código:

### 4.1 Lado do harness (para o adapter — "use in any agent")
Caracterizar, por harness:
- **Descoberta de MCP:** como registra/descobre servers (config, mcp.json, plugin)?
- **Hooks / lifecycle:** tem session-start/end? pre/post-turn? (Claude Code tem; Kiro tem parcial)
- **Auto-capture:** onde capturar conversa/decisão automaticamente?
- **Injeção de contexto:** onde e como injeta memória no prompt/contexto?
- **Referência:** `claude-hooks/` (upstream) como padrão a espelhar.

### 4.2 Lado do memory-system (para o importer — "bring your memory")
Caracterizar, por sistema (mem0/letta/zep/Mnemosyne/honcho/cognee/...):
- **Storage model:** o que armazena (chunks? facts? grafos? episódios?)
- **Schema:** campos, tipos, metadados, timestamps.
- **Features trazíveis:** o que ele faz que nós não fazemos (feature-parity — R4).
- **Export path:** API/SDK/dump para extrair.
- Mapeamento para nosso schema (content, tags, importance, timestamps) — reusa rfc-importers R2.

### 4.3 Conciliação por par
Um par entregue = importer (4.2) + adapter (4.1) + teste E2E da jornada completa (migrar + usar).

### 4.4 Pares priorizados
| Prioridade | Par | Papel | Nota |
|-----------|-----|-------|------|
| 1 | **Claude Code ⊕ mem0** | adoção externa exemplar (harness mais popular + memory-system mais popular) | adapter existe (`claude-hooks/`); falta importer mem0 |
| 2 | **Kiro ⊕ (harvest atual)** | nosso próprio harness — adapter nativo espelhando `claude-hooks/` | Kiro hoje usa harvest genérico, sem hooks ricos |
| 3+ | OpenClaw, Cursor, Continue ⊕ (letta/zep/...) | expansão da matriz | por demanda |

> **Sobre Hermes:** NÃO é um par a construir — Hermes (T'Pol/Scotty) **já usa** este serviço via MCP genérico (decisão 17/set). Entra no arco como pergunta de refinamento ("adapter Hermes-nativo valeria, como o Mnemosyne tem?"), não como primeiro par.
> **Sobre Mnemosyne:** é o **benchmark** do arco (Hermes-first, 8 importers, adapters nativos) — objeto do feature-parity study (§4.2), potencialmente um importer (trazer memória de quem usa Mnemosyne), NÃO algo que rodamos.

---

## 5. Relação com outras RFCs (o que É e o que NÃO É deste arco)

**Deste arco (adoção/portabilidade):**
- **D9 rfc-importers** → o lado "bring". Re-habilitado por este arco: em 13/set foi marcado "não vale" como feature interna, mas sob a ótica de ADOÇÃO OSS (reduzir fricção de migração de mem0/letta/zep) volta a ser estratégico. Esta RFC-mãe adiciona a caracterização prévia (R2) e a conciliação por par.
- **Grupo G (adapters)** → o lado "use", um adapter nativo por harness, espelhando `claude-hooks/`.
- **Feature-parity study** → já iniciado (`comparativo-mnemosyne-vs-memory-service.md` + `mnemosyne-ideias-adotaveis.md`); estender para mem0/letta/zep.

**NÃO deste arco (arco de retrieval/arquitetura interna, distinto):**
- D1 quantization, D3 query-intent, D4 ranking/Weibull, polyphonic recall → melhoram o motor de busca, não a portabilidade. Ficam no seu próprio agrupamento.
- D5 working-memory, D6 persona-tier, D7 delta-sync → em 13/set marcados "não vale" isoladamente (temos context-injection / bootstrap profile / Insync). delta-sync evoluiu depois (#1345, Henry pediu) mas é infra de sync, não portabilidade de adoção. Não são filhas deste arco.

> Correção de premissa (28/set): a v0.1 inicial listava D5/D6/D7 como "peças do arco" — errado. A pesquisa de 13/set já os havia descartado como features internas. Este arco é sobre ADOÇÃO (importers + adapters + parity), não sobre orquestrar as RFCs D de retrieval.

---

## 6. Fora de Escopo

- Implementação de qualquer par nesta RFC (é a mãe; código nas filhas).
- Federated retrieval entre múltiplos servers (#57).
- Exportar do nosso store PARA outro sistema (só importamos — rfc-importers §5).

---

## 7. Critérios de Aceite (da RFC-mãe, não do código)

- [ ] Modelo das duas metades (import ⊕ adapt, conciliado por par) aceito como linha de trabalho.
- [ ] Método de investigação de dois lados (§4) validado pelo Henry como o groundwork correto.
- [ ] Feature-parity study reconhecido como pré-código (não copiar às cegas).
- [ ] Par 1 (Hermes ⊕ Mnemosyne) confirmado como primeiro alvo.
- [ ] RFCs D5/D6/D7/D9 re-enquadradas como filhas deste arco no roadmap.

---

## 8. Insumos já coletados no CdIA (não re-pesquisar)

O groundwork de dois lados (§4) já tem base substancial no CdIA — a RFC parte disto, não do zero:

**Lado memory-system ("bring" / feature-parity §4.2):**
- `pesquisa/comparativo-mnemosyne-vs-memory-service.md` + `pesquisa/mnemosyne-ideias-adotaveis.md` — Mnemosyne (8 importers, BEAM, sync cripto, Hermes-first). Benchmark do arco.
- `pesquisa/comparativo-hermes-vs-mcp-memory-service.md` — **achado-chave:** Hermes memory built-in já tem **provedores pluggáveis** (builtin/Hindsight/Honcho/**Mem0**). "Provider de memória plugável" já é padrão existente → reforça viabilidade do arco.
- `pesquisa/compilacao-final-analises-mcp-memory.md` + análises OpenRouter/gpt-oss/poolside.

**Lado harness ("use" / adapter §4.1):**
- `harness/anatomia-do-nosso-harness.md` — modelo completo do nosso harness Kiro (steering/skills/hooks/14 MCPs) = a caracterização §4.1 para o par Kiro.
- `harness/context-engineering-stack.md`, `harness/o-que-faz-um-agente-melhor.md`, `harness/push-automatico-contexto.md` — injeção de contexto.
- `pesquisa/agentes/raio-x-agentes-ia-2026.md`, `pesquisa/agentes/comunicacao-entre-agentes-mercado.md` — panorama de harnesses do mercado.

**Ação:** consolidar esses insumos num anexo de feature-parity ao abrir a Discussion (já respondem boa parte de §4.1/§4.2 para Kiro, Hermes e Mnemosyne).

---

## 9. Anexo — Lista inicial de referência (a matriz N × M)

Base para o **segundo comentário** da Discussion: os dois eixos já mapeados no CdIA (`raio-x-agentes-ia-2026.md` + `comparativo-mnemosyne-vs-memory-service.md`). Não é exaustiva — é o ponto de partida a validar/estender com o Henry e a comunidade. ⚠️ Dados de mercado do raio-x (nº de hooks, modelo de memória de cada harness) são de meados/2026 e devem ser re-verificados antes de virarem afirmação pública na Discussion.

### 9.1 Harnesses / agentes (eixo "use in any agent")
Com o modelo de memória de cada um (do mapa de dialetos):

| Harness | Tipo | Memória persistente hoje | Hooks/lifecycle | Adapter nosso? |
|---------|------|--------------------------|-----------------|----------------|
| **Claude Code** | CLI | automatic memory | 29 eventos de hook | ✅ `claude-hooks/` (upstream) |
| **Kiro** | CLI | MCP (memory-service) | pre/post hooks | 🟡 harvest genérico, sem adapter rico |
| **Hermes** | agente | layered (FTS5+LLM+providers pluggáveis: builtin/Hindsight/Honcho/Mem0) | — | usa via MCP genérico (já) |
| **OpenClaw** | CLI persistente | built-in RAG | — | ❌ |
| **Cursor** | IDE | — | — | ❌ |
| **Windsurf** | IDE | — | Cascade | ❌ |
| **Cline** | ext. VSCode | — | — | ❌ |
| **Codex CLI** | CLI | — | — | ❌ |
| **Aider** | CLI | — | — | ❌ |
| **Gemini CLI** | CLI | — | — | ❌ |
| **GitHub Copilot** | ext. IDE | — | — | ❌ |

### 9.2 Memory-systems concorrentes (eixo "bring your memory")
Os 9 que o Mnemosyne já importa (nosso benchmark) — candidatos a `BaseImporter` (rfc-importers):

| Sistema | O que é | Prioridade de importer |
|---------|---------|------------------------|
| **mem0** | memory layer popular p/ agentes | 1 (par Claude Code ⊕ mem0) |
| **letta** (ex-MemGPT) | memória com paginação de contexto | 2 |
| **zep** | memória temporal + knowledge graph | 2 |
| **honcho** | memória de usuário/persona | 3 |
| **hindsight** | provider já plugável no Hermes | 3 |
| **cognee** | memória em grafo | 3 |
| **supermemory** | memória universal SaaS | 3 |
| **holographic** | Hermes Holographic Memory | oportunista (se houver base a migrar) |
| **agentic** | import LLM-guided (genérico) | transversal |

### 9.3 Como usar esta matriz
Cada célula (harness × memory-system) é um par potencial. Priorizamos pela popularidade e pela dor real: **Claude Code ⊕ mem0** primeiro (adapter existe, falta importer mem0). A lista se estende conforme demanda da comunidade responder à Discussion.

---

## 10. Próximos passos

1. Amadurecer esta RFC localmente (v0.1 → v0.2), incorporando os insumos do §8.
2. Abrir **Discussion** no GitHub (categoria Ideas) pingando @doobidoo — 1º comentário: o arco + método + pedido de leitura de escopo. **2º comentário: a matriz de referência (§9)** — lista inicial de harnesses + memory-systems para ancorar a conversa.
3. Com OK: consolidar feature-parity (mem0/letta/zep, estendendo o comparativo Mnemosyne existente).
4. Primeiro par de adoção: Claude Code ⊕ mem0 (adapter existe; falta importer mem0).
