# SPEC-F009 — OpenCode integration guide and upstream surfaces

| Field | Value |
|-------|-------|
| Status | planned |
| Impact | Low — docs and changelog |
| Depends on | F001–F008; F010 (status section and matrix row) |
| Blocks | — |
| Branch | `feat/opencode-installer` |
| Date | 2026-10-23 |

## 1. Context

After the merge of `upstream/main`, the repository has the agent layout accepted
in discussion [#1614](https://github.com/doobidoo/mcp-memory-service/discussions/1614):
`agents/README.md` is the five-layer index (PR
[#1617](https://github.com/doobidoo/mcp-memory-service/pull/1617)) and
`agents/hermes/README.md` documents a shipped integration (PR
[#1618](https://github.com/doobidoo/mcp-memory-service/pull/1618)).
`docs/agents/` is now reserved for documentation-only frameworks; a harness that
installs something belongs under `agents/<name>/`.

OpenCode still lives in `opencode/`, which upstream's staged plan moves to
`agents/opencode/` in a later mechanical PR. Until then, `opencode/README.md` is
the canonical guide: it must stop describing a manual `cp` and start describing
the one-command install shipped by F001–F008.

After F001–F008 the product has a one-command install, an uninstall, authorship,
and a lab. Users need a single page that states prerequisites, the exact
commands, what is deposited where, how to verify, and how to remove it. The
first-class gap study and the status table live in F010; this spec covers the
practical guide and the upstream-facing surfaces.

## 2. Objective

Document OpenCode at the same level as the other first-class integrations, on
the surfaces upstream actually reads, and make every documented command match
the shipped CLI.

## 3. Non-goals

- Adding `docs/agents/opencode.md`: `docs/agents/` is for docs-only frameworks,
  and OpenCode installs files.
- Moving `opencode/` to `agents/opencode/` (upstream staged PR 2).
- Marketing copy or screenshots.
- Rewriting unrelated integration guides.
- Translating docs to Portuguese (project docs are English).
- Internal specs in the upstream PR (DEVELOPMENT-STANDARDS §4.5).

## 4. Requirements

**R1 — Canonical guide.**
`opencode/README.md` contains the integration guide: prerequisites, install,
what is deposited, verification, authentication and identity, configuration,
uninstall, and troubleshooting.

EARS: THE `opencode/README.md` SHALL contain sections for prerequisites, install,
what is deposited, verification, authentication and agent identity,
configuration, uninstall, and troubleshooting.

**R2 — Command accuracy.**
Every command in the guide exists and its flags match `--help`.

EARS: WHEN a documented command is executed in a sandbox, THE command SHALL
succeed or SHALL fail only because of a documented prerequisite.

**R3 — Deposited surfaces table.**
The guide lists each surface and its path: MCP registration, plugin, plugin
config, `AGENTS.md` block, and skill.

EARS: THE guide SHALL include a table mapping every OpenCode surface to its
resolved path.

**R4 — Index and integration list.**
`agents/README.md` carries the OpenCode row (owned by F010) and
`docs/integrations.md` names the OpenCode installer next to the Hermes one.

EARS: THE `docs/integrations.md` OpenCode entry SHALL name the installer as the
primary method.

**R5 — Root README.**
The root `README.md` OpenCode section shows the one-command install and links to
the guide, instead of the manual configuration snippet only.

EARS: THE root README OpenCode section SHALL show the installer command and
SHALL link to `opencode/README.md`.

**R6 — Plugin README alignment.**
`opencode/README.md` points to the installer as the primary path and labels the
manual copy as the advanced path; V1/V2 statements match the shipped code.

EARS: THE OpenCode plugin README SHALL describe the installer as the primary
installation method.

**R7 — Changelog fragment.**
A `changelog.d/<issue>.feature.md` fragment describes the user-visible effect in
one paragraph, per §9.0.2.

EARS: THE changelog fragment SHALL describe the OpenCode first-class
installation in at most five lines.

**R8 — Uninstall documented.**
The guide documents `--uninstall`, what it removes, and what it deliberately
keeps (modified files, config).

EARS: THE guide SHALL state that uninstall removes only registrations and
unmodified installer-created files.

**R9 — Lab evidence.**
The guide's verification section names the commands that prove the install,
including the lab test.

EARS: THE verification section SHALL include `opencode mcp list` and the lab
test command.

**R10 — Upstream/internal boundary.**
No upstream-facing document links to `specs/`.

EARS: THE upstream-facing documents SHALL NOT contain a `specs/` path.

## 5. Technical contract

### 5.1 Files

```
opencode/README.md                      # canonical guide, installer-first
agents/README.md                        # OpenCode row (F010)
docs/integrations.md                    # installer line
README.md                               # OpenCode section
changelog.d/<issue>.feature.md          # new
```

`docs/agents/README.md` is not touched: it lists documentation-only frameworks.
When upstream moves the directory, these files become
`agents/opencode/README.md` and the links follow in the same commit.

### 5.2 Guide skeleton

```markdown
# OpenCode Memory Awareness Plugin

## First-class status            # F010
## Prerequisites
## Install
## What gets installed
## Verify
## Authentication and agent identity
## Configuration
## Uninstall
## Troubleshooting
## OpenCode V1 and V2
```

Each command is a fenced `bash` block with no placeholder that cannot be
resolved (absolute repo paths are written as `$MMS_REPO` with an export line).

### 5.3 Changelog shape

```markdown
- **OpenCode is a first-class client: one command installs registration, plugin,
  instructions, and skill.** `memory install opencode` writes the V2
  `mcp.servers.mms` entry without touching JSONC comments, deposits the plugin,
  and verifies the effect; `--uninstall` removes only what it created.
```

## 6. Edge cases

| Case | Behaviour |
|------|-----------|
| User has a legacy `mcp.mms` entry | Guide explains it is honoured and shows uninstall |
| User has both `.json` and `.jsonc` | Troubleshooting entry explains the abort and the fix |
| PyPI install without the repo | Guide uses the CLI, not the script |
| No Node | Plugin still installs; sidebar build is out of scope |
| Upstream moves `opencode/` first | The PR rebases and updates the relative links |

## 7. Acceptance criteria (measurable)

| AC | Command | Expected |
|----|---------|----------|
| AC1 | `pytest tests/docs/test_agent_docs.py -q` | all pass |
| AC2 | required headings in `opencode/README.md` | all present |
| AC3 | link check over the touched Markdown | no broken relative link |
| AC4 | command extraction: every `memory install` example returns `--help` exit 0 | all pass |
| AC5 | `grep -n 'install' docs/integrations.md` in the OpenCode area | installer named |
| AC6 | `grep -n 'memory install opencode' README.md` | at least one match |
| AC7 | `grep -rn 'specs/' agents/README.md opencode/README.md docs/integrations.md README.md` | no match |
| AC8 | changelog fragment | `<= 5` lines, starts with `- **` |

## 8. Test plan (RED-on-main)

1. Required headings in `opencode/README.md`.
2. Relative markdown link resolver (local files only).
3. Command/flags consistency: parse fenced `bash` blocks, compare to
   `memory install --help` output.
4. Changelog length and format.
5. `docs/integrations.md` and root `README.md` mention the installer.
6. No `specs/` path in upstream-facing files.

RED proof: on the merged branch before this change, the guide still describes the
manual copy, `docs/integrations.md` has no installer line for OpenCode, the root
README has no installer command, and the changelog fragment is absent, so tests
1, 4, 5, and 6 fail.

## 9. Risks and rollback

| Risk | Mitigation |
|------|------------|
| Docs drift from flags | AC4 parses and executes `--help` |
| Overlong guide | Skeleton fixed in §5.2; unrelated detail links out |
| Upstream moves the directory | Relative links validated; rebase updates them |
| Changelog becomes a diary | §9.0.2 limit |

Rollback: docs-only revert.

## 10. Out of scope

- Website/site docs.
- Videos and screenshots.
- Other harness guides.
- Wiki and discussion edits (manual, post-merge; see F010 §5.4).
