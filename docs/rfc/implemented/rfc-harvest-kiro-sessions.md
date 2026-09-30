# Harvest: cobertura multi-formato de sessões Kiro

> **ABSORVIDA → `rfc-ingestao-multi-agente` — camada 2 (perfil de parsing por agente).** Esta RFC deixou de ser item isolado; seu conteúdo é parte da arquitetura guarda-chuva. Mantida como histórico/detalhe da camada.

**Data:** 2026-07-21 (rev. 2026-09-29 — reescrita: mapa real de formatos + eixo idioma)
**Autor:** Claudio + Zero (Kiro)
**Branch de código:** `feat/harvest-kiro-sessions` (fork-only enquanto amadurece)
**Base:** `upstream/main` v11.14.0
**Versão:** 2.0
**Substitui:** `harvest-kiro-ide-sessions.md` v1.0 (jul/2026) — que assumiu que o "IDE" era um formato `history[]` separado. Verificado em 29/set: o acervo IDE **migrou para o layout de workspace do CLI** (payload-wrapped v4), então não há um parser `history[]` a escrever. O que falta é outro.

---

## 1. Problema

O harvest de um único harness (Kiro) precisa lidar com **múltiplos formatos de sessão** acumulados ao longo do tempo e em locais diferentes. Hoje o pipeline colhe bem só um deles. Isto demonstra, em concreto, por que adaptar a memória a um agente que **não é o Claude Code** é uma pilha de trabalho, não um plugue: mesmo dentro de um harness, "alcançável" e "colhido corretamente" são coisas distintas.

### Inventário real deste host (verificado 29/set/2026)

| # | Formato | Local | Volume | Parser lê conteúdo? | `find_sessions` acha? |
|---|---------|-------|--------|--------------------|-----------------------|
| 1 | **CLI legacy** `{kind:Prompt/Response/AssistantMessage, data}` | `~/.kiro/sessions/cli/*.jsonl` | 1104 arquivos | ✅ `_parse_kiro_line` | ✅ glob `*.jsonl` na raiz |
| 2 | **v4 payload-wrapped** `{id, timestamp, payload:{type, content}}` | `~/.kiro/sessions/{workspace_hash}/{uuid}/messages.jsonl` | 33 sessões (inclui as antigas do IDE, fev–mar) | ✅ `_parse_kiro_v4_line` (#1366) | ❌ **glob não desce em `*/*/messages.jsonl`** |
| 3 | **CLI SQLite (fonte viva)** `conversations_v2.value` JSON com `history[]` | `~/.local/share/kiro-cli/data.sqlite3` | 195 conversas | ❌ **parser lê jsonl, não SQLite** | ❌ (não é arquivo jsonl) |

**Nota sobre o "IDE":** a v1.0 desta RFC tratava o IDE como um formato `history[]` próprio em `~/.config/Kiro/.../kiro.kiroagent/`. Em 29/set não há mais `history[]` ali — as sessões do IDE (fev–mar 2026) aparecem agora nos dir-hash de workspace (#2), em v4 payload-wrapped, que o `_parse_kiro_v4_line` (#1366) já lê. Logo, **não há parser IDE a escrever**; o IDE virou o caso #2.

### Os dois gaps reais (medidos, não presumidos)

- **Gap 1 — descoberta (glob), não parsing.** `find_sessions()` faz glob de `*.jsonl` na raiz do diretório. As sessões de workspace estão em `{hash}/{uuid}/messages.jsonl` (dois níveis abaixo). Medição: `find_sessions(~/.kiro/sessions)` retorna **0**; `find_sessions(~/.kiro/sessions/cli)` retorna 1104. As 33 sessões de workspace v4 são invisíveis — **o parser sabe lê-las, o descobridor nunca chega nelas.**
- **Gap 2 — SQLite não é lido.** A fonte viva do CLI v3 é `data.sqlite3` (`conversations_v2`, 195 conversas). O harvest lê apenas `.jsonl`. Cada `value` é um JSON com `history[]` (turnos estruturados `user.content.Prompt.prompt` + `assistant`) e `transcript[]` (strings). O `history[]` é a fonte estruturada limpa.

### Eixo idioma (liga com a RFC design-extraction v0.3, R0.4)

O corpus destes formatos é majoritariamente pt-BR (amostra CLI: text 66 pt / 12 unknown / 0 en). O instrumento de cobertura Phase 0 já mede idioma por bloco (R0.4). Levar a matriz **formato × idioma × cobertura** ao upstream é o dado que prova a complexidade da portabilidade: o Kiro tem 3 formatos, o harvest cobre 1,5, e o conteúdo é pt-BR (que um extractor en-only degradaria).

---

## 2. Objetivo

Fazer o harvest **descobrir e colher todos os formatos de sessão do Kiro** deste host, e produzir números de cobertura por formato e idioma. Sem mudar o que já funciona (CLI legacy) e sem tocar a fonte SQLite viva (ler via cópia read-only).

**Não-objetivos:** escrever um parser `history[]` de IDE (o acervo migrou para v4); recolher em massa o que já foi colhido (R10); o design-extractor (isso é a RFC #1346, degrau seguinte).

---

## 3. Requisitos (prosa + EARS)

### Alvo A — descoberta multi-layout (glob)

- **RA.1** — WHEN `find_sessions` recebe um diretório-raiz de sessões, THE método SHALL encontrar tanto `*.jsonl` na raiz (CLI legacy/Claude) quanto `*/*/messages.jsonl` em subdiretórios de workspace (v4 payload-wrapped), combinando ambos e ordenando por mtime.
- **RA.2** — THE descoberta SHALL permanecer retrocompatível: apontar para `cli/` explicitamente continua funcionando como hoje.
- **RA.3** — THE conteúdo das sessões de workspace SHALL ser parseado pelo `_parse_kiro_v4_line` existente (#1366), sem novo parser.

### Alvo B — parser de SQLite (Crew / fonte viva CLI v3)

- **RB.1** — THE parser SHALL ler `conversations_v2` de um arquivo SQLite, extraindo texto conversacional de cada `value` JSON via `history[]` (user `content.Prompt.prompt` + assistant), preservando ordem e papéis.
- **RB.2** — THE leitura SHALL usar conexão read-only (`file:...?mode=ro`) e NUNCA abrir o arquivo vivo em escrita — ler de cópia/backup para evitar corrupção do banco do Kiro em uso (R3 do inventário).
- **RB.3** — THE parser SQLite SHALL alimentar o mesmo instrumento de cobertura Phase 0 (seen/extracted/dropped + idioma), para que o SQLite entre na matriz de cobertura como os demais formatos.

### Não-funcional

- **RN.1** — Ambos os alvos SHALL ser aditivos: os testes existentes do parser (CLI legacy, v4, coverage instrument) permanecem verdes.
- **RN.2** — Redação de segredos permanece pré-requisito de qualquer ingestão em massa (R1 do inventário) — fora do escopo destes dois alvos (que são descoberta + parsing), tratado no pipeline de ingestão.

---

## 4. Plano de execução (fork-only, 1 commit por alvo)

1. **RFC** (este arquivo) — commit doc.
2. **Alvo A (glob multi-layout)** — TDD G3→G4→G5, 1 commit. Gera número: quantas sessões de workspace passam a ser vistas.
3. **Alvo B (parser SQLite)** — TDD G3→G4→G5, 1 commit. Gera número: cobertura das 195 conversas.
4. **Matriz de números** — rodar coverage+idioma sobre CLI + workspace + SQLite → tabela formato × idioma.
5. **Upstream** — issue de tracking (usual four) + PR para cada alvo, levando os números. 1-PR-por-vez (fila do Henry).

---

## 5. Relação com outros itens

- **#1366** (parser v4 payload-wrapped) — o Alvo A reusa esse parser; só adiciona descoberta.
- **#1346 / RFC design-extraction v0.3** — esta RFC é pré-requisito de cobertura: reconhecer todos os formatos ANTES de medir o gap de design e antes do extractor. O eixo idioma (R0.4) atravessa as duas.
- **#1350** (Phase 0 coverage instrument) — ambos os alvos alimentam o mesmo instrumento; a matriz de números sai dele.
- **Inventário** `INVENTARIO-SESSOES-KIRO-resgate-total.md` (CdIA) — a fonte deste mapa; esta RFC é a versão upstream-facing dos gaps 1 e 2.

## 6. Migração e compatibilidade

- **Alvo A** não muda o que é escrito nem o parsing — só amplia a descoberta. Sessões de workspace passam a ser colhidas daqui pra frente; dedup semântico + tracker protegem contra reprocessar o já colhido.
- **Alvo B** é aditivo (novo caminho de leitura); read-only garante zero risco ao banco vivo.
- Ambos default-safe: nenhum comportamento existente muda sem apontar explicitamente para os novos caminhos.

## 7. Estado

REESCRITA v2.0 (29/set). Mapa de formatos verificado ao vivo. Próximo: implementar Alvo A (glob) → Alvo B (SQLite), cada um fork-only com gate TDD, depois issues+PRs upstream com a matriz de números.
