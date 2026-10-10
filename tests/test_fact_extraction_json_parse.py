"""Tests for the tolerant LLM-JSON parser used by batch fact extraction.

Regression: groq gpt-oss wraps JSON arrays in ```json fences or adds a short
preamble, which broke a bare json.loads() and aborted the whole extraction run
('Failed to parse LLM response as JSON: Expecting value: line 1 column 1').
"""
from mcp_memory_service.extraction.facts import _parse_llm_json_array


def test_plain_json_array():
    assert _parse_llm_json_array('[{"s":"a","p":"b","o":"c"}]') == [{"s": "a", "p": "b", "o": "c"}]


def test_fenced_json_array():
    resp = 'Here are the facts:\n```json\n[{"s":"x","p":"y","o":"z"}]\n```\n'
    assert _parse_llm_json_array(resp) == [{"s": "x", "p": "y", "o": "z"}]


def test_fenced_without_lang():
    resp = '```\n[{"s":"1","p":"2","o":"3"}]\n```'
    assert _parse_llm_json_array(resp) == [{"s": "1", "p": "2", "o": "3"}]


def test_preamble_then_array():
    resp = 'Sure! The extracted triples are: [{"s":"m","p":"n","o":"o"}] done.'
    assert _parse_llm_json_array(resp) == [{"s": "m", "p": "n", "o": "o"}]


def test_empty_array():
    assert _parse_llm_json_array("[]") == []


def test_unparseable_returns_none():
    assert _parse_llm_json_array("I could not find any facts.") is None


def test_empty_string_returns_none():
    assert _parse_llm_json_array("") is None


def test_object_not_list_returns_none():
    # A bare object (not a list) is not a valid batch result.
    assert _parse_llm_json_array('{"s":"a"}') is None
