# Specs — Feature Map

This directory follows the project's Spec-Driven Development standard
(`DEVELOPMENT-STANDARDS.md` §0 and §13).

- `planned/` — specs approved for development or still under refinement.
- `implemented/` — specs delivered to a release.

Naming: `SPEC-F{NNN}-{kebab-name}.md`.

The only pre-existing file, `phase3-nli-contradiction.md`, predates this map and
is kept as-is; it is not renumbered.

## OpenCode first-class client

Goal: make `mcp-memory-service` (MMS) a first-class client of OpenCode, at the
same level as the `codebase-memory-mcp` installer — one command deposits every
surface OpenCode reads, verifies the effect, and uninstalls surgically.

| Spec | Title | Impact | Depends on |
|------|-------|--------|------------|
| [F001](planned/SPEC-F001-opencode-mcp-registration.md) | OpenCode harness + MCP registration (JSONC-safe) | High | — |
| [F002](planned/SPEC-F002-opencode-plugin-deposit.md) | Plugin deposit and XDG-aware paths | Medium | F001 |
| [F003](planned/SPEC-F003-managed-agents-instructions.md) | Managed block in global `AGENTS.md` | Medium | F001 |
| [F004](planned/SPEC-F004-opencode-usage-skill.md) | Harness-neutral usage skill | Low | F001 |
| [F005](planned/SPEC-F005-agent-authorship.md) | `X-Agent-ID` authorship (MCP + plugin REST) | High | F001, F002 |
| [F006](planned/SPEC-F006-mcp-initialize-instructions.md) | `instructions` in MCP `initialize` | Medium | — |
| [F007](planned/SPEC-F007-memory-install-cli.md) | `memory install opencode` CLI entry point | High | F001–F004 |
| [F008](planned/SPEC-F008-isolated-lab-acceptance.md) | Isolated lab and acceptance suite | High | F001, F002 |
| [F009](planned/SPEC-F009-opencode-integration-docs.md) | Integration guide and upstream surfaces | Low | F001–F008, F010 |
| [F010](planned/SPEC-F010-opencode-first-class-status.md) | First-class gap status and agent onboarding | Medium | F001–F005, F009 |

### Execution order

```
F001 ──► F002 ──► F005
  │        │
  ├──────► F003 ──► F004 ──► F007
  │                 │
  └─────────────────┴──────► F008 ──► F009
F006 is independent (server-side) and can ship in parallel with F001.
F010 documents the gap from the merged upstream index; its status table can
land before the code, its final claims follow F001–F005.
```

### Status

| Spec | Status | Evidence |
|------|--------|----------|
| F001 | GREEN, G5 | `jsonc.py` + harness OpenCode; `python3 -m pytest tests/harness/test_jsonc_config.py tests/harness/test_instalar_opencode.py -q` → 41 passed. RED on the pre-change tree: 27 failed. G5: 2 high blockers fixed (CRLF I/O, compact uninstall) plus 6 findings; re-review approved with low-severity reservations. |
| F002 | GREEN, G5 | Plugin package deposit, config bootstrap, hash-guarded manifest and XDG `resolvePaths`. `python3 -m pytest tests/harness/test_instalar_opencode_plugin.py -q` → 23 passed; combined `tests/harness tests/docs tests/hermes` → 121 passed. G5 first round rejected with 3 blockers (relative `--root`, escaping `plugins` symlink, corrupt `created_dirs`); regression tests added and re-review approved with low/medium residual risks. |
| F003–F004 | planned | Specs approved; no implementation yet on `feat/opencode-installer`. |
| F005 | GREEN, G5 | Installer writes `X-Agent-ID` (flag > `MMS_AGENT_ID` > `opencode`) on both surfaces, merges an explicit ID into existing plugin configs, and preserves existing registration headers. Plugin resolves env > file > default and sends the header on every REST call. `python3 -m pytest tests/harness/test_agent_id.py -q` → 23 passed; `node --test opencode/tests/agent-id.test.js` → 13 pass; combined Python suite → 144 passed. G5 rounds fixed existing-config propagation, registration-header loss, and uninstall ownership of edited configs. AC3 reproduced against the live service: header-only `memory_store` was found by an `agent_id`-filtered search and not by another agent. |
| F006–F009 | planned | Specs approved; no implementation yet on `feat/opencode-installer`. |
| F010 | docs GREEN, final claims pending | `opencode/README.md#first-class-status`, the OpenCode index row with 🚧, the 8-item checklist, and `CONTRIBUTING.md` link are in the tree; `tests/docs/test_opencode_status_docs.py` is 11/11 green. Final ✅ claims follow F001–F005. |

The branch was synced with `upstream/main` on 2026-10-23 (merge commit), so
`agents/README.md` and `agents/hermes/README.md` are present locally.
