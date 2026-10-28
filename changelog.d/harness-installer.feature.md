- **OpenCode is a first-class client: one command installs registration, plugin, instructions, and skill.**
  `memory install opencode` writes the V2 `mcp.servers.mms` entry without touching JSONC comments, deposits
  the plugin, the `mms-uso` skill and a managed `AGENTS.md` block, and probes the write path before claiming
  success; reruns re-probe, and `--uninstall` removes only installer-owned state. The multi-harness installer
  moved into the package (`memory install list|opencode`).
