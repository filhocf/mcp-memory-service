Fixed session triage never activating: the `_apply_triage` gate (opt-in via
`MCP_HARVEST_TRIAGE`) was wired into `SessionHarvester` but no real entry point
passed `triage_enabled`/`triage_threshold`, so the feature was dead in
production. The harvest entry points (consolidate action, scheduler, memory_harvest
tool, HTTP endpoint) now build their config via `harvest_config_from_env`, which
reads the env vars while preserving all call-site overrides. Default stays OFF.
