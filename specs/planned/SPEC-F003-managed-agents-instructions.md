# SPEC-F003 — Managed block in the global `AGENTS.md`

| Field | Value |
|-------|-------|
| Status | planned |
| Impact | Medium — edits `~/.config/opencode/AGENTS.md`, read on every session |
| Depends on | F001 |
| Blocks | F009 |
| Branch | `feat/opencode-installer` |
| Date | 2026-10-23 |

## 1. Context

OpenCode loads discovered `AGENTS.md` files as operating instructions. The
global file `~/.config/opencode/AGENTS.md` applies to every project. Today MMS
has no presence there; users must add guidance by hand, and the existing
`codebase-memory-mcp` installer already demonstrates the expected shape: a
marker-delimited block that can be replaced and removed without touching the
rest.

The block must stay short: it is paid for on every prompt. It points to the
`mms-uso` skill (F004) for the full doctrine instead of duplicating it.

## 2. Objective

Install a marker-delimited, idempotent MMS section in the global `AGENTS.md`,
replaceable across upgrades, removable on uninstall, and safe around
user-written content.

## 3. Non-goals

- Writing project-local `AGENTS.md` files.
- Rewriting or reordering user content.
- Duplicating the full usage doctrine (that lives in the skill).

## 4. Requirements

**R1 — Marker contract.**
The managed section is delimited by `<!-- mms:start -->` and `<!-- mms:end -->`
on their own lines.

EARS: WHEN the installer writes the MMS section, THE installer SHALL wrap it in
`<!-- mms:start -->` and `<!-- mms:end -->` markers.

**R2 — Create.**
When `AGENTS.md` is absent, the installer creates it containing only the managed
section and records it as created.

EARS: WHEN `$OPENCODE_ROOT/AGENTS.md` does not exist, THE installer SHALL create
it with the managed section.

**R3 — Replace in place.**
When a managed section already exists, the installer replaces only its body and
preserves every byte outside the markers.

EARS: WHEN the markers exist exactly once, THE installer SHALL replace only the
text between them.

**R4 — Append without collision.**
When the file exists without markers, the installer appends one blank line and
the managed section, preserving the existing content and its trailing newline
convention.

EARS: WHEN `AGENTS.md` exists without an MMS marker, THE installer SHALL append
the managed section and SHALL NOT modify existing lines.

**R5 — Ambiguity refusal.**
Duplicate, nested, or unbalanced markers abort the install without writing.

EARS: IF the marker count is not zero or one balanced pair, THEN THE installer
SHALL abort with a non-zero exit code and SHALL NOT modify the file.

**R6 — Idempotence.**
Reinstalling the same body produces no write.

EARS: WHEN the managed body already equals the payload, THE installer SHALL
report `nothing to do` and SHALL NOT write the file.

**R7 — Uninstall.**
Uninstall removes the managed section and one adjacent blank line, keeps the
rest of the file, and deletes the file only when the installer created it and it
is now empty.

EARS: WHEN `--uninstall` runs, THE installer SHALL remove the managed section
and SHALL leave all user content intact.

**R8 — Portability and cost.**
The block contains no harness-specific name, no hardcoded port, and is at most
40 lines.

EARS: THE managed block SHALL contain no occurrence of `Kiro`, `Hermes`, or a
literal port and SHALL NOT exceed 40 lines.

## 5. Technical contract

### 5.1 Location

```
<root>/AGENTS.md
```

`<root>` is the OpenCode config directory resolved in F001.

### 5.2 Payload

`scripts/harness/payload/opencode/AGENTS.md`:

```markdown
<!-- mms:start -->
## Memory service (mcp-memory-service)

You have a persistent memory service registered as the `mms` MCP server.

- Before answering questions about prior state, decisions, or "where we left
  off", call `memory_search` first.
- Keep reads cheap: `memory_search(query=..., limit=3, max_response_chars=2000)`.
- Store decisions, measured numbers, procedures, and pitfalls. Do not store
  what is already in the repository or the transcript.
- Prefer specific tags: `decision`, `procedure`, `measured`, `pitfall`,
  `<project>-system`.
- `agent_id` is stamped by the client; do not invent an identity.

Full doctrine: load the `mms-uso` skill.
<!-- mms:end -->
```

The exact wording may change during G2; the constraints in R8 are binding.

### 5.3 Operations

```python
def has_block(text: str) -> bool
def replace_block(text: str, body: str) -> str
def remove_block(text: str, body: str) -> str
```

Line endings of the existing file are preserved (`\r\n` stays `\r\n`).

## 6. Edge cases

| Case | Behaviour |
|------|-----------|
| File empty | Write only the block |
| File without trailing newline | Add exactly one before the appended block |
| CRLF file | Block uses CRLF |
| Markers inside a fenced code block | Counted; ambiguous >1 pair aborts (safe default) |
| Block is the entire file and we created it | Uninstall deletes the file |
| Block is the entire file but we did not create it | Uninstall leaves an empty file |

## 7. Acceptance criteria (measurable)

| AC | Command | Expected |
|----|---------|----------|
| AC1 | `pytest tests/harness/test_instalar_opencode_agents_md.py -q` | all pass |
| AC2 | install on clean root | `AGENTS.md` exists with one marker pair |
| AC3 | prepend user text + install | user text byte-identical; one block appended |
| AC4 | install twice | second run does not change the hash |
| AC5 | uninstall | block gone; user text intact |
| AC6 | duplicate markers | non-zero exit; hash unchanged |
| AC7 | `grep -E 'Kiro\|Hermes\|:[0-9]{4,5}'` in the block | no match |

## 8. Test plan (RED-on-main)

1. Create, append, replace, remove, idempotence.
2. CRLF and missing-trailing-newline round-trips.
3. Ambiguity refusal (duplicate/unbalanced markers).
4. Payload lint: line count, forbidden tokens.
5. End-to-end through `main(["--harness","opencode", ...])`.

RED proof: current branch has no OpenCode harness, so every test fails at
harness lookup. The payload-lint test is written so that it fails if the Kiro
text is reused verbatim.

## 9. Risks and rollback

| Risk | Mitigation |
|------|------------|
| Instruction bloat on every prompt | 40-line cap; pointer to the skill |
| User edits inside the block | Next install replaces it (documented; block is managed) |
| Marker collision with another tool | Namespaced markers `mms:` |

Rollback: uninstall removes the block only.

## 10. Out of scope

- Local/project `AGENTS.md`.
- `instructions` config arrays.
- Non-OpenCode harnesses.
