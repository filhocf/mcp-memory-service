"""Regression test for the migration 020 probe (H3).

The hub DB already has memories.facts_extracted_at (added by the original fork
migration in July) but migration_registry has no row for version 20. Without a
probe entry, run_pending re-runs the unconditional
`ALTER TABLE memories ADD COLUMN facts_extracted_at`, hits `duplicate column
name`, rolls back and breaks every later migration.

The fix adds version 20 to delta_probes so _stamp_probes recognizes the
pre-existing column and stamps 20 as applied instead of re-running the ALTER.
This test exercises the probe directly (the full run_pending needs the whole
008-019 schema; the probe behaviour is what matters here).
"""
import sqlite3

from pathlib import Path
import mcp_memory_service.storage as storage_pkg
from mcp_memory_service.storage.migration_runner import MigrationRunner


def _runner():
    migrations_dir = Path(storage_pkg.__file__).parent / "migrations"
    return MigrationRunner(migrations_dir)


def _registry(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS migration_registry ("
        "version INTEGER PRIMARY KEY, name TEXT NOT NULL, filename TEXT NOT NULL, "
        "applied_at TEXT, checksum TEXT)"
    )
    conn.commit()


def test_probe_020_stamps_when_facts_column_preexists(tmp_path):
    """Column already present + no v20 row -> probe stamps 20, no duplicate-column crash."""
    db = tmp_path / "hub_like.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE memories (id INTEGER PRIMARY KEY, content_hash TEXT, "
        "facts_extracted_at TEXT DEFAULT NULL)"
    )
    _registry(conn)

    runner = _runner()
    probe = {20: "SELECT 1 FROM pragma_table_info('memories') WHERE name='facts_extracted_at'"}
    stamped = runner._stamp_probes(conn, probe)

    assert 20 in stamped, f"probe did not stamp v20; stamped={stamped}"
    applied = {r[0] for r in conn.execute("SELECT version FROM migration_registry").fetchall()}
    assert 20 in applied
    conn.close()


def test_probe_020_does_not_stamp_when_column_absent(tmp_path):
    """Fresh DB without the column -> probe is a no-op (normal ALTER path applies it later)."""
    db = tmp_path / "fresh.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY, content_hash TEXT)")
    _registry(conn)

    runner = _runner()
    probe = {20: "SELECT 1 FROM pragma_table_info('memories') WHERE name='facts_extracted_at'"}
    stamped = runner._stamp_probes(conn, probe)

    assert 20 not in stamped, "probe stamped v20 on a DB that lacks the column"
    conn.close()
