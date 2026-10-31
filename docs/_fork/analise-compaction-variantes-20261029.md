# Análise: variantes de design da compaction de sync_events (P1 Greptile)

**Data:** 2026-10-29 · **Autor:** Zero (+ análise seven) · **Contexto:** PR #1721 (fix/sync-event-log-compaction)
**Status:** em decisão de arquitetura; PR a ser convertido para draft.

## Problema (P1#1 do Greptile, confirmado no código)

A compaction colapsa a cadeia de `update_metadata` por `content_hash` num evento consolidado
com UM par HLC (o do vencedor-geral via `_winning_row`/`_ev_winner_key`). Mas `apply._resolve_md_fields`
faz LWW **field-level** (cada campo tem vencedor próprio pelo menor `_winner_key`, lido do ENVELOPE
hlc_physical/hlc_logical da linha). Em compaction **parcial** (watermark = MIN(last_seq_pushed) corta
no meio da cadeia), um campo cujo edit vencedor está ACIMA do watermark não é colapsado, mas o
consolidado abaixo passa a carregar, para aquele campo, o clock do vencedor-geral (inflado) → pode
vencer incorretamente sobre o edit real acima. Os testes atuais (T1/T5/T7 + E2E) só provam colapso
TOTAL; o caso parcial com campo-vencedor cruzando o watermark não é coberto.

## P1#2 (independente): event_id determinístico sem conteúdo

`event_id = cmp-sha256(content_hash:win_phys:win_log)` não inclui o payload. Dois peers que compactam
cadeias DIVERGENTES com o mesmo par HLC vencedor geram o mesmo id com payloads diferentes →
`apply_remote_event` (apply.py:182) rejeita o segundo como "replay with altered payload" → descarte
silencioso. Correção ortogonal: incluir `hash(updates)` no id.

## P2: DELETE … IN com 1 parâmetro por evento

Cadeia > SQLITE_MAX_VARIABLE_NUMBER (~999/32766) estoura no DELETE e o savepoint reverte tudo. Precisa
chunking do delete dentro do mesmo savepoint.

## Variantes

| Variante | Resolve P1#1? | Contrato/schema | Complexidade | Risco lateral |
|----------|---------------|-----------------|--------------|---------------|
| **A** clock-por-campo no consolidado | Sim, em tese | MUDA o contrato (par HLC vive no envelope, não no payload; bootstrap/seed/version-negotiation leem do envelope) | Alta | Alto (peers legados, reintroduz "MAX por coluna inventa clock") |
| **B** all-or-nothing por hash (só colapsa se cadeia viva inteira ≤ watermark) | Sim, por construção (reduz ao colapso total já provado) | Nenhuma mudança | Baixa (um predicado em _plan_for_hash) | Baixo |
| **B'** colapsa prefixo < watermark só se vencedor-geral do prefixo == vencedor de cada campo do prefixo | Sim | Nenhuma | Média | Médio |
| **C1/C2** prefixo contíguo / baseline-create | Parcial / abre fronteira create-delete | — | Média-Alta | Médio-Alto |

## MEDIÇÃO (banco real, DNBSCDC289, lab-bloat/base.db, 29/out)

- watermark = MIN(last_seq_pushed) = **1.383.010** = MAX(seq). **gap = 0.**
- update_metadata total = 1.345.590; **abaixo do watermark = 1.345.590 (100%)**.
- hashes com update_metadata ACIMA do watermark = **0**.

**Consequência:** na topologia real (1 peer hub-vps, push a cada 1 min `MCP_SYNC_SCHEDULE=1m`), o
push é contínuo → last_seq_pushed acompanha max_seq → **nada fica acima do watermark**. B captura
~100% do inchaço. B e B' são equivalentes na prática; a perda de agressividade de B é hipotética
(só numa janela transitória ≤1min ou peer offline longo, auto-corrigível no avanço do watermark).

## Recomendação

- **Variante B** (all-or-nothing por hash, respeitando incarnação viva via create_key).
- **+ P1#2**: incluir hash do payload no event_id determinístico.
- **+ P2**: chunking do DELETE.
- Testes a adicionar no G3: campo-vencedor acima do watermark em compaction parcial (prova que B pula
  o hash); all-or-nothing respeita incarnação viva (edit morto acima não bloqueia); ids determinísticos
  com payloads divergentes; cadeia grande (>999) força chunking; convergência pós-compaction parcial.

## Aberto para parecer externo (T'Pol)

Se, na topologia que ela opera (VPS como hub, múltiplos spokes), o gap watermark↔max_seq for
materialmente > 0 (peers que atrasam), B deixaria as cadeias quentes sem compactar e B'/A voltariam
a importar. Pedir a medição do lado dela.
