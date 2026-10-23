# SPEC-F010 — OpenCode first-class status and agent onboarding

| Field | Value |
|-------|-------|
| Status | docs GREEN — final ✅ claims pending F001–F005 |
| Impact | Medium — upstream-facing documentation and the integration index |
| Depends on | F001–F005 (facts), F009 (install guide) |
| Blocks | — |
| Branch | `feat/opencode-installer` |
| Date | 2026-10-23 |

## 1. Context

Upstream accepted the agent-integration layout in discussion
[#1614](https://github.com/doobidoo/mcp-memory-service/discussions/1614) and
merged `agents/README.md` (PR
[#1617](https://github.com/doobidoo/mcp-memory-service/pull/1617)) plus
`agents/hermes/README.md` (PR
[#1618](https://github.com/doobidoo/mcp-memory-service/pull/1618)). The index
defines **five layers** and an "Adding an agent" section of three lines.

The OpenCode row in that index currently reads:

| Layer | Today |
|-------|-------|
| 1. Connectivity | ✅ MCP |
| 2. Connector | ✅ `opencode/memory-plugin.js` (a plugin contributed earlier) |
| 3. Lifecycle hooks | ✅ load, capture, session summary, harvest |
| 4. Preference override | 🔴 not observed |
| 5. Usage toolkit | 🔴 none shipped |

The existing plugin is a real contribution, but it is not a first-class
integration: there is no installer, no uninstall, no XDG-aware paths, no
authorship stamp, no usage skill, no managed instructions, no lab, and the
registration shape is not the V2 one. A reader of the index cannot see that gap,
and a new contributor has no checklist to close it for the next harness.

This spec records the study, credits what exists, states what this work closes,
and leaves open what it does not close. It is the OpenCode worked example of the
onboarding path, not a generic template detached from code.

## 2. Objective

Document the OpenCode first-class gap in the agent index and in
`opencode/README.md`, and turn `agents/README.md#adding-an-agent` into a
checklist that a contributor can execute — using OpenCode as the worked example.

## 3. Non-goals

- Reconciling Hermes/Kiro docs (out of scope for this delivery).
- Moving `opencode/` to `agents/opencode/` (upstream's staged PR 2).
- Editing the wiki `Memory-Portability-Map` or discussion #520 (manual,
  post-merge steps described in §5.4).
- Implementing layer 4 (preference override) or a model-backed session e2e.
- Shipping `specs/` upstream; specs are internal per DEVELOPMENT-STANDARDS §4.5.

## 4. Requirements

**R1 — Layer status table in the OpenCode README.**
`opencode/README.md` gains a `## First-class status` section with a five-row
table whose columns are `Layer`, `Today`, `This work`, `Remaining`.

EARS: THE `opencode/README.md` SHALL contain a `## First-class status` section
with exactly five layer rows and the columns `Layer`, `Today`, `This work`,
`Remaining`.

**R2 — Credit the existing contribution.**
The section names the existing plugin, its V1/V2 adapter, and its tests as prior
work, and distinguishes them from the installer, authoring, toolkit, and lab
added by this work.

EARS: THE section SHALL name the existing plugin and SHALL state which layers it
already covers.

**R3 — No overclaim.**
Layer 4 is marked 🔴 with the reason; the document does not claim a model-backed
session test, and the sidebar is labelled optional.

EARS: THE section SHALL mark layer 4 as 🔴 and SHALL NOT claim a model-backed
session test.

**R4 — Index row updated.**
The OpenCode row in `agents/README.md` reflects the final state of this work:
layer 2 points to the installer, layer 5 points to the usage skill, and the row
links to `opencode/README.md#first-class-status`.

EARS: WHEN the work is merged, THE OpenCode row SHALL show the installer in layer
2 and the usage skill in layer 5 and SHALL link to the status section.

**R5 — Work-in-progress signal.**
While the code is not merged, the same row carries a `🚧 first-class work in
progress` marker; the final commit of the delivery removes the marker.

EARS: WHILE the delivery is not merged, THE OpenCode row SHALL carry the
`🚧 first-class work in progress` marker.

**R6 — Onboarding checklist.**
`agents/README.md#adding-an-agent` is expanded to a checklist covering: claim the
issue, choose the transport, name the five layers, decide directory vs row,
build the installer (plan/verify/uninstall/idempotence/sandbox), prove it with a
lab, ship the usage toolkit and authorship, and update every documentation
surface.

EARS: THE "Adding an agent" section SHALL contain a numbered checklist with all
eight items above.

**R7 — Documentation surface map.**
The checklist names every surface a new integration must update: `agents/README.md`,
`docs/integrations.md`, root `README.md`, the integration README, a changelog
fragment, and the wiki map when the integration ships.

EARS: THE checklist SHALL list the six documentation surfaces explicitly.

**R8 — Discoverability.**
`CONTRIBUTING.md` links to the checklist from its "Project Documentation"
section.

EARS: THE "Project Documentation" section SHALL link to
`agents/README.md#adding-an-agent`.

**R9 — Upstream/internal boundary.**
No upstream-facing document links to `specs/`; the roadmap in the OpenCode README
points to the public issue/PR, not to internal specs.

EARS: THE upstream-facing documents SHALL NOT contain a `specs/` path.

**R10 — Link integrity.**
Every relative link added by this spec resolves in the repository; no issue or PR
number is invented.

EARS: WHEN the documentation tests run, THE relative links SHALL resolve.

## 5. Technical contract

### 5.1 `opencode/README.md` — new section

Place it immediately after the introduction, before `## OpenCode V1 and V2`:

```markdown
## First-class status

This integration is being completed as a first-class client: the plugin already
exists; the installer, authorship, toolkit, and lab are the work in progress.
The five-layer model is defined in [`agents/README.md`](../agents/README.md).

| Layer | Today | This work | Remaining |
|---|---|---|---|
| 1. Connectivity | ✅ MCP and REST | — | — |
| 2. Connector | ✅ `memory-plugin.js` (V1/V2 adapter + tests) | one-command installer, JSONC-safe V2 registration, surgical uninstall, XDG paths | — |
| 3. Lifecycle hooks | ✅ load, capture, session summary, harvest | verification in the lab | — |
| 4. Preference override | 🔴 not observed | — | OpenCode keeps no native memory store we can override; no evidence yet |
| 5. Usage toolkit | 🔴 none shipped | `mms-uso` skill, managed `AGENTS.md` block, `initialize.instructions` | — |

Not claimed by this work: a model-backed end-to-end session (needs credentials
and is non-deterministic), the optional TUI sidebar, and layer 4.
```

The table is the source of truth for the status; the roadmap below it names the
public issue/PR once it exists.

### 5.2 `agents/README.md` — row

Replace the current OpenCode row with the final state. The installer link points
to `opencode/README.md` until upstream's staged PR 2 moves the directory; the
usage-toolkit column points to the skill path shipped by the installer.

### 5.3 `agents/README.md#adding-an-agent` — checklist

```markdown
## Adding an agent

An integration that installs something gets a directory here, `agents/<name>/`,
with its installer, its tests, and a README naming which of the five layers it
covers. A client that needs only configuration does not get a directory — it gets
a row in this page.

Before calling an integration first-class, work through the list:

1. **Claim the issue.** Open or take an issue and wait for assignment; CI checks
   it for `src/` changes.
2. **Choose the transport.** MCP (stdio or streamable HTTP) when the harness
   speaks the protocol; REST when it does not. State which one the installer
   registers and why.
3. **Name the five layers.** Fill the row honestly; a connected harness can still
   be at layer 1.
4. **Decide directory vs row.** Installing something → `agents/<name>/` with
   README, installer, tests. Configuration only → a row in this page.
5. **Build the installer.** Plan before writing, idempotent, verifies the effect,
   uninstalls only what it created, and supports a sandbox root. A config file it
   edits is never a file it owns.
6. **Prove it in a lab.** Isolated `HOME`/XDG, free port, temporary database, a
   real client check, and a guard that the developer's real config is unchanged.
7. **Ship the toolkit and authorship.** A usage skill or managed instructions,
   plus `X-Agent-ID` on writes. Without them the integration reaches the store but
   is not used well.
8. **Update every surface.** This index, `docs/integrations.md`, the root
   `README.md`, the integration README, `changelog.d/`, and the wiki map when it
   ships.

The OpenCode integration is the worked example:
[`opencode/README.md#first-class-status`](../opencode/README.md#first-class-status).
```

### 5.4 Manual post-merge steps (not files in this repository)

1. **Wiki `Memory-Portability-Map`.** Replace the OpenCode row's "no usage skill
   shipped" with the shipped state and add the link to `agents/README.md` as the
   shipped source of truth. The wiki is edited by a collaborator; record the
   exact diff in the PR description.
2. **Discussion #520.** Add a follow-up comment with the one-command path and the
   V2 shape, without editing the maintainer's original answer.
3. **Upstream issue/PR.** Open the issue before the PR (CONTRIBUTING "Before You
   Start"); link it from the status section. External posting requires approval.

## 6. Edge cases

| Case | Behaviour |
|------|-----------|
| The issue does not exist yet | Status section says "tracked in the pull request that introduces this section"; the number is added when opened |
| Upstream moves `opencode/` before this lands | Update the relative links in the same commit; the checklist is path-agnostic |
| Layer 4 evidence appears later | The row changes to 🟡/✅ in a separate PR with the observation |
| Sidebar build is unavailable | It stays documented as optional; not a first-class claim |
| Wiki cannot be edited | The PR description carries the proposed diff; the repo docs remain correct |

## 7. Acceptance criteria (measurable)

| AC | Command | Expected |
|----|---------|----------|
| AC1 | `pytest tests/docs/test_opencode_status_docs.py -q` | all pass |
| AC2 | `grep -c '^| [1-5]\.' opencode/README.md` inside the section | `5` |
| AC3 | `grep -n 'First-class status' opencode/README.md` | one heading |
| AC4 | OpenCode row in `agents/README.md` | contains installer link, skill link, status anchor |
| AC5 | `grep -rn 'specs/' agents/README.md opencode/README.md docs/integrations.md README.md` | no match |
| AC6 | link check over the touched Markdown | no broken relative link |
| AC7 | `grep -c '^[1-8]\. \*\*' agents/README.md` | `8` checklist items |
| AC8 | `grep -n 'adding-an-agent' CONTRIBUTING.md` | one link |

## 8. Test plan (RED-on-main)

`tests/docs/test_opencode_status_docs.py`:

1. `opencode/README.md` has the heading and exactly five layer rows.
2. The table's layer 4 row contains `🔴`.
3. The section names the existing plugin and the V2 adapter.
4. `agents/README.md` has eight numbered checklist items.
5. The checklist names the six surfaces and the sandbox requirement.
6. The OpenCode row links to the status anchor and does not say "none shipped"
   in layer 5.
7. No upstream-facing doc contains `specs/`.
8. Relative link resolver for the touched files.

RED proof: on the merged branch before this change, the heading, the table, the
eight-item checklist, and the links are absent. `python3 -m pytest
tests/docs/test_opencode_status_docs.py -q` produced **9 failed, 2 passed**; all
nine failures were `AssertionError` (missing section, no five rows, no credited
plugin, no V1/V2 adapter, no index link, empty checklist, missing surfaces, no
`CONTRIBUTING` link, no non-overclaim paragraph). The two passing tests are the
`specs/` boundary and the relative-link resolver, which are regression guards.

## 9. Risks and rollback

| Risk | Mitigation |
|------|------------|
| Overclaiming before the code merges | 🚧 marker + "Not claimed" paragraph |
| The checklist becomes a policy the maintainer did not agree to | It describes the convention accepted in #1614 and cites the worked example; wording is reviewable |
| Wiki drifts from the repo | The repo is the source of truth; the wiki links here |
| Moving `opencode/` breaks links | Relative links are validated by AC6 |

Rollback: docs-only revert; no runtime effect.

## 10. Out of scope

- Hermes/Kiro documentation reconciliation.
- The `agents/opencode/` move (upstream PR 2).
- Layer 4 implementation.
- Wiki and discussion edits (manual, post-merge).
- Internal specs in the upstream PR.
