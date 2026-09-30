# RFC: descoberta e identificação de fonte de sessão por agente (harvest)

**Data:** 2026-09-30
**Autor:** Claudio + Zero (Kiro)
**Branch de código:** (a definir — `feat/harvest-source-identity`, fork-only enquanto amadurece)
**Base:** `upstream/main` v11.14.0+
**Versão:** 0.1 (draft)
**Status:** DRAFT — investigação de formatos feita ao vivo (30/set); pré-design.

---

## 1. Problema

O harvest hoje trata sessões como **arquivos a serem parseados**, não como **produções de um agente numa encarnação específica**. Isso vira um problema concreto assim que há mais de uma forma de rodar o mesmo agente:

- Um mesmo agente (ex.: "Zero") roda em **três encarnações** do Kiro — CLI, IDE e Crew — e **cada uma persiste em local/mecanismo diferente**. Colher os três num balaio único, sem saber quem produziu o quê, perde a autoria e mistura contextos.
- A questão anterior à leitura de qualquer fonte é: **qual agente/encarnação produziu esta sessão, e onde ele guarda?** Sem responder isso, "conectar o SQLite ao harvest" (issue #1377) é um `if path.endswith('.sqlite3')` cego, sem proveniência.
- O padrão não é exclusivo do Kiro: OpenClaw, OpenCode e Hermes provavelmente seguem linha parecida (cada um com seu mecanismo de persistência para CLI/IDE). Uma camada de identificação de fonte é reusável entre harnesses.

Em resumo: falta uma **camada de descoberta + identificação de fonte**, um passo antes do parsing, que responda "quem/onde" e só então roteie cada fonte ao parser certo, carimbando proveniência.

## 2. Achados da investigação (Kiro, verificado ao vivo 30/set)

Cada encarnação do Kiro já expõe sinais de identidade — só não os lemos hoje:

| Encarnação | Sessão | Metadado lateral de identidade | Sinais "qual agente/contexto" |
|---|---|---|---|
| **CLI** | `~/.kiro/sessions/cli/{uuid}.jsonl` | `{uuid}.json` irmão | `agent_id.name` (ex. `kiro_default`), `session_created_reason` (ex. `subagent`), `cwd`, `title` |
| **IDE / workspace** | `~/.kiro/sessions/{workspace_hash}/{sess_uuid}/messages.jsonl` | `session.json` (por sessão) + `.index/index.json` (por workspace) | `agentMode` (ex. `vibe`), `workspacePaths`, `rootPaths`, `title` |
| **Crew** | `data.sqlite3` → `conversations_v2.value` (JSON) | embutido no `value` | `conversation_id`, `cwd` (via `file_line_tracker`) |

Fatos decisivos:
- **O CLI já carimba `agent_id.name` + `session_created_reason`** no `{uuid}.json` — ou seja, o próprio harness distingue agente principal de subagente. É a matéria-prima da identificação, ignorada hoje.
- **IDE migrou para o workspace layout** (confirmado 29/set) — historicamente era caminho distinto; hoje coincide estruturalmente com o CLI workspace, mas o metadado (`session.json`) é próprio.
- **Distinção CLI vs IDE vs Crew** é possível por estrutura + metadado, sem heurística frágil: flat+`{uuid}.json` (CLI), nested+`session.json` (IDE/workspace), SQLite `conversations_v2` (Crew).

## 3. Objetivo

Introduzir uma camada de **source discovery & identification** que, dado um host, enumere as fontes de sessão **por encarnação/agente**, resolva a proveniência de cada uma (encarnação, agent_id, workspace/cwd), e roteie cada fonte ao parser adequado (`parse_file` jsonl / `parse_sqlite`). Carimbar essa proveniência no harvest, alimentando o `agent_id` das memórias.

**Não-objetivos:** reescrever os parsers (já existem: jsonl, v4, SQLite); resolver conflito cross-agent (isso é a Fase 3 do agent-id / delta-sync); um framework de auto-detecção mágica entre harnesses arbitrários (começa por Kiro, extensível).

## 4. Esboço de requisitos (a detalhar)

- **RA** — descobrir fontes por encarnação num host (CLI jsonl+sqlite, IDE/workspace nested, Crew SQLite), cada uma com um descritor de proveniência (encarnação, agent_id/agentMode, workspace/cwd, session_id estável).
- **RB** — ler o metadado lateral de cada encarnação (`{uuid}.json`, `session.json`, `conversations_v2`) para preencher a proveniência — sem inferência frágil quando o dado existe.
- **RC** — rotear cada fonte ao parser certo (jsonl → `parse_file`; SQLite → `parse_sqlite`), fechando o gap "SQLite reader unreachable" (#1377) pelo caminho correto, não por hardcode.
- **RD** — carimbar a proveniência de agente na memória colhida, integrando com `agent_id` (#1100 / #1278 / #1297) — a identificação de fonte é o lado *de entrada* do que o agent_id resolve na memória.
- **RE** — session_id estável e único por fonte (já resolvido para workspace em #1376: `{workspace_hash}/{session_dir}`), estendido para carregar a encarnação.

## 5. Amarração com o ecossistema (verificado)

Esta RFC é o elo que faltava entre arcos que já existem:

- **agent_id (`rfc-agent-id-multi-agent.md`, #1100 / #1278 / #1297 mergeados)** — carimba `agent_id` nas memórias e resolve conflito cross-agent. **Esta RFC é o lado de ENTRADA (harvest):** de onde o `agent_id` vem na colheita. A rfc-agent-id assumia o `agent_id` como dado; aqui ele é *descoberto na fonte*.
- **delta-sync (`rfc-delta-sync.md`, #1345)** — sync multi-writer com autoria per-agent. A fonte identificada alimenta a autoria que a sync propaga.
- **portabilidade (`rfc-memory-portability.md`, discussion #1364)** — a "pilha por harness" (conector, hooks, skill, override). **A identificação de fonte é uma camada nomeada dessa pilha:** *descoberta de fonte por agente/encarnação*, reusável entre harnesses.
- **harvest-kiro-sessions v2.0 + design-extraction (#1346)** — os parsers/cobertura que ESTA camada alimenta; #1376 (discovery workspace) e #1377 (SQLite parser) são pré-requisitos já em PR.

## 6. Próximos passos

1. Detalhar RA-RE com EARS + amostras reais dos 3 metadados.
2. Piloto: enumerar+identificar as fontes deste host, produzir um relatório de proveniência (quantas sessões por encarnação/agente), sem colher — medir antes de mudar o fluxo (disciplina R10).
3. Abrir como discussion/issue upstream amarrando #1100/#1345/#1364 quando amadurecer.
4. Só então: rotear SQLite no fluxo (fecha #1377 pelo caminho certo) + carimbar agent_id na colheita.

## 7. Estado

DRAFT v0.1 (30/set). Mapa de identificação verificado ao vivo. É o "passo anterior" ao fix de reachability do #1377 — que fica deliberadamente fora do PR #1379 (parser SQLite) e vira trabalho desta camada.
