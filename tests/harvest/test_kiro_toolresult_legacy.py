"""RED tests for Kiro CLI legacy toolResult extraction.

These tests FAIL with the current implementation, proving the gap where ToolResults
and toolResult blocks are dropped instead of extracted. They validate the behavior
that I1 will implement: extracting text from ToolResults messages and toolResult
blocks within AssistantMessage content.

Current main behavior (causes RED):
- ToolResults messages are dropped by 'if not role' guard (kind not in KIRO_KIND_MAP)
- toolResult blocks are dropped by else generic without text extraction
- Coverage shows extracted=0 for both cases

Target behavior (GREEN after I1):
- ToolResults message → extract consolidated text from toolResult blocks → 1 ParsedMessage role="assistant"
- toolResult block in AssistantMessage → extract text alongside existing text blocks
- Coverage shows extracted≥1 and language tally for extracted content
- Mirrors v4 _parse_kiro_v4_line tool_result semantics: role assistant, _is_injected_content filter, no 10k cutoff
"""

import json
import pytest

from mcp_memory_service.harvest.parser import TranscriptParser


def _write(tmp_path, lines):
    """Helper to write JSONL test fixture matching existing pattern."""
    p = tmp_path / "session.jsonl"
    p.write_text("".join(json.dumps(o) + "\n" for o in lines), encoding="utf-8")
    return p


def test_message_toolresults_extracted(tmp_path):
    """RED: ToolResults message should extract consolidated text from toolResult blocks → 1 ParsedMessage role='assistant'.
    
    Current: returns [] because ToolResults kind not in KIRO_KIND_MAP, hits 'if not role' guard.
    Target: navigate data.content[]->toolResult->data.content[]->text, extract 'resultado analitico...'.
    """
    parser = TranscriptParser()
    lines = [
        {
            "version": "v1",
            "kind": "ToolResults", 
            "data": {
                "message_id": "msg1",
                "content": [
                    {
                        "kind": "toolResult",
                        "data": {
                            "toolUseId": "tu1",
                            "content": [
                                {
                                    "kind": "json",
                                    "data": {
                                        "content": [
                                            {"type": "text", "text": "resultado analitico com mais de trinta caracteres aqui"}
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    ]
    fp = _write(tmp_path, lines)

    msgs = parser.parse_file(fp)
    
    # RED: current implementation drops ToolResults → len(msgs) == 0
    # GREEN: should extract 1 message with role='assistant' containing the text
    assert len(msgs) == 1, f"Expected 1 extracted message, got {len(msgs)}"
    assert msgs[0].role == "assistant"
    assert "resultado analitico" in msgs[0].text


def test_block_toolresult_in_assistant_extracted(tmp_path):
    """RED: AssistantMessage with text + toolResult block should extract BOTH → 2 ParsedMessage.
    
    Current: only extracts the text block, drops toolResult block without text extraction.
    Target: extract text block AND navigate toolResult->data.content[]->text for separate ParsedMessage.
    """
    parser = TranscriptParser()
    lines = [
        {
            "version": "v1",
            "kind": "AssistantMessage",
            "data": {
                "content": [
                    {
                        "kind": "text",
                        "data": "analise em texto normal do assistant com mais de trinta caracteres"
                    },
                    {
                        "kind": "toolResult",
                        "data": {
                            "toolUseId": "tu2",
                            "content": [
                                {
                                    "kind": "text",
                                    "data": {
                                        "content": [
                                            {"type": "text", "text": "saida de ferramenta rica com bastante conteudo textual aqui"}
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    ]
    fp = _write(tmp_path, lines)

    msgs = parser.parse_file(fp)
    
    # RED: current gets 1 (text block only), drops toolResult
    # GREEN: should get 2 (text + toolResult both extracted)
    assert len(msgs) == 2, f"Expected 2 extracted messages (text + toolResult), got {len(msgs)}"
    text_msgs = [m for m in msgs if "analise em texto normal" in m.text]
    tool_msgs = [m for m in msgs if "saida de ferramenta rica" in m.text]
    assert len(text_msgs) == 1, "Should extract the text block"
    assert len(tool_msgs) == 1, "Should extract the toolResult block"
    assert all(m.role == "assistant" for m in msgs), "All extracted should be role='assistant'"


def test_toolresult_coverage_and_language(tmp_path):
    """RED: coverage_report() should show ToolResults/toolResult with extracted≥1 and pt language tally.
    
    Current: extracted=0 because both message and block types are dropped.
    Target: extracted≥1 and languages.extracted.pt≥1 (content is pt-BR).
    """
    parser = TranscriptParser()
    lines = [
        {
            "version": "v1", 
            "kind": "ToolResults",
            "data": {
                "content": [
                    {
                        "kind": "toolResult",
                        "data": {
                            "toolUseId": "tu1", 
                            "content": [
                                {
                                    "kind": "text",
                                    "data": {
                                        "content": [
                                            {"type": "text", "text": "análise detalhada com decisão sobre configuração que não deve ser cortada"}
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    ]
    fp = _write(tmp_path, lines)
    
    msgs = parser.parse_file(fp)
    report = parser.coverage_report()
    
    # RED: current shows ToolResults extracted=0, no language data
    # GREEN: should show extracted≥1 for ToolResults key and pt language tally
    assert "ToolResults" in report or "toolResult" in report, "Coverage should track ToolResults or toolResult"
    
    # Check the appropriate key exists and has extracted content
    key = "ToolResults" if "ToolResults" in report else "toolResult"
    assert report[key]["extracted"] >= 1, f"Expected extracted≥1 for {key}, got {report[key]['extracted']}"
    
    # Language detection for extracted pt-BR content  
    lang_data = report[key].get("languages", {}).get("extracted", {})
    assert lang_data.get("pt", 0) >= 1, f"Expected pt language count≥1, got {lang_data}"


def test_toolresult_injected_content_dropped(tmp_path):
    """ToolResult with <system-reminder> should NOT be extracted (dropped by _is_injected_content filter).
    
    This should PASS today if the filter is applied correctly, or FAIL if not implemented yet.
    Validates the injected content filtering mirrors v4 behavior.
    """
    parser = TranscriptParser()
    lines = [
        {
            "version": "v1",
            "kind": "ToolResults", 
            "data": {
                "content": [
                    {
                        "kind": "toolResult",
                        "data": {
                            "toolUseId": "tu1",
                            "content": [
                                {
                                    "kind": "text",
                                    "data": {
                                        "content": [
                                            {"type": "text", "text": "<system-reminder>This is injected harness content</system-reminder> with some analysis"}
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    ]
    fp = _write(tmp_path, lines)

    msgs = parser.parse_file(fp)
    report = parser.coverage_report()
    
    # Should NOT extract injected content
    extracted_texts = [m.text for m in msgs]
    assert not any("<system-reminder>" in text for text in extracted_texts), "Injected content should be filtered out"
    
    # Coverage should show dropped, not extracted
    if "ToolResults" in report:
        assert report["ToolResults"]["dropped"] >= 1, "Injected content should be counted as dropped"


def test_toolresult_long_dump_not_cut(tmp_path):
    """RED: ToolResult with >10k chars (no injected markers) should be EXTRACTED without cutoff.
    
    Current: dropped at message/block level, never reaches length check.
    Target: mirrors v4 behavior - no 10k cutoff for tool results (rich analytical data).
    """
    parser = TranscriptParser()
    long_content = "análise detalhada " * 1000  # >10k chars, pt-BR content, no markers
    assert len(long_content) > 10000, "Test content must exceed 10k chars"
    
    lines = [
        {
            "version": "v1",
            "kind": "ToolResults",
            "data": {
                "content": [
                    {
                        "kind": "toolResult", 
                        "data": {
                            "toolUseId": "tu1",
                            "content": [
                                {
                                    "kind": "text",
                                    "data": {
                                        "content": [
                                            {"type": "text", "text": long_content}
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    ]
    fp = _write(tmp_path, lines)

    msgs = parser.parse_file(fp)
    
    # RED: current drops at structure level, never gets to extract long content
    # GREEN: should extract the full long content without 10k cutoff
    assert len(msgs) == 1, f"Expected 1 extracted long tool result, got {len(msgs)}"
    assert len(msgs[0].text) > 10000, f"Expected long text extracted, got {len(msgs[0].text)} chars"
    assert "análise detalhada" in msgs[0].text


def test_thinking_counted_not_extracted(tmp_path):
    """Thinking block with empty text should be counted in coverage (seen+dropped) but NOT extracted.
    
    May PASS today if thinking falls through to else block. Validates coverage tracking
    for non-extractable blocks that should still be visible in the instrument.
    """
    parser = TranscriptParser()
    lines = [
        {
            "version": "v1",
            "kind": "AssistantMessage",
            "data": {
                "content": [
                    {
                        "kind": "thinking",
                        "data": {
                            "text": "",
                            "signature": None,
                            "redactedContent": [46, 75, 84]
                        }
                    }
                ]
            }
        }
    ]
    fp = _write(tmp_path, lines)

    msgs = parser.parse_file(fp)
    report = parser.coverage_report()
    
    # Should NOT extract thinking (empty text)
    assert len(msgs) == 0, "Thinking blocks should not be extracted"
    
    # Coverage should show thinking as seen+dropped, no language tally (no text)
    assert "thinking" in report, "Coverage should track thinking blocks"
    assert report["thinking"]["seen"] >= 1, "Thinking should be seen"
    assert report["thinking"]["extracted"] == 0, "Thinking should not be extracted"
    
    # No language data for thinking (no text content)
    lang_data = report["thinking"].get("languages", {})
    assert not lang_data or not lang_data.get("extracted"), "Thinking should have no extracted language data"


def test_toolresult_malformed_defensive(tmp_path):
    """Malformed toolResult structures should not crash, return [] or count as dropped.
    
    Tests defensive programming: missing data, non-list content, empty content.
    """
    parser = TranscriptParser()
    lines = [
        # Missing data
        {
            "version": "v1",
            "kind": "ToolResults"
        },
        # data.content not a list
        {
            "version": "v1", 
            "kind": "ToolResults",
            "data": {
                "content": "not a list"
            }
        },
        # Empty content list
        {
            "version": "v1",
            "kind": "ToolResults", 
            "data": {
                "content": []
            }
        },
        # toolResult without proper structure
        {
            "version": "v1",
            "kind": "ToolResults",
            "data": {
                "content": [
                    {
                        "kind": "toolResult",
                        "data": {}  # Missing content
                    }
                ]
            }
        }
    ]
    fp = _write(tmp_path, lines)

    # Should not crash
    msgs = parser.parse_file(fp)
    report = parser.coverage_report()
    
    # Should handle gracefully - no extraction from malformed data
    assert isinstance(msgs, list), "Should return list even with malformed data"
    
    # Coverage should track the attempts
    if "ToolResults" in report:
        assert report["ToolResults"]["dropped"] >= 1, "Malformed entries should be dropped"


def test_regression_text_block_still_extracted(tmp_path):
    """Regression: AssistantMessage with only text block should still extract as before.
    
    Ensures toolResult extraction doesn't break existing text extraction behavior.
    This should PASS (regression prevention).
    """
    parser = TranscriptParser()
    lines = [
        {
            "version": "v1",
            "kind": "AssistantMessage",
            "data": {
                "content": [
                    {
                        "kind": "text",
                        "data": "regular assistant message text that should be extracted normally"
                    }
                ]
            }
        }
    ]
    fp = _write(tmp_path, lines)

    msgs = parser.parse_file(fp)
    
    # This should continue to work (regression test)
    assert len(msgs) == 1, "Regular text extraction should still work"
    assert msgs[0].role == "assistant"
    assert "regular assistant message" in msgs[0].text


def test_toolresult_nested_json_extraction(tmp_path):
    """RED: ToolResult with nested JSON structure should extract the inner text content.
    
    Current: message-level drop means nested navigation never happens.
    Target: deep navigation through kind=json -> data.content[] -> type=text -> text.
    """
    parser = TranscriptParser()
    lines = [
        {
            "version": "v1",
            "kind": "AssistantMessage",
            "data": {
                "content": [
                    {
                        "kind": "toolResult",
                        "data": {
                            "toolUseId": "tu1",
                            "content": [
                                {
                                    "kind": "json",
                                    "data": {
                                        "content": [
                                            {"type": "text", "text": "conteúdo JSON aninhado extraído com sucesso"},
                                            {"type": "text", "text": "segunda parte do resultado JSON"}
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    ]
    fp = _write(tmp_path, lines)

    msgs = parser.parse_file(fp)
    
    # RED: current drops toolResult block entirely
    # GREEN: should extract and consolidate both text parts
    assert len(msgs) == 1, f"Expected 1 consolidated toolResult message, got {len(msgs)}"
    assert "conteúdo JSON aninhado" in msgs[0].text
    assert "segunda parte do resultado" in msgs[0].text


def test_toolresult_mixed_content_types(tmp_path):
    """RED: ToolResult with mixed json/text content should extract from both.
    
    Current: block-level drop.
    Target: navigate both kind=json and kind=text within same toolResult.
    """
    parser = TranscriptParser()
    lines = [
        {
            "version": "v1",
            "kind": "ToolResults",
            "data": {
                "content": [
                    {
                        "kind": "toolResult",
                        "data": {
                            "toolUseId": "tu1",
                            "content": [
                                {
                                    "kind": "text",
                                    "data": {
                                        "content": [
                                            {"type": "text", "text": "primeira parte via kind text"}
                                        ]
                                    }
                                },
                                {
                                    "kind": "json", 
                                    "data": {
                                        "content": [
                                            {"type": "text", "text": "segunda parte via kind json"}
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    ]
    fp = _write(tmp_path, lines)

    msgs = parser.parse_file(fp)
    
    # RED: current drops ToolResults entirely at message level
    # GREEN: should consolidate text from both json and text kinds
    assert len(msgs) == 1, f"Expected 1 consolidated message, got {len(msgs)}"
    assert "primeira parte via kind text" in msgs[0].text
    assert "segunda parte via kind json" in msgs[0].text