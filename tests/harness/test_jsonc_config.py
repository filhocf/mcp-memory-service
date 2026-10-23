"""Tests for specs/planned/SPEC-F001 — the bounded JSONC editor.

The contract under test is byte preservation: the editor may rewrite only the
`mms` member, so comments, key order, indentation, trailing commas and CRLF line
endings must survive every install and uninstall.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "harness"))


def _jsonc():
    return importlib.import_module("jsonc")


ENTRY = {"type": "remote", "url": "http://127.0.0.1:39123/mcp"}

EMPTY_SERVERS = """{
  // servers we already had
  "mcp": {
    "servers": {}
  },
  "theme": "dark"
}
"""

EMPTY_SERVERS_AFTER_UPSERT = """{
  // servers we already had
  "mcp": {
    "servers": {
      "mms": {
        "type": "remote",
        "url": "http://127.0.0.1:39123/mcp"
      }
    }
  },
  "theme": "dark"
}
"""


# --- load --------------------------------------------------------------------


def test_load_accepts_line_comments_block_comments_and_trailing_comma():
    text = """{
  // a line comment
  "a": 1, /* a block comment */
  "b": [1, 2,],
  "c": {"d": true,},
}
"""

    assert _jsonc().load(text) == {"a": 1, "b": [1, 2], "c": {"d": True}}


def test_load_raises_jsonc_error_on_invalid_text():
    jsonc = _jsonc()

    with pytest.raises(jsonc.JsoncError):
        jsonc.load('{"a": }')

    with pytest.raises(jsonc.JsoncError):
        jsonc.load('{"a": 1')


# --- find_span ---------------------------------------------------------------


def test_find_span_returns_the_value_text_for_a_unique_path():
    jsonc = _jsonc()
    text = """{
  "mcp": {
    "servers": {
      "mms": {"type": "remote"}
    }
  }
}
"""

    span = jsonc.find_span(text, ["mcp", "servers", "mms"])

    assert span is not None
    start, end = span
    assert text[start:end] == '{"type": "remote"}'


def test_find_span_ignores_mms_inside_strings_and_comments():
    jsonc = _jsonc()
    text = """{
  // "mms": {"type": "remote"} is only mentioned here
  /* mms: {"type": "remote"} */
  "note": "mms",
  "mcp": {
    "servers": {
      "mms": {"type": "remote"}
    }
  }
}
"""

    span = jsonc.find_span(text, ["mcp", "servers", "mms"])

    assert span is not None
    start, end = span
    assert text[start:end] == '{"type": "remote"}'
    # The span is the real key, not the decoys in the comment and the note value.
    assert text[:start].rstrip().endswith('"mms":')


def test_find_span_returns_none_for_an_absent_path():
    jsonc = _jsonc()

    assert jsonc.find_span('{\n  "mcp": {}\n}', ["mcp", "servers", "mms"]) is None


def test_find_span_raises_on_duplicate_key():
    jsonc = _jsonc()
    text = """{
  "mcp": {
    "servers": {
      "mms": {"type": "remote"},
      "mms": {"type": "remote"}
    }
  }
}
"""

    with pytest.raises(jsonc.JsoncError):
        jsonc.find_span(text, ["mcp", "servers", "mms"])


# --- upsert ------------------------------------------------------------------


def test_upsert_inserts_into_an_existing_container_and_preserves_other_bytes():
    jsonc = _jsonc()

    result = jsonc.upsert(EMPTY_SERVERS, ["mcp", "servers", "mms"], ENTRY)

    assert result == EMPTY_SERVERS_AFTER_UPSERT
    assert jsonc.load(result)["mcp"]["servers"]["mms"] == ENTRY
    assert jsonc.load(result)["theme"] == "dark"


def test_upsert_creates_missing_intermediate_objects():
    jsonc = _jsonc()
    text = '{\n  "theme": "dark"\n}\n'

    result = jsonc.upsert(text, ["mcp", "servers", "mms"], ENTRY)

    data = jsonc.load(result)
    assert data["mcp"]["servers"]["mms"] == ENTRY
    assert data["theme"] == "dark"
    assert '"theme": "dark"' in result


def test_upsert_replaces_an_existing_value_without_touching_its_neighbours():
    jsonc = _jsonc()
    text = """{
  "mcp": {
    "servers": {
      "mms": {
        "type": "remote",
        "url": "http://127.0.0.1:1/mcp"
      },
      "other": {"type": "remote"}
    }
  }
}
"""

    result = jsonc.upsert(text, ["mcp", "servers", "mms"], ENTRY)

    assert result == text.replace(":1/mcp", ":39123/mcp")
    assert jsonc.load(result)["mcp"]["servers"]["mms"] == ENTRY


# --- remove ------------------------------------------------------------------


def test_remove_deletes_the_member_and_keeps_comment_and_other_server():
    jsonc = _jsonc()
    text = """{
  // keep this comment
  "mcp": {
    "servers": {
      "mms": {
        "type": "remote",
        "url": "http://127.0.0.1:39123/mcp"
      },
      "other": {
        "type": "remote",
        "url": "http://127.0.0.1:9000/mcp"
      }
    }
  }
}
"""
    expected = """{
  // keep this comment
  "mcp": {
    "servers": {
      "other": {
        "type": "remote",
        "url": "http://127.0.0.1:9000/mcp"
      }
    }
  }
}
"""

    result = jsonc.remove(text, ["mcp", "servers", "mms"])

    assert result == expected
    data = jsonc.load(result)
    assert "mms" not in data["mcp"]["servers"]
    assert data["mcp"]["servers"]["other"]["url"] == "http://127.0.0.1:9000/mcp"


def test_remove_of_the_only_member_leaves_an_empty_container():
    jsonc = _jsonc()
    text = """{
  "mcp": {
    "servers": {
      "mms": {"type": "remote"}
    }
  }
}
"""
    expected = """{
  "mcp": {
    "servers": {}
  }
}
"""

    result = jsonc.remove(text, ["mcp", "servers", "mms"])

    assert result == expected
    assert jsonc.load(result) == {"mcp": {"servers": {}}}


def test_remove_returns_the_text_unchanged_when_the_path_is_absent():
    jsonc = _jsonc()
    text = '{\n  "mcp": {\n    "servers": {}\n  }\n}\n'

    assert jsonc.remove(text, ["mcp", "servers", "mms"]) == text
    assert jsonc.remove(text, ["absent", "servers", "mms"]) == text


# --- line endings ------------------------------------------------------------


def test_crlf_is_preserved_outside_the_edited_member():
    jsonc = _jsonc()
    text = (
        '{\r\n'
        '  // keep this comment\r\n'
        '  "mcp": {\r\n'
        '    "servers": {\r\n'
        '      "mms": {"type": "remote", "url": "http://127.0.0.1:1/mcp"},\r\n'
        '      "other": {"type": "remote"}\r\n'
        '    }\r\n'
        '  }\r\n'
        '}\r\n'
    )
    expected = text.replace("http://127.0.0.1:1/mcp", "http://127.0.0.1:39123/mcp")

    result = jsonc.upsert(text, ["mcp", "servers", "mms"], ENTRY)

    assert result == expected
    assert "\n" not in result.replace("\r\n", "")
    assert result.count("\r\n") == text.count("\r\n")


# --- G5 regression: compact/inline documents and comments -------------------


def test_remove_handles_a_compact_inline_member():
    jsonc = _jsonc()
    text = '{"mcp":{"servers":{"mms":{},"other":{}}}}'

    result = jsonc.remove(text, ["mcp", "servers", "mms"])

    assert result == '{"mcp":{"servers":{"other":{}}}}'
    assert jsonc.load(result) == {"mcp": {"servers": {"other": {}}}}


def test_remove_handles_the_last_inline_member():
    jsonc = _jsonc()
    text = '{"mcp":{"servers":{"other":{},"mms":{}}}}'

    result = jsonc.remove(text, ["mcp", "servers", "mms"])

    assert result == '{"mcp":{"servers":{"other":{}}}}'
    assert jsonc.load(result) == {"mcp": {"servers": {"other": {}}}}


def test_upsert_into_an_empty_object_keeps_its_comment():
    jsonc = _jsonc()
    text = """{
  "mcp": {
    "servers": {
      // our servers live here
    }
  }
}
"""

    result = jsonc.upsert(text, ["mcp", "servers", "mms"], ENTRY)

    assert "// our servers live here" in result
    assert jsonc.load(result)["mcp"]["servers"]["mms"] == ENTRY


def test_remove_of_the_only_member_keeps_its_comment():
    jsonc = _jsonc()
    text = """{
  "mcp": {
    "servers": {
      // keep this comment
      "mms": {"type": "remote"}
    }
  }
}
"""

    result = jsonc.remove(text, ["mcp", "servers", "mms"])

    assert "// keep this comment" in result
    assert jsonc.load(result) == {"mcp": {"servers": {}}}


def test_remove_of_the_only_member_with_a_trailing_comma_leaves_no_comma():
    jsonc = _jsonc()
    text = """{
  "mcp": {
    "servers": {
      "mms": {},
      // trailing note
    }
  }
}
"""

    result = jsonc.remove(text, ["mcp", "servers", "mms"])

    assert "// trailing note" in result
    assert "\n," not in result
    assert jsonc.load(result) == {"mcp": {"servers": {}}}
