"""Bounded JSONC editor for harness configuration files.

The editor changes one member and leaves every other byte alone: comments, key
order, indentation, trailing commas, and CRLF line endings all survive. It exists
because OpenCode stores its MCP servers in `opencode.jsonc`, a file the user also
edits by hand, and `opencode mcp add` cannot target a sandbox root or undo itself.

The public surface is intentionally small:

    load(text)                 -> dict
    find_span(text, path)      -> (start, end) | None
    upsert(text, path, value)  -> str
    remove(text, path)         -> str

`upsert` merges into an existing object so a URL change does not reflow its
neighbours; `remove` deletes the member, its comma, and the line it occupied.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any

__all__ = ["JsoncError", "load", "find_span", "upsert", "remove"]


class JsoncError(ValueError):
    """The document is not valid JSONC or the edit would be ambiguous."""


@dataclass
class _Member:
    key: str
    key_start: int
    key_end: int
    value: "_Node"
    comma: int | None = None


@dataclass
class _Node:
    start: int
    end: int
    kind: str  # "object" | "array" | "scalar"
    value: Any = None
    members: list[_Member] = field(default_factory=list)
    items: list["_Node"] = field(default_factory=list)


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0

    # -- primitives ---------------------------------------------------------

    def skip(self) -> None:
        text = self.text
        while self.i < len(text):
            char = text[self.i]
            if char in " \t\r\n":
                self.i += 1
            elif text.startswith("//", self.i):
                newline = text.find("\n", self.i)
                self.i = len(text) if newline == -1 else newline
            elif text.startswith("/*", self.i):
                end = text.find("*/", self.i + 2)
                if end == -1:
                    raise JsoncError("unterminated block comment")
                self.i = end + 2
            else:
                return

    def parse_string(self) -> tuple[str, int, int]:
        start = self.i
        if self.text[self.i] != '"':
            raise JsoncError(f"expected string at offset {self.i}")
        self.i += 1
        while self.i < len(self.text):
            char = self.text[self.i]
            if char == "\\":
                self.i += 2
                continue
            if char == '"':
                self.i += 1
                raw = self.text[start : self.i]
                try:
                    return json.loads(raw), start, self.i
                except json.JSONDecodeError as exc:  # pragma: no cover - guarded by scanner
                    raise JsoncError(str(exc)) from exc
            self.i += 1
        raise JsoncError("unterminated string")

    def parse_value(self) -> _Node:
        self.skip()
        if self.i >= len(self.text):
            raise JsoncError("unexpected end of input")
        char = self.text[self.i]
        if char == "{":
            return self.parse_object()
        if char == "[":
            return self.parse_array()
        if char == '"':
            value, start, end = self.parse_string()
            return _Node(start, end, "scalar", value)
        match = re.match(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null", self.text[self.i :])
        if not match:
            raise JsoncError(f"unexpected token at offset {self.i}")
        start = self.i
        self.i += len(match.group(0))
        return _Node(start, self.i, "scalar", json.loads(match.group(0)))

    def parse_object(self) -> _Node:
        start = self.i
        self.i += 1
        members: list[_Member] = []
        while True:
            self.skip()
            if self.i >= len(self.text):
                raise JsoncError("unterminated object")
            if self.text[self.i] == "}":
                self.i += 1
                break
            key, key_start, key_end = self.parse_string()
            self.skip()
            if self.i >= len(self.text) or self.text[self.i] != ":":
                raise JsoncError(f"expected ':' after {key!r}")
            self.i += 1
            value = self.parse_value()
            self.skip()
            comma = None
            if self.i < len(self.text) and self.text[self.i] == ",":
                comma = self.i
                self.i += 1
                self.skip()
            members.append(_Member(key, key_start, key_end, value, comma))
            if comma is None and (self.i >= len(self.text) or self.text[self.i] != "}"):
                raise JsoncError(f"expected ',' or '}}' after {key!r}")
        value = {member.key: member.value.value for member in members}
        return _Node(start, self.i, "object", value, members=members)

    def parse_array(self) -> _Node:
        start = self.i
        self.i += 1
        items: list[_Node] = []
        while True:
            self.skip()
            if self.i >= len(self.text):
                raise JsoncError("unterminated array")
            if self.text[self.i] == "]":
                self.i += 1
                break
            items.append(self.parse_value())
            self.skip()
            if self.i < len(self.text) and self.text[self.i] == ",":
                self.i += 1
            elif self.i < len(self.text) and self.text[self.i] == "]":
                continue
        return _Node(start, self.i, "array", [item.value for item in items], items=items)


def _parse(text: str) -> _Node:
    parser = _Parser(text)
    node = parser.parse_value()
    parser.skip()
    if parser.i != len(text):
        raise JsoncError(f"trailing content at offset {parser.i}")
    return node


def _strip_jsonc(text: str) -> str:
    """Remove comments and trailing commas, leaving string contents untouched."""
    out: list[str] = []
    i = 0
    in_string = False
    while i < len(text):
        char = text[i]
        if in_string:
            out.append(char)
            if char == "\\":
                i += 1
                if i < len(text):
                    out.append(text[i])
            elif char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            i += 1
        elif text.startswith("//", i):
            newline = text.find("\n", i)
            i = len(text) if newline == -1 else newline
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                raise JsoncError("unterminated block comment")
            i = end + 2
        else:
            out.append(char)
            i += 1

    stripped = "".join(out)
    result: list[str] = []
    i = 0
    in_string = False
    while i < len(stripped):
        char = stripped[i]
        if in_string:
            result.append(char)
            if char == "\\":
                i += 1
                if i < len(stripped):
                    result.append(stripped[i])
            elif char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            i += 1
            continue
        if char == ",":
            lookahead = i + 1
            while lookahead < len(stripped) and stripped[lookahead] in " \t\r\n":
                lookahead += 1
            if lookahead < len(stripped) and stripped[lookahead] in "}]":
                i += 1
                continue
        result.append(char)
        i += 1
    return "".join(result)


def load(text: str) -> dict:
    """Parse JSONC into a dict, raising `JsoncError` when it is not valid."""
    try:
        data = json.loads(_strip_jsonc(text))
    except json.JSONDecodeError as exc:
        raise JsoncError(str(exc)) from exc
    if not isinstance(data, dict):
        raise JsoncError("the configuration root must be an object")
    return data


def _member(node: _Node, key: str) -> _Member | None:
    matches = [member for member in node.members if member.key == key]
    if len(matches) > 1:
        raise JsoncError(f"duplicate key {key!r}")
    return matches[0] if matches else None


def _node_at_path(text: str, path: list[str]) -> _Node | None:
    node = _parse(text)
    for segment in path:
        if node.kind != "object":
            return None
        member = _member(node, segment)
        if member is None:
            return None
        node = member.value
    return node


def find_span(text: str, path: list[str]) -> tuple[int, int] | None:
    """Value span of `path`, or None. Raises on a duplicate key on the path."""
    if not path:
        node = _parse(text)
        return (node.start, node.end)
    node = _node_at_path(text, path)
    if node is None:
        return None
    return (node.start, node.end)


# --- rendering ---------------------------------------------------------------


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _indent_at(text: str, position: int) -> int:
    line_start = text.rfind("\n", 0, position) + 1
    spaces = 0
    while line_start + spaces < len(text) and text[line_start + spaces] == " ":
        spaces += 1
    return spaces


def _render(value: Any, base_indent: int, newline: str) -> str:
    """Render a value whose opening brace sits after `"key": `.

    Continuation lines are shifted by `base_indent`, so the closing brace aligns
    with the key's indentation.
    """
    raw = json.dumps(value, indent=2, ensure_ascii=False)
    lines = raw.split("\n")
    if len(lines) == 1:
        return raw
    rendered = lines[0]
    for line in lines[1:]:
        rendered += newline + (" " * base_indent) + line
    return rendered


def _set_path(data: dict, path: list[str], value: Any) -> dict:
    result = copy.deepcopy(data)
    cursor = result
    for segment in path[:-1]:
        cursor = cursor.setdefault(segment, {})
        if not isinstance(cursor, dict):
            raise JsoncError(f"cannot descend through {segment!r}")
    cursor[path[-1]] = copy.deepcopy(value)
    return result


def _gate(before: dict, after: dict, path: list[str], value: Any) -> None:
    if after != _set_path(before, path, value):
        raise JsoncError("the edit would change more than the requested member")


# --- editing -----------------------------------------------------------------


def _has_comment(text: str) -> bool:
    """True when the fragment contains a comment outside a string."""
    i = 0
    in_string = False
    while i < len(text):
        char = text[i]
        if in_string:
            if char == "\\":
                i += 2
                continue
            if char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
        elif text.startswith("//", i) or text.startswith("/*", i):
            return True
        i += 1
    return False


def _insert_member(text: str, node: _Node, key: str, value: Any, newline: str) -> str:
    indent = _indent_at(text, node.start)
    child_indent = indent + 2
    member_text = f'"{key}": {_render(value, child_indent, newline)}'

    if not node.members:
        interior = text[node.start + 1 : node.end - 1]
        if _has_comment(interior):
            close = node.end - 1
            line_start = text.rfind("\n", 0, close) + 1
            if text[line_start:close].strip():
                insertion = newline + (" " * child_indent) + member_text + newline + (" " * indent)
                return text[:close] + insertion + text[close:]
            insertion = (" " * child_indent) + member_text + newline
            return text[:line_start] + insertion + text[line_start:]
        replacement = (
            "{"
            + newline
            + (" " * child_indent)
            + member_text
            + newline
            + (" " * indent)
            + "}"
        )
        return text[: node.start] + replacement + text[node.end :]

    last = node.members[-1]
    if last.comma is None:
        insert_at = last.value.end
        tail = text[last.value.end : node.end]
        extra_close = ""
        if "\n" not in tail and "\r" not in tail:
            extra_close = newline + (" " * indent)
        inserted = "," + newline + (" " * child_indent) + member_text + extra_close
    else:
        insert_at = last.comma + 1
        inserted = newline + (" " * child_indent) + member_text
    return text[:insert_at] + inserted + text[insert_at:]


def _replace_value(text: str, span: tuple[int, int], value: Any) -> str:
    rendered = _render(value, _indent_at(text, span[0]), _newline(text))
    return text[: span[0]] + rendered + text[span[1] :]


def _merge_object(text: str, path: list[str], value: dict) -> str:
    """Merge `value` into the object at `path`, preserving untouched members."""
    node = _node_at_path(text, path)
    if node is None or node.kind != "object":
        raise JsoncError(f"{path} is not an object")

    for member in list(node.members):
        if member.key not in value:
            text = _remove_member_at(text, path, member.key)

    for key, child in value.items():
        node = _node_at_path(text, path)
        assert node is not None
        member = _member(node, key)
        if member is None:
            text = _insert_member(text, node, key, child, _newline(text))
        elif member.value.kind == "object" and isinstance(child, dict):
            text = _merge_object(text, [*path, key], child)
        elif member.value.value != child:
            span = (member.value.start, member.value.end)
            text = _replace_value(text, span, child)
    return text


def _member_is_first_on_line(text: str, member: _Member) -> bool:
    line_start = text.rfind("\n", 0, member.key_start) + 1
    return not text[line_start : member.key_start].strip()


def _remove_member_at(text: str, path: list[str], key: str) -> str:
    node = _node_at_path(text, path)
    if node is None or node.kind != "object":
        return text
    member = _member(node, key)
    if member is None:
        return text

    first_on_line = _member_is_first_on_line(text, member)

    if len(node.members) == 1:
        interior = text[node.start + 1 : node.end - 1]
        if not _has_comment(interior):
            return text[: node.start] + "{}" + text[node.end :]
        start = text.rfind("\n", 0, member.key_start) + 1 if first_on_line else member.key_start
        end = member.value.end
        if member.comma is not None:
            end = member.comma + 1
        if first_on_line:
            if text.startswith("\r\n", end):
                end += 2
            elif text.startswith("\n", end):
                end += 1
        return text[:start] + text[end:]

    index = node.members.index(member)
    if index < len(node.members) - 1:
        start = text.rfind("\n", 0, member.key_start) + 1 if first_on_line else member.key_start
        if member.comma is not None:
            end = member.comma + 1
            if first_on_line:
                if text.startswith("\r\n", end):
                    end += 2
                elif text.startswith("\n", end):
                    end += 1
        else:
            end = member.value.end
            if first_on_line:
                if text.startswith("\r\n", end):
                    end += 2
                elif text.startswith("\n", end):
                    end += 1
        return text[:start] + text[end:]

    previous = node.members[index - 1]
    start = previous.comma if previous.comma is not None else previous.value.end
    end = member.value.end
    return text[:start] + text[end:]


def upsert(text: str, path: list[str], value: Any) -> str:
    """Set `path` to `value`, creating missing objects and preserving the rest."""
    if not path:
        raise JsoncError("the path cannot be empty")
    before = load(text)
    target = find_span(text, path)

    if target is not None:
        node = _node_at_path(text, path)
        if node is not None and node.kind == "object" and isinstance(value, dict):
            result = _merge_object(text, path, value)
        else:
            result = _replace_value(text, target, value)
    else:
        existing: _Node | None = None
        existing_path: list[str] = []
        for length in range(len(path) - 1, -1, -1):
            prefix = path[:length]
            node = _node_at_path(text, prefix) if prefix else _parse(text)
            if node is not None and node.kind == "object":
                existing = node
                existing_path = prefix
                break
        if existing is None:
            raise JsoncError("no object container found")
        remaining = path[len(existing_path) :]
        nested: Any = value
        for segment in reversed(remaining[1:]):
            nested = {segment: nested}
        result = _insert_member(text, existing, remaining[0], nested, _newline(text))

    after = load(result)
    _gate(before, after, path, value)
    return result


def remove(text: str, path: list[str]) -> str:
    """Delete `path` when present; return `text` unchanged when it is absent."""
    if not path:
        raise JsoncError("the path cannot be empty")
    before = load(text)
    if find_span(text, path) is None:
        return text
    result = _remove_member_at(text, path[:-1], path[-1])
    after = load(result)
    expected = copy.deepcopy(before)
    cursor = expected
    for segment in path[:-1]:
        cursor = cursor[segment]
    del cursor[path[-1]]
    if after != expected:
        raise JsoncError("the edit would change more than the requested member")
    return result
