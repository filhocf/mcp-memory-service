# SPEC-F004 — Harness-neutral usage skill

| Field | Value |
|-------|-------|
| Status | planned |
| Impact | Low — payload text only |
| Depends on | F001 |
| Blocks | F007, F009 |
| Branch | `feat/opencode-installer` |
| Date | 2026-10-23 |

## 1. Context

The current payload skill
(`scripts/harness/payload/skills/mms-uso/SKILL.md`) is written for Kiro: it
names Kiro, points at `~/.kiro/settings/mcp.json`, and hardcodes port `3202`. It
is deposited into every harness that declares a skill, so the same text is
wrong for Hermes and would be wrong for OpenCode.

The measured usage doctrine in that file is still valuable (search before state
questions, `limit <= 3`, `max_response_chars <= 2000`, what to store, the
`memory_context` and `memory_list` pitfalls). Only the harness-specific parts
must go.

## 2. Objective

Turn the payload skill into one harness-neutral, English skill that the
installer can deposit into Kiro, Hermes, and OpenCode without edits, and that
OpenCode discovers by the ID `mms-uso`.

## 3. Non-goals

- Per-harness skill variants.
- Translating the skill into Portuguese (project docs are English).
- Changing the measured cost numbers without a new measurement.

## 4. Requirements

**R1 — Neutral identity.**
The skill text contains no harness name and no literal port.

EARS: THE skill SHALL NOT contain `Kiro`, `Hermes`, `OpenCode`, `3202`, or any
other literal port.

**R2 — Discovery contract.**
The file remains at `skills/mms-uso/SKILL.md` with `name: mms-uso` and a
`description` that states when to use it.

EARS: WHEN the skill directory is scanned, THE file SHALL be recognized as skill
ID `mms-uso` from its path and SHALL expose a non-empty description.

**R3 — Trigger specificity.**
The description names state/recall questions, not a generic "memory" label.

EARS: THE description SHALL mention prior decisions, project state, or "where we
left off" as triggers.

**R4 — Measured doctrine preserved.**
The skill keeps the search discipline (`limit <= 3`,
`max_response_chars <= 2000`) and the store/tag guidance, and marks the cost
numbers as measured on a specific date.

EARS: THE skill SHALL instruct `memory_search` with `limit <= 3` and
`max_response_chars <= 2000` and SHALL label cost figures with their measurement
date.

**R5 — Portability of endpoint.**
The skill refers to "the `mms` MCP server registered by the installer" instead
of an absolute URL.

EARS: THE skill SHALL refer to the registered server by name and SHALL NOT embed
an endpoint URL.

**R6 — Authorship rule.**
The skill states that `agent_id` is supplied by the client transport and must
not be invented in tool calls.

EARS: THE skill SHALL state that `agent_id` comes from the harness and SHALL NOT
instruct the model to choose one.

**R7 — Size.**
The skill stays under 90 lines so its load cost remains small.

EARS: THE skill body SHALL NOT exceed 90 lines.

## 5. Technical contract

### 5.1 File

`scripts/harness/payload/skills/mms-uso/SKILL.md`

```markdown
---
name: mms-uso
description: "Use the mcp-memory-service (mms) as long-term memory: when to
  search before answering about prior state or decisions, how to keep reads
  cheap, what to store, and the measured pitfalls."
---

# mms-uso — operating the memory service

## Before acting
...

## How to search
...

## What to store
...

## Pitfalls (measured 2026-10-20)
...

## Authorship
...
```

No frontmatter fields beyond `name` and `description`.

### 5.2 Repository payload variants

The installer maps every harness with a `skill` surface to this single file.
`payload/skills/mms-uso/SKILL.md` is the only skill shipped.

## 6. Edge cases

| Case | Behaviour |
|------|-----------|
| Harness expects a flat `skills/*.md` | Out of scope; all supported harnesses use the directory form |
| Skill ID collision with a user skill | Documented; OpenCode precedence prefers project/local sources |
| Skill loaded on a server without REST | The skill's tools are MCP tools, so it still works |

## 7. Acceptance criteria (measurable)

| AC | Command | Expected |
|----|---------|----------|
| AC1 | `pytest tests/harness/test_payload_skill.py -q` | all pass |
| AC2 | `grep -riE 'kiro\|hermes\|opencode\|:3202' scripts/harness/payload/skills/mms-uso/SKILL.md` | no match |
| AC3 | `wc -l .../SKILL.md` | `<= 90` |
| AC4 | install into a sandbox; path `skills/mms-uso/SKILL.md` exists | exit 0 |
| AC5 | frontmatter parse | `name == "mms-uso"`, description non-empty |

## 8. Test plan (RED-on-main)

1. Payload lint for forbidden tokens.
2. Line-count budget.
3. Frontmatter parsing and description triggers.
4. Presence of the two search limits and the authorship rule.
5. Deposit path per harness (kiro, hermes, opencode).

RED proof: the current payload matches `3202` and `Kiro`, so the lint test fails
on the current branch; the opencode deposit test fails at harness lookup.

## 9. Risks and rollback

| Risk | Mitigation |
|------|------------|
| Kiro users lose the Kiro-specific path | The skill now defers to "the registered server"; Kiro's MCP config still names it |
| Cost figures age | The date is explicit; a new measurement updates the spec and the text together |

Rollback: revert the payload commit; no installed data is affected.

## 10. Out of scope

- The `mms-custo` skill referenced by the old text (not shipped by this
  installer).
- Localized variants.
