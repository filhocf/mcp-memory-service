# ESTADO — mcp-memory-service (Claudio)

> **Atualizado: 21/out/2026** @ sirdata · fork/main 9d62f6d3 · chore/rfc-cleanup-20261021 @ d2466633 · 453 à frente / 17 atrás do upstream.
> **Feito embaixo, a fazer em cima.** Arquivos-irmãos: `ARCOS.md` (mapa denso do agente) · `LEDGER-feats.md` (invariante) · `diario-de-gates.md` (ciclos) · `AUDITORIA-rfcs-2026-10-21.md` (relatório fonte).

## ⚡ ATUALIZAÇÃO 21/out — limpeza da árvore de RFCs

- **89 RFCs auditadas** (64 `planned/`, 25 `implemented/`). **17 em planned já entregues** (delta-sync inteiro, D3/D7/D8, store-visibility, agent-id-streamable, fase0-kiro, hybrid-http); **20 mortas** (3 absorvidas pela ingestão, 2 superseded pelo delta-sync, 5 anexos de portabilidade, 4 de refactor, 3 gates G0, 1 genérica); `rfc-s2-belief-store` reaberto (marcada "implemented por engano" na própria RFC); `_index.md` regenerada de 47 para 89.
- **2 SHAs marcados "VERIFICAR" desde 15/set → VEREDITO:** `4358c29b` (NER PT-BR/EN) e `d017a1d4` (harvest Kiro IDE) **ambos portados ao upstream** (`upstream/main` tem `ner_patterns/pt_BR.yaml` e `messages.jsonl` no harvester/parser). Lênia encerrada.
- **Código fork-only real: 16 arquivos novos** + 33 modificados em `src/`. Os 453 commits à frente são documentação (60 tocam o ESTADO.md, 32 o LEDGER).
- **Doc reorganizado:** feito para baixo, a fazer em cima — ordem pedida pelo Claudio.

```
mcp-memory-service (fork) ── 21/out
│  Legenda: ✅ MERGED/feito · 🟢 fork-only feito · 🟡 parcial/design · 🔴 a fazer
│
├─ ━━━ A FAZER (feita para baixo) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
│
├─ ⭐ P1 WORKING MEMORY ── a maior lacuna prática · 99% do contexto quente fora do pull
│   │   "numa sessão longa, memórias relevantes criadas depois da abertura não são re-injetadas"
│   │   RFC pronta: docs/rfc/planned/rfc-working-memory (DRAFT 13/set, EARS R1-R7)
│   │   branch feat/working-memory INEXISTENTE · working_memory ausente de src/
│   ├─ F1 G0 spec fechada para o seven ────── 🔴 a fazer
│   ├─ F2 implementar camada working_memory ─ 🔴 (store tier próprio + TTL + eviction)
│   │     ├─ injeção por turno, não por sessão ─ 🔴
│   │     └─ promoção working → episodic idempotente ─ 🔴
│   └─ F3 medir gap após implementação ────── 🔴
│         aceitação: gap de 99% → ≤10% · payload ≤2x orçamento · 0 dep
│
├─ ⭐ P0 SÍNTESE DE BELIEF ── a doença · derivação copia 314/314 verbatim
│   │   "o que É um belief, QUEM o escreve abstrato, COMO sabemos que foi útil?"
│   │   RFC G1 pronta: docs/rfc/planned/rfc-belief-synthesis.md · autor: fork-only
│   ├─ F1 síntese real em derive_beliefs (claim, não cópia) ── 🔴
│   │     ├─ ligar rewriter LLM que a RFC assumiu ── 🔴
│   │     ├─ representante por centralidade ─────── 🔴
│   │     └─ ingerir decision/learning/mistake ────── 🔴
│   ├─ F2 singular path (belief de fonte ÚNICA) ── 🔴
│   └─ F3 citar entrada (decision/learning) ────── 🔴
│         aceitação: Recall@pool 0,30 → ≥0,80 · verbatim <20%
│
├─ P2 ABSTENÇÃO + MULTILÍNGUE ── nenhuma RFC · dor medida
│   │   "não sei" confiável ≠ busca que devolve vizinho semântico
│   │   PT 16% vs EN 50% (mesmo acervo); 3 buscas para concluir ausência
│   ├─ F1 RFC de abstenção (limiar de confiança + resposta assinada) ─ 🔴
│   └─ F2 expansão bilíngue da query (sem re-embed) ──── 🔴
│         aceitação: recall PT ≥ recall EN −10 p.p.
│
├─ P3 SINAL DE USO NÃO CIRCULAR ── injected_then_used=0 estruturalmente
│   ├─ spec-b/c/e fork-only e medidos ──────── 🟢 feito (invalidate no 07/out)
│   ├─ mm-01/mm-02/mm-03 (trilogia) ──────── 🟢 resgatada (branch validacao/, 93 testes)
│   └─ registrar devolução do usuário ────── 🔴
│         aceitação: injected_then_used > 0 com rastreio da fonte
│
└─ P4 MEMÓRIA PROCEDURAL ── "o que aprendo sobre COMO fazer não vira skill"
    ├─ rfc-skill-auto-generation (30/set) sem código ─ 🟡 parada
    ├─ mistake_note_search inoperante (bug de produto) ─ 🔴 a corrigir
    └─ pós-processamento de padrões repetidos ──── 🔴
          aceitação: N padrões repetidos -> skill candidata com OK humano
```

## 🔴 Falta fazer

- **F1** — Working memory (P1): G0 spec fechada para o seven, com critério de aceitação (gap de 99% → ≤10%; payload ≤2x orçamento; evicção por TTL; promoção idempotente). Branch não existe — criar `feat/working-memory` de `upstream/main`.
- **F2** — Síntese de belief (P0): implementar síntese real em `derive_beliefs` (claim abstrato do cluster, não cópia verbatim). Dependência: nada de código novo, é o arco de síntese.
- **F3** — Abstenção + multilíngue (P2): escrever a RFC (hoje inexistente); correção barata = expansão de query bilíngue, sem re-embed.
- **F4** — Sinal de uso (P3): sinal positivo real + negativo (re-query após injeção), correlacionado por source_hash.
- **F5** — Memória procedural (P4): fixar `mistake_note_search` (bug de produto), construir skill a partir de padrão repetido.

## ✅ Feito (ordem inversa do tempo, mais recente primeiro)

- **20/out** — UIAA/hermes fechado: D3 (mms-doctor, 49 testes, G6 6/6), D7 (instalador, 22 testes, E2E em Hermes limpo + banco zerado, idempotente, uninstall cirúrgico), D8 (docs/agents/hermes.md).
- **19/out** — Índice uniforme em produção (vectors re-embedados para paraphrase-multilingual); régua Recall@10 0,567 / @30 0,675 / @100 0,750.
- **18/out** — baseline de recall com régua consolidada (18/out); importador do state.db (G6); chunking testado (resolvido na amostra, falha em escala).
- **17/out** — redisponibilidade do venv ONNX blindada;INC2+INC6 entregues; INC4 reposicionada como arco próprio (40e6ecfb).
- **16/out** — 2 commits não-pushados na main (d91fda19 filtro degenerado, c6234c06 injeção-memoria-crua +0,558 recall provenle).
- **15/out** — sync upstream v12.0.0; RFC inter-agent inbox escrita e revisada (e2fd1cf0, fork main).
- **14/out** — Recall@pool 0,30 medido; RFC belife síntese escrita; 6 degenerados expurgados.
- **13/out** — INC6 (trigger de importância) no vivo (spoke sirdata); fever, INC2+INC6 done;INC4 reposicionada.
- **12/out** — pymongo; 9 IAs reagendar dreaming; RFC-MM-01 (feedback PASSIVO) reescrita.
- **11/out** — harvest fix (modo as sessões do CLI), tracker reconstruído 19→1299 no vivo.
- **10/out** — pipeline proveniência 63ddfaaa aplicado no vivo.

## 📌 Histórico (índice por mês)

- **20/out** — [CHECKPOINT-2026-10-20-orc-220-e-board.md](CHECKPOINT-2026-10-20-orc-220-e-board.md) — Orc 2.2.0 publicado, AC-D1 final (−13,86%), RELEASE 2.2.0/2.1.0 no board, 10 reparents, lateral de Arcos 29 raízes, DEC -3.
- **19/out** — [hermes-primeira-classe.md](hermes-primeira-classe.md) — Hermes como cliente de 1a classe, inventario medido.
- **18/out** — [diagnostico-precisao-recuperacao.md](diagnostico-precisao-recuperacao.md) — acurácia da recuperação (recorrer, não recomendar), a diferença do estado (fixada 19/out); [relatorio-noturno-20261018.md](relatorio-noturno-20261018.md) — chunking testado, resolve na amostra, falha em escala; [plano-autonomo-20261018.md](plano-autonomo-20261018.md) — contrato de autonomia.
- **17/out** — [observacoes-metodologia-20261017.md](observacoes-metodologia-20261017.md) — 69 features sem linha no LEDGER, cadence de specs; [plano-autonomo-20261017.md](plano-autonomo-20261017.md) — receita no env por host.
- **16/out** — [política-contexto-e-custo.md](politica-contexto-e-custo.md) — 210k → 150k, orçamento instalado.
- **15/out** — Job `ensure-onnx-venv.sh` na unit de systemd; nota no Gate 3 — não rodar `uv sync` cru.
- **14/out** — [worktrees.md](worktrees.md) — registro canônico dos worktrees, um por sessão.

## Não feito (decisão deliberada, não pendência)

- **Provider desligado** (`hermes memory status` → `Provider: (none)`): com a MEMORY.md ok, ligar provider traria dual-write, e a MEMORY.md é a única fonte que o Hermes injeta no system prompt. Funciona, mas não é o caminho do runtime.
- **Delta-sync Crons Insync**: aposentados (superseded pelo delta-sync nativo).
- **Reranker ONNX**: medido (+16,7 p.p. @10, IC95 [+10,0 · +23,3], zero casos pioraram, bootstrap pareado 10.000). Não ligado — o provedor do Hermes dá contexto suficiente.
- **Kiro CLI headless como LLM provider**: `rfc-kiro-headless-llm-provider` — não implementado.
- **HOOKS TUI/CLI**: `HOOKS.md` e `A3-README.md` cobrem a mecanica; hooks de shell permitem lades; o `mms-participation-summary.md` assina o protocolo A3.
- **Board orc**: `ARC: mms` criado; hierarquia nova ativa; QueryFlow ainda não reorganizado mesma forma.
