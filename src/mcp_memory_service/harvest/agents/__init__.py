"""Agent profile loader for harvest extraction.

Loads a declarative extraction profile (role maps, discovery globs, noise
filters) from a per-agent YAML file in this directory. Mirrors
``harvest.patterns.load_patterns``: ``AGENTS_DIR`` is the module directory,
PyYAML is used when available with a minimal fallback parser otherwise, and a
missing file logs a warning and falls back to the hardcoded default profile
(byte-identical to the previously inlined ``TranscriptParser`` constants).
"""

import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

AGENTS_DIR = Path(__file__).parent


def _default_profile() -> Dict:
    """Hardcoded default profile (S0.6 fallback).

    MUST stay byte-identical to the former ``TranscriptParser`` constants so a
    missing/unloadable kiro.yaml leaves parsing output unchanged.
    """
    return {
        "agent": "kiro",
        "roles": {
            "relevant_types": ["user", "assistant"],
            "by_kind": {
                "Prompt": "user",
                "Response": "assistant",
                "AssistantMessage": "assistant",
            },
            "by_payload_type": {"user": "user", "assistant": "assistant"},
        },
        "detect": {
            "openclaw_message_types": ["prompt.submitted", "model.completed"],
        },
        "discovery": {
            "globs": [
                "*.jsonl",
                "*.trajectory.jsonl",
                "cli/*.jsonl",
                "*/*/messages.jsonl",
            ],
        },
        "noise": {
            "injected_markers": [
                "<system-reminder>",
                "</system-reminder>",
                "<command-name>",
                "<command-message>",
                "<ide_opened_file>",
            ],
            "system_cutoff_chars": 10000,
        },
    }


def load_agent_profile(agent: str = "kiro") -> Dict:
    """Load the extraction profile for an agent.

    Args:
        agent: Agent name; resolves to ``{AGENTS_DIR}/{agent}.yaml``.

    Returns:
        Profile dict. Falls back to the hardcoded default if the YAML file is
        absent or cannot be parsed (compat with the pre-refactor behavior).
    """
    filepath = AGENTS_DIR / f"{agent}.yaml"
    if not filepath.exists():
        logger.warning(f"Agent profile not found: {filepath} — using hardcoded default")
        return _default_profile()

    profile = _parse_yaml_profile(filepath)
    if not profile:
        logger.warning(f"Agent profile empty/unparseable: {filepath} — using hardcoded default")
        return _default_profile()
    return profile


def _parse_yaml_profile(filepath: Path) -> Dict:
    """Parse an agent profile YAML into a dict."""
    try:
        import yaml
    except ImportError:
        # Fallback: minimal parser for environments without PyYAML.
        return _parse_yaml_simple(filepath)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        logger.warning(f"Failed to load agent profile {filepath}: {e}")
        return {}

    return data or {}


def _parse_yaml_simple(filepath: Path) -> Dict:
    """Minimal YAML parser for the agent profile (no PyYAML dependency).

    Handles exactly the shapes used by the agent profiles: nested mappings keyed
    by 2-space indentation, ``key: value`` scalars (quoted or bare), and
    ``- item`` sequences under a key. Integer-looking scalars are coerced to int.
    This is a last-resort fallback; PyYAML is the normal path. Produces output
    byte-identical to :func:`_default_profile` for the shipped kiro.yaml.
    """
    def _coerce(val: str):
        v = val.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            return v[1:-1]
        if v.lstrip("-").isdigit():
            return int(v)
        return v

    root: Dict = {}
    # Stack of (indent, container_dict). The root is at indent -1.
    stack = [(-1, root)]
    # The mapping key currently awaiting a nested list of "- " items, with the
    # indent of that key and the dict it lives in.
    list_target = None  # (key_indent, key, parent_dict)

    with open(filepath, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            content = line.strip()

            if content.startswith("- "):
                # Sequence item: append to the list owned by the pending key.
                # The key was provisionally created as an empty dict; the first
                # item converts it to a list.
                if list_target is not None:
                    _, key, parent = list_target
                    if not isinstance(parent.get(key), list):
                        parent[key] = []
                    parent[key].append(_coerce(content[2:]))
                continue

            # A non-list line ends any pending list collection at a deeper level.
            # Pop mapping containers whose indent is >= current line indent.
            while len(stack) > 1 and indent <= stack[-1][0]:
                stack.pop()
            if list_target is not None and indent <= list_target[0]:
                list_target = None

            parent = stack[-1][1]
            key, _, rest = content.partition(":")
            key = key.strip()
            rest = rest.strip()
            if rest == "":
                # Nested mapping OR a list header; create a dict and arm the
                # list target in case "- " items follow.
                child: Dict = {}
                parent[key] = child
                stack.append((indent, child))
                list_target = (indent, key, parent)
            else:
                parent[key] = _coerce(rest)
                list_target = None

    # Any key that received list items ends up as a list (set above); keys that
    # received nested scalars stay dicts. Drop empty dicts created for pure-list
    # keys so the shape matches PyYAML (list, not {}).
    def _prune(obj):
        if isinstance(obj, dict):
            return {k: _prune(v) for k, v in obj.items()}
        return obj

    return _prune(root)
