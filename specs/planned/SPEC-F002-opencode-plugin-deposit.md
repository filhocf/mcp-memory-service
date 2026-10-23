# SPEC-F002 — OpenCode plugin deposit and XDG-aware paths

| Field | Value |
|-------|-------|
| Status | GREEN, G5 |
| Impact | Medium — new files under the OpenCode config directory |
| Depends on | F001 |
| Blocks | F005, F008 |
| Branch | `feat/opencode-installer` |
| Date | 2026-10-23 |

## 1. Context

MMS ships `opencode/memory-plugin.js`, a plugin that injects memory context,
captures decisions, and registers `/memory`. Today installation is a manual
`cp` plus a manually copied configuration file, documented in
`opencode/README.md`. The plugin hardcodes `~/.config/opencode` and
`~/.local/state/opencode`, so an isolated lab (custom `HOME`/`XDG_*`) reads and
writes the developer's real paths.

The installer must deposit the plugin the same way it deposits a steering file,
record what it created, and never overwrite user configuration.

## 2. Objective

Deposit the plugin as a self-contained OpenCode plugin directory, create a
minimal configuration only when none exists, resolve paths through XDG, and
uninstall only files the installer created and still owns.

## 3. Non-goals

- Building the optional TUI sidebar (Babel/Solid build). It stays opt-in and
  documented.
- Registering the plugin through the `plugins` config array (auto-discovery is
  enough and avoids editing the config for a second surface).
- Migrating existing manual installs.

## 4. Requirements

**R1 — Plugin package deposit.**
The installer creates `<root>/plugins/opencode-memory/` with the plugin code and
a `package.json` that exports `"."`.

EARS: WHEN the plugin directory is absent, THE installer SHALL create
`plugins/opencode-memory/{index.js,package.json}`.

**R2 — Valid module.**
The deposited `index.js` must be importable by Node and export both the V2
`setup` entry point and the V1 `server` entry point.

EARS: WHEN `index.js` is imported by Node, THE module SHALL expose `default.setup`
and `default.server`.

**R3 — No plugin config entry.**
The installer SHALL NOT add a `plugins` entry to `opencode.json`.

EARS: WHEN the plugin is deposited, THE installer SHALL leave the `plugins`
field of `opencode.json(c)` untouched.

**R4 — Configuration bootstrap.**
The installer creates `<root>/memory-plugin.json` only when neither
`memory-plugin.json` nor `memory-awareness.json` exists, with the endpoint and
port selected at install time.

EARS: WHEN no plugin configuration exists, THE installer SHALL create
`memory-plugin.json`; WHEN one exists, THE installer SHALL NOT modify it,
except for the explicit `--agent-id` merge defined in SPEC-F005.

**R5 — XDG resolution in the plugin.**
The plugin resolves its config, state, and data directories from
`XDG_CONFIG_HOME`, `XDG_STATE_HOME`, and `XDG_DATA_HOME`, falling back to the
current `~/.config` and `~/.local` layout.

EARS: WHERE `XDG_CONFIG_HOME` is set, THE plugin SHALL read configuration from
`$XDG_CONFIG_HOME/opencode`; WHERE it is unset, THE plugin SHALL read from
`~/.config/opencode`.

**R6 — Ownership and provenance.**
The manifest records every created file with its SHA-256. Uninstall removes a
file only when its current hash matches the recorded hash; a user-modified file
is kept and reported.

EARS: IF a deposited file has been modified since installation, THEN THE
installer SHALL preserve it and SHALL report it as retained on uninstall.

**R7 — Idempotence.**
Re-running install with the same files and hashes plans no copy action.

EARS: WHEN a deposited file exists with the installed hash, THE installer SHALL
report `nothing to do` for that surface.

## 5. Technical contract

### 5.1 Layout

```
<root>/plugins/opencode-memory/
├── index.js          # copy of opencode/memory-plugin.js
└── package.json      # name, version, type=module, exports {".": "./index.js"}
```

`index.js` is copied byte-for-byte from the repository source; the installer
does not transpile it.

### 5.2 `package.json`

```json
{
  "name": "opencode-memory",
  "version": "<mms version>",
  "type": "module",
  "exports": { ".": "./index.js" }
}
```

The TUI export (`"./tui"`) is intentionally absent until the optional build is
deposited.

### 5.3 Configuration bootstrap

```json
{
  "memoryService": {
    "endpoint": "http://127.0.0.1:<port>",
    "timeoutMs": 5000,
    "loadTimeoutMs": 2500,
    "maxMemoriesPerSession": 8
  }
}
```

Only these keys are written; defaults for every other key stay in the plugin.
`127.0.0.1` is used instead of `localhost` so the client does not depend on
IPv6/IPv4 resolution order.

### 5.4 Manifest

```json
{
  "created": [
    {"path": ".../index.js", "sha256": "..."},
    {"path": ".../package.json", "sha256": "..."},
    {"path": ".../memory-plugin.json", "sha256": "..."}
  ],
  "created_dirs": [".../plugins", ".../plugins/opencode-memory"]
}
```

Directories created by the installer are recorded separately and removed only
when empty. Legacy manifests that store plain path strings remain readable. For
the plugin `index.js`, ownership is provable when its bytes match the shipped
source; the other legacy string entries keep the historical behaviour and are
removed on uninstall.

### 5.5 Test seam in the plugin

The plugin exports `_internal.resolvePaths(options)` so the XDG rules are tested
directly instead of by reading prose. The signature is:

```js
resolvePaths({ env = process.env, home = homedir(), directory } = {}) -> {
  configDir, stateDir, dataDir, statusFile, inboxStateFile, configPaths
}
```

- `configDir = (XDG_CONFIG_HOME || home/.config)/opencode`;
- `stateDir = (XDG_STATE_HOME || home/.local/state)/opencode`;
- `dataDir = (XDG_DATA_HOME || home/.local/share)/opencode`;
- `statusFile = OPENCODE_MEMORY_STATUS_FILE || stateDir/.memory-status.json`;
- `configPaths` preserves the existing precedence: explicit `configPath`,
  `OPENCODE_MEMORY_PLUGIN_CONFIG`, `<configDir>/memory-plugin.json`,
  `<configDir>/memory-awareness.json`, then project-local paths.
- The module-level constants and `pluginConfigPaths()` both call this function,
  so the exported seam is the same code path the plugin uses.

## 6. Edge cases

| Case | Behaviour |
|------|-----------|
| Plugin directory exists with an older file | Replace only `index.js` if its hash matches a known-previous install; otherwise abort (`foreign plugin`) |
| `memory-plugin.json` exists | Never overwrite; report `configuration retained` (SPEC-F005 may merge only `memoryService.agentId` when `--agent-id` is explicit) |
| `memory-awareness.json` exists | Treat as configuration present; do not create the new file |
| Uninstall after the user edited `index.js` | Keep the file, report it, remove the rest |
| Status file parent missing | Plugin creates it on first write (`mkdir -p`) |
| Node absent | Install still deposits files; the Node import smoke test is skipped with a reported reason |

## 7. Acceptance criteria (measurable)

| AC | Command | Expected |
|----|---------|----------|
| AC1 | `pytest tests/harness/test_instalar_opencode_plugin.py -q` | all pass |
| AC2 | install into `$SB/opencode`, then `node -e "import('file://.../index.js').then(m=>...)"` | exports `setup` and `server` |
| AC3 | `test -f "$SB/opencode/plugins/opencode-memory/package.json"` | exit 0 |
| AC4 | second install | no file change (hash equal) |
| AC5 | pre-create `memory-plugin.json`, install | file bytes unchanged |
| AC6 | edit `index.js`, uninstall | file retained and reported; `package.json` removed |
| AC7 | `XDG_CONFIG_HOME=$SB/config` plugin config lookup | reads `$SB/config/opencode/memory-plugin.json` |

## 8. Test plan (RED-on-main)

1. Deposit on a clean root creates both files with the expected exports.
2. Idempotent second run.
3. Config bootstrap respects an existing file and an existing legacy file.
4. Hash-guard uninstall keeps a modified file.
5. XDG config/state/data resolution, with and without the variables.
6. Node import smoke test guarded by `shutil.which("node")`.

RED proof on current branch: tests fail with `KeyError: 'opencode'` / absent
deposit actions; the XDG tests fail against the hardcoded `homedir()` paths.

## 9. Risks and rollback

| Risk | Mitigation |
|------|------------|
| Plugin breaks OpenCode startup | Node import smoke test; plugin errors are contained by OpenCode |
| User config overwritten | Create-only policy |
| Stale plugin after upgrade | Version in `package.json` + hash comparison |

Rollback: `--uninstall` removes only unmodified files created by the installer.

## 10. Out of scope

- TUI sidebar build and deployment.
- `/memory` command migration for V1.
- Auto-updating a manually installed plugin.
