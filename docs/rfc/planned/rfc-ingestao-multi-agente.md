# RFC: Ingestão multi-agente (arquitetura guarda-chuva do harvest)

**Data:** 2026-09-30
**Autor:** Claudio + Zero (Kiro)
**Base:** `upstream/main` v11.14.0+
**Versão:** 0.2 (draft — visão + triagem C3a validada em acervo real §8)
**Status:** DRAFT v0.1 — Discussion ABERTA 30/set: https://github.com/doobidoo/mcp-memory-service/discussions/1393 (aguarda Henry avaliar o formato em camadas + o 1º incremento Kiro→YAML).
**Absorve (deixam de ser itens isolados, viram camadas):** `rfc-harvest-source-identity` (C1), `rfc-harvest-kiro-sessions` (C2), `rfc-harvest-design-extraction` (C3).
**Vizinhas (não absorvidas):** `rfc-agent-id-multi-agent` (autoria — o que a C1 carimba), `rfc-delta-sync`/`rfc-hub-memoria-centralizada` (o hub sincroniza o colhido), `rfc-memory-portability` (#1364 — esta RFC é a camada discovery/parsing da pilha de 5 camadas), `rfc-importers` (a outra porta de entrada), `rfc-harvest-provenance` (transversal), `rfc-quality-model` (alimenta a C3).

---

## 1. Problema

A qualidade da colheita depende do importador entender **formato E semântica de cada agente**. Hoje o harvest não tem regras adequadas por agente e falha em três eixos que na verdade são um só problema visto de ângulos diferentes:

1. **Regras por-agente hardcoded e espalhadas.** ~10 das 12 regras do `harvest/parser.py` são dados disfarçados de código (mapas kind→role, sets de tipos, marcadores de injeção, cutoffs, globs). Adicionar um agente = editar o parser em 6+ lugares (risco de regressão nos 3 já suportados).
2. **Sinal vs ruído mal separado.** Medição real (150 sessões, pós-I1): dos blocos de texto longo que o extractor descarta, **95% é prosa de análise valiosa** (jogada fora por não casar frase-gatilho) e **4% é JSON/log de tool vazado** (ruído colhido). O parser não distingue raciocínio de dado estruturado.
3. **N agentes na mesma máquina, 1 serviço.** O harvest assume 1 fonte (`MCP_HARVEST_SESSION_DIR` singular). A realidade é 1 serviço de memória servindo **N clientes/agentes** — Kiro CLI (`~/.kiro/sessions/cli/`, formato `{kind}`), Kiro workspace/IDE (`{hash}/{uuid}/messages.jsonl`, v4), Kiro Crew (`data.sqlite3`), e potencialmente OpenClaw, OpenCode, Hermes — cada um com seu path, formato, perfil de regras e identidade.

**Consequência:** conhecimento perde-se por três motivos independentes (formato não reconhecido, ruído misturado ao sinal, fonte não descoberta), e integrar um agente novo é caro e arriscado.

## 2. Objetivo

Uma arquitetura de ingestão **declarativa, plugável e multi-fonte**: o serviço descobre de quais agentes/fontes colher, aplica o perfil de regras de cada agente (em YAML, não hardcoded), separa sinal de ruído por heurística barata antes de qualquer LLM, e carimba a proveniência (`agent_id`) de cada memória. Integrar um agente novo passa a ser **escrever um YAML + testes**, não editar o parser.

**Não-objetivos:** reescrever o parser de uma vez (execução é incremental); logica complexa em YAML (o irredutível fica em hooks de código nomeados); resolver conflito cross-agent (é o hub/`rfc-agent-id` Fase 3); redação de segredos no store local (é no ponto de saída — LLM/sync — RFC própria).

## 3. Arquitetura — três camadas

```
                 ┌─────────────────────────────────────────────┐
   N fontes  →   │ C1  REGISTRO/DESCOBERTA de fontes            │
 (1 serviço,     │     declarativo + auto-descoberta assistida  │  → resolve {agente, path, perfil, identidade}
  N clientes)    └───────────────────┬─────────────────────────┘
                                      ↓
                 ┌─────────────────────────────────────────────┐
                 │ C2  PERFIL DE PARSING POR AGENTE (YAML)      │  → formato, kinds→role, onde está o texto,
                 │     plugável; precedente patterns-por-locale │    markers de injeção, tool-results
                 └───────────────────┬─────────────────────────┘
                                      ↓
                 ┌─────────────────────────────────────────────┐
                 │ C3  EXTRAÇÃO/QUALIDADE                       │  → heurísticas sinal-ruído O(n) 1º
                 │     (declarativo → LLM só depois, gated)     │    (prosa vs JSON/log); LLM destila prosa
                 └───────────────────┬─────────────────────────┘
                                      ↓
                          memória + proveniência (agent_id)  [transversal]
```

### Camada 1 — Registro / descoberta de fontes (absorve `rfc-harvest-source-identity`)
- **RC1.1** — THE serviço SHALL suportar N fontes de colheita registradas, cada uma com `{agente, fonte/path, perfil, identidade}` — não um `MCP_HARVEST_SESSION_DIR` singular.
- **RC1.2** — THE registro SHALL ser **declarativo com auto-descoberta assistida**: o operador registra/ativa os agentes que roda; cada perfil de agente sugere os paths canônicos daquele agente (`discovery.globs`), então ativar uma fonte pode ser só "ativar o agente X" (path default do perfil) ou com path custom.
- **RC1.3** — THE camada SHALL ler o metadado lateral de identidade de cada fonte (verificado ao vivo: Kiro CLI `{uuid}.json` tem `agent_id.name`+`session_created_reason`; IDE `session.json` tem `agentMode`+`workspacePaths`; Crew `conversations_v2`) para preencher a proveniência — sem inferência frágil quando o dado existe.
- **RC1.4** — THE proveniência resolvida SHALL alimentar o `agent_id` da memória colhida (lado de ENTRADA de `rfc-agent-id-multi-agent`).

### Camada 2 — Perfil de parsing por agente, YAML plugável (absorve `rfc-harvest-kiro-sessions`)
- **RC2.1** — THE parsing por-agente SHALL ser dirigido por um perfil declarativo `harvest/agents/{agente}.yaml`, espelhando o padrão já usado para `patterns/{locale}.yaml` (loader + fallback sem-PyYAML + resolução central). Diferença semântica: locale é aditivo/mergeável; agente é **seletivo** (1 perfil por fonte).
- **RC2.2** — THE perfil SHALL declarar: detecção de formato (assinatura da 1ª linha), discovery (globs+exclusões), mapeamento bloco→role, localização do texto (paths), kinds de tool-result + schema de extração, markers de injeção, identidade/proveniência.
- **RC2.3** — WHERE a navegação de estrutura aninhada não couber em seletores de path declarativos (resíduo irredutível, ex: tool-results aninhados), THE perfil SHALL referenciar um **hook de código nomeado** — a lógica complexa fica em Python, não em YAML.
- **RC2.4** — WHEN um agente novo é adicionado, THE integração SHALL ser escrever `agents/{novo}.yaml` + fixtures de teste, sem editar o interpretador do parser.

### Camada 3 — Extração / qualidade (absorve `rfc-harvest-design-extraction`)
- **RC3.1** — THE camada SHALL separar sinal (prosa de raciocínio) de ruído (JSON/log de tool) por **heurísticas declarativas O(n) SEM LLM** (ex: começa-com-`{`/`[`, razão de chars estruturais, densidade alfabética, parse-as-json). Estas rodam ANTES de qualquer LLM.
- **RC3.2** — THE prosa longa retida (que não casa frase-gatilho mas passa nas heurísticas anti-estrutura) SHALL ser candidata a design-extraction. As alternativas baratas (RC3.1 + parsear tool-results) vêm PRIMEIRO; o LLM (RC3.3) só se justifica se o Phase 0 mostrar que o gap sobrevive a elas (correção do Henry, #1364/#1346).
- **RC3.3** — WHERE o LLM-extractor for usado, THE extractor SHALL honrar o locale do operador (`config/locale.py` + patterns per-locale, como NER/NLI/harvest) e reusar a cadeia de providers do harvest.
- **RC3.4** — THE camada SHALL ser opt-in por config (default off até validação de yield) e contar taxa de adoção dia-1 + o 3º estado do dashboard (rodou/conteúdo-presente/pipeline-não-representou).

#### C3a — Triagem de sessão por-agente (novo, validado empiricamente — §8)
Antes de parsear/extrair blocos, uma sessão inteira pode ser descartável. A triagem opera em **dois eixos INDEPENDENTES** (não colapsar num só — colapsar descarta conversa real):
- **RC3.5** — THE triagem SHALL avaliar cada sessão em dois eixos separados: **(A) é teste?** (assinatura de prompt mecânico, declarável por agente — ex. Kiro: `^(hello|turn N|echo|list ALL tools|respond with)`) e **(B) tem conteúdo colhível?** (≥1 resposta `assistant` com prosa real). Uma sessão SHALL ser descartada apenas se **(A) for teste inequívoco OU (B) não tiver conteúdo** — nunca por ser curta.
- **RC3.6** — THE triagem SHALL distinguir os estados terminais: `teste` (assinatura A), `truncada` (pergunta real sem resposta = morte-de-sessão), `vazia` (0 conversa = casca), `dump-volumoso` (bloco único > teto de chars = tool dump), de `ouro`/`conversa` (retidos). O rótulo preserva o julgamento (não chamar conversa-morta de "teste"); o destino segue o eixo B.
- **RC3.7** — THE descoberta SHALL deduplicar sessões por identificador estável da sessão (ex. Kiro: `sess_uuid`), pois o sync (Insync/OneDrive) espelha a mesma sessão sob N workspace-hashes; colher sem dedup multiplica a memória.
- **RC3.8** — WHERE um embedding multilíngue estiver disponível (ex. `paraphrase-multilingual-MiniLM-L12-v2`, já usado pelo serviço), THE camada MAY usar dedup semântico contra o já-colhido como gate barato ANTES do LLM. WHERE só houver embedding en-only (`all-MiniLM-L6-v2`), THE gate semântico SHALL ser desabilitado para corpora não-en (degrada silenciosamente).

## 4. As duas portas de entrada
- **"Use in any agent"** = colher de agentes **locais** (C1→C2→C3 desta RFC). Kiro, OpenClaw, OpenCode, Hermes.
- **"Bring your memory"** = importar de sistemas **externos** (`rfc-importers`: mem0/letta/zep — export, não sessão viva). Compartilha a C2 (tradução formato→schema); a fonte é um arquivo de export, não uma sessão em curso.
Reconciliadas: ambas convergem no schema interno + proveniência. A matriz N×M da portabilidade (`rfc-memory-portability` #1364) usa esta camada de discovery/parsing como o lado reusável.

## 5. Migração (usual four — Henry: migração/compat declarada)
- **Fase 0 — extrair só os DADOS de UM agente (Kiro) para `agents/kiro.yaml`, código intacto.** O parser lê maps/markers/cutoff do YAML em vez das constantes. **Zero mudança de comportamento.** Golden test: `coverage_report()` (instrumento #1350, já existe) byte-idêntico antes/depois nas sessões reais. É o 1º passo, seguro, medível, reversível — o formato que o Henry aceita (1 assunto, compat trivial).
- **Fase 1 — interpretador de paths** (generaliza a navegação C2). Risco real → cobrir com fixtures dos formatos ANTES.
- **Fase 2 — registro multi-fonte (C1)** substitui o `MCP_HARVEST_SESSION_DIR` singular por N fontes, retrocompatível (1 fonte default = comportamento atual).
- **Fase 3 — heurísticas sinal-ruído (C3)**, default off, atrás do Phase 0.
- **Fase 4 — identidade/proveniência (C1 RC1.3/1.4)**: sidecar metadata → agent_id.
Cada fase = 1 PR pequeno. NÃO abrir "reescrita do parser" como um PR.

## 6. Riscos
- **Over-engineering (config Turing-completa):** manter YAML declarativo puro (dados+seletores); lógica em hooks nomeados (RC2.3). Linha explícita.
- **Escopo grande demais para o Henry:** esta RFC é a VISÃO; a execução sai em incrementos (Fase 0 primeiro). A discussion alinha a visão; os PRs saem pequenos.
- **Navegação heterogênea (tool-results):** resíduo irredutível → hook de código, não YAML.
- **Regressão:** o instrumento de cobertura #1350 é o golden test de não-regressão em cada fase.

## 7. Estado
DRAFT v0.2 — visão de arquitetura + triagem C3a validada em dados reais (§8). Próximo: levar à discussion (Henry decide design), depois materializar specs por camada e executar a Fase 0 (Kiro→YAML, golden test). Peças já feitas que encaixam: I0 coverage (#1350), I0-lang idioma (#1379), IA discovery (#1378), IB SQLite (#1379), I1 ToolResults (fork 78e29b05) — todas viram partes das camadas 2/3.

## 8. Evidência empírica — triagem C3a num acervo real de Kiro (30/set)
Curadoria de um backup real de sessões Kiro (workspace layout `{hash}/sess_{uuid}/messages.jsonl`, formato payload-wrapped), validando as regras C3a acima contra o corpus real de dois períodos.

**Acervo histórico (backup jun-jul, 27 sessões):** após dedup por `sess_uuid`, a triagem de dois eixos rotulou **5 OURO + 3 CONVERSA (retidos) vs 15 TESTE + 1 TRUNCADA + 2 VAZIA + 1 DUMP-VOLUMOSO (descartados)** — **~70% descartável por heurística O(n), zero LLM.** O DUMP era um único bloco de **37,6 milhões de chars** (tool_result despejado); se enviado ao LLM sem o teto de RC3.6, seria custo absurdo e ruído puro.

**Sessões vivas (set, mesmo host):** **5 OURO + 6 CONVERSA (retidos) vs 2 TRUNCADA + 10 VAZIA (descartados)** — as 10 VAZIA confirmam o padrão de **morte-de-sessão** (sessão nasce, grava metadata, morre antes de qualquer resposta).

**Lições que moldaram as regras (todas viraram RC3.5-3.8):**
1. **Dois eixos, não um.** Uma primeira heurística "sessão curta = descartável" descartou conversa real curta ("consegue acompanhar o contexto do X?", "pode gerar um docx?"). Separar *é-teste* (assinatura de prompt) de *tem-conteúdo* (resposta assistant) corrigiu — conversa real curta com resposta é RETIDA.
2. **Morte-de-sessão ≠ teste.** Uma pergunta real cuja sessão morreu antes da resposta (`tool_result` vazios, sem `assistant`) é `truncada`, não `teste`: descarta-se pela ausência de conteúdo, mas o rótulo não a confunde com smoke-test.
3. **Ruído estrutural embarcado.** Cada `messages.jsonl` do Kiro embute o system prompt + todos os steering (~25k chars) em cada sessão — o "bloco de 25k" das sessões curtas é steering injetado, não conteúdo (confirma `_is_injected_content`).
4. **Dedup por sessão, não por path.** O sync espelha a mesma `sess_uuid` sob N workspace-hashes; colher sem dedup triplicava.
5. **Economia do gate barato.** Filtro estrutural (eixo A/B) + dedup semântico protegem o LLM: dos acervos combinados, só ~40% das sessões chegariam ao LLM, e o dump de 37M chars nunca.
