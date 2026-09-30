# G0 — I1: visibilidade de ToolResults no formato {kind} atual do Kiro CLI

**Data:** 2026-09-30 · **Autor:** Claudio + Zero + arch-analyst · **Fase:** G0 (análise, sem código)
**Arco:** 1 (harvest multi-formato) · **Refs:** RFC #1346 v0.4, parser.py `_parse_kiro_line`

## Achado que corrige premissa (verificado no disco)

A RFC #1346/roadmap diziam "harvest ignora ToolResults + thinking se perde". Fatos numa sessão CLI real (`4c393350...jsonl`):

- **`thinking` (430 blocos): TODOS redacted** — `data.text=""` + `redactedContent:[bytes]`. O extended-thinking é criptografado no disco. **IRRECUPERÁVEL.** Fica só CONTADO (dropped, sem text=), nunca marcador (poluiria idioma).
- **`toolUse` (408 blocos):** só args/toolName, sem texto conversacional. Não é alvo.
- **Dado rico de tool está em DOIS lugares no formato {kind} do CLI (o que o CLI grava HOJE — o código chama "legacy" por herança, mas é o corrente):**
  - **Mensagem `ToolResults` (387)** — `kind` de MENSAGEM (topo do obj). Dropada na guarda `if not role` (parser.py ~373), ANTES do loop de blocos.
  - **Bloco `toolResult` (407)** — dentro de `content[]` de AssistantMessage. Dropado no `else` genérico (parser.py ~407).
- Ambos têm a MESMA estrutura interna: `data.content[] → {kind:"json"|"text", data:{content:[{type:"text", text:"..."}]}}`. A mensagem `ToolResults.data.content[]` contém blocos `toolResult`.

## Design (recomendação arch, validada)

1. **Helper único** `_extract_kiro_toolresult_text(tr_data) -> str|None`: navega `content[]→kind json/text→data.content[].text`, defensivo (guardas isinstance em cada nível, listas vazias, kinds inesperados → skip, nunca lança). Consolida segmentos com `\n\n".join` → 1 texto.
2. **Mensagem `ToolResults`:** ramo dedicado ANTES da guarda `if not role` em `_parse_kiro_line`. Itera `data.content[]`, para cada bloco `toolResult` chama o helper. role="assistant". 1 ParsedMessage consolidado.
3. **Bloco `toolResult`:** no loop de content[], `elif block_kind in {"toolResult","ToolResult","tool_result"}` chama o mesmo helper.
4. **Semântica espelha o v4** (`_parse_kiro_v4_line` tool_result): role="assistant"; filtro `_is_injected_content` (NÃO `_is_system_content` — SEM cutoff 10k, tool result longo é o dado rico); texto verbatim.
5. **Coverage key:** `"ToolResults"` (mensagem) / `"toolResult"` (bloco) — distintas de `"tool_result"` do v4, para o instrumento rastrear ganho por formato (não unificar).

## Riscos (do arch)
- **Alto — segredos em ToolResults:** é problema da INGESTÃO (redação), NÃO do parser (que é leitura fiel, espelha v4 que também não redige). I1 aumenta a superfície de conteúdo bruto → confirmar que o store tem redação, senão abrir item separado. **NÃO redigir no parser.**
- Médio — dumps enormes: NÃO aplicar cutoff no parser (espelha v4); truncagem é decisão do I2/extractor (R9).
- Médio — injected: aplicar `_is_injected_content` sobre o texto consolidado.

## Impacto no I2
Pós-I1, entrada do I2 = AssistantMessage-text-longo + ToolResults (msg+bloco). thinking sai (redacted). Valida a alternativa barata R2.1(b) da RFC ("parsear ToolResults pode bastar antes do LLM") — I1 é o pré-requisito medível.

## Contrato de teste (G3)
RED: ToolResults msg + bloco toolResult hoje retornam [] / coverage extracted=0. GREEN: extrai texto consolidado, role=assistant, coverage+idioma. Edge: data ausente/não-dict, content=[], string em vez de lista, kind inesperado, injected (system-reminder → dropped), dump >10k (extraído, sem cutoff), verbatim, thinking (contado sem text), consolidação (1 msg não N), regressão (text/toolUse inalterados), paridade v4↔legado.

## Próximo
G3 (dev-tests RED) → G4 (dev-python GREEN) → G5 (reviewer). Atualizar RFC #1346 removendo expectativa de recuperar thinking (redacted).
