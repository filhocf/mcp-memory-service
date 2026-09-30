- **Harvest extracts ToolResults from the legacy Kiro CLI format (#1346).**
  The legacy parser dropped rich tool output in two places: the `ToolResults`
  message kind (dropped at the `if not role` guard) and the `toolResult` block
  inside an `AssistantMessage` (dropped in the generic `else`). Both now extract
  the nested text (`content[] → kind json/text → data.content[].text`) via a
  shared `_extract_toolresult_text` helper, mirroring the v4 `tool_result`
  semantics: role `assistant`, `_is_injected_content` filter applied per block,
  no 10k cutoff (a long tool result is the analytical data #1346 wants), content
  kept verbatim. Injected markers are filtered per block so one injected block
  does not drop the legitimate ones alongside it. `thinking` blocks stay counted
  but not extracted — the Kiro extended-thinking is redacted on disk (empty text
  + encrypted `redactedContent`), so there is nothing to harvest. Real session:
  ToolResults extraction went 0 → 36 on one CLI transcript. Groundwork for the
  design-extractor (I2, R2.1(b) — parsing tool results may close part of the gap
  before the LLM step).
