# Spec: #11 Schema Versioning + Migration Registry

**Date:** 2026-06-01
**Branch:** `feat/schema-versioning` (from `main`)
**Repo:** `~/git/mcp-memory-service`
**Refs:** Codeberg issue #11, doobidoo comment (01/jun/2026)

---

## Design

Replace the current "run idempotent SQL, swallow duplicate-column error" approach with a proper migration registry.

### Components

1. **`schema_version` in metadata table** — single row tracking current version
2. **Migration registry table** — records which migrations have been applied
3. **Versioned MigrationRunner** — only runs pending migrations, wraps each in transaction
4. **CLI commands** — `--check-db` (diagnosis) and `--migrate` (apply)

---

## 1. Schema Version Tracking

The `metadata` table already exists (currently empty). Add a row:

```sql
-- In initialize(), after ensuring metadata table exists:
INSERT OR IGNORE INTO metadata (key, value) VALUES ('schema_version', '7');
```

Missing version → assume 7 (pre-migration era). New migrations start from 008.

---

## 2. Migration Registry Table

```sql
CREATE TABLE IF NOT EXISTS migration_registry (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    filename TEXT NOT NULL,
    applied_at TEXT NOT NULL,  -- ISO 8601
    checksum TEXT              -- SHA256 of SQL content (detect tampering)
);
```

---

## 3. Versioned MigrationRunner (rewrite)

Replace `src/mcp_memory_service/storage/migration_runner.py`:

```python
class MigrationRunner:
    """Schema migration runner with version tracking and registry."""

    def __init__(self, migrations_dir: Path):
        self.migrations_dir = migrations_dir

    def _discover_migrations(self) -> list[tuple[int, str, Path]]:
        """Discover migration files sorted by version number.
        Returns: [(version, name, path), ...]
        Files must be named: NNN_description.sql (e.g., 008_add_graph.sql)
        """

    def _get_applied_versions(self, conn) -> set[int]:
        """Read migration_registry to find already-applied versions."""

    def _get_current_version(self, conn) -> int:
        """Read schema_version from metadata. Default 7 if missing."""

    def run_pending(self, conn, dry_run=False) -> dict:
        """Run all pending migrations in order.
        Each migration:
        1. BEGIN TRANSACTION
        2. Execute SQL
        3. INSERT INTO migration_registry (version, name, filename, applied_at, checksum)
        4. UPDATE metadata SET value=version WHERE key='schema_version'
        5. COMMIT
        If any step fails → ROLLBACK that migration, stop, report.
        Returns: {applied: [...], skipped: [...], error: None|str}
        """

    def check(self, conn) -> dict:
        """Diagnosis only (safe for read-only/locked DB).
        Returns: {current_version, pending: [...], registry: [...], healthy: bool}
        No writes performed.
        """
```

---

## 4. CLI Commands

In the server entry point (`memory-server` or `__main__.py`), add argparse:

```python
parser.add_argument("--check-db", action="store_true", help="Check schema version and pending migrations")
parser.add_argument("--migrate", action="store_true", help="Apply pending migrations")
```

`--check-db`: opens DB read-only, prints status, exits 0 (healthy) or 1 (pending/error).
`--migrate`: opens DB read-write, runs pending, prints results, exits.

Both exit before starting the MCP server.

---

## 5. Integration with Storage Init

In `SqliteVecMemoryStorage.initialize()`:

```python
# Replace current _run_graph_migrations() with:
runner = MigrationRunner(migrations_dir)
result = runner.run_pending(conn)
if result["error"]:
    logger.error(f"Migration failed: {result['error']}")
    raise RuntimeError(f"Schema migration failed: {result['error']}")
logger.info(f"Schema at v{runner._get_current_version(conn)}, {len(result['applied'])} migrations applied")
```

---

## 6. Rename Existing Migrations

Current files (008-011) keep their names. The runner discovers them by prefix number.
Future migrations: `012_add_beliefs_table.sql`, `013_...`, etc.

---

## Files Affected

- `src/mcp_memory_service/storage/migration_runner.py` — full rewrite (~120 lines)
- `src/mcp_memory_service/storage/sqlite_vec.py` — replace `_run_graph_migrations()` with new runner call (~10 lines changed)
- `src/mcp_memory_service/server/__main__.py` or entry point — add `--check-db` / `--migrate` args (~30 lines)
- `tests/test_schema_versioning.py` — new test file (~100 lines)

**Total: ~260 lines new/rewritten + ~100 lines tests**

---

## Validation

```bash
.venv/bin/python -m pytest tests/test_schema_versioning.py -x -q --timeout=60
```

Test scenarios:
1. Fresh DB → all migrations applied, registry populated, version = 11
2. Existing DB (version 7) → only 008-011 applied
3. Already up-to-date → no migrations run, check reports healthy
4. Half-applied (simulate crash) → detectable via registry gap
5. `--check-db` on read-only DB → no writes, correct report
6. `--migrate` applies pending and updates version
7. Checksum mismatch detection (migration file changed after apply)

---

## Commit Strategy

1. `feat(schema): migration registry table + version tracking`
2. `feat(schema): rewrite MigrationRunner with transaction safety`
3. `feat(schema): --check-db and --migrate CLI commands`
4. `test(schema): versioning integration tests`

---

## Doobidoo's Requirements (verbatim)

- ✅ `schema_version` in metadata table
- ✅ Migration registry (version + name + file), apply only pending
- ✅ `--check-db` and `--migrate` CLI commands
- ✅ Missing version → assume 7, run from 008
- ✅ Each migration in transaction with `applied_at`
- ✅ `--check-db` safe against read-only/locked DB
