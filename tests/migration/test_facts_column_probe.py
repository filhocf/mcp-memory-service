"""Regression test for the facts_extracted_at migration probe.

The hub DB already has memories.facts_extracted_at (added by the original fork
migration in July) but migration_registry has no row for its version. Without a
probe entry, run_pending re-runs the unconditional
`ALTER TABLE memories ADD COLUMN facts_extracted_at`, hits `duplicate column
name`, rolls back and breaks every later migration.

The fix adds the facts version to delta_probes so _stamp_probes recognizes the
pre-existing column and stamps it as applied instead of re-running the ALTER.

NOTE (31/out): the facts migration was renumbered 020 -> 022 after upstream #1729
landed `020_add_belief_embedding.sql` (a real numbering collision — two fork/upstream
migrations both claimed 020). The probe and this test now use version 22.
"""
import sqlite3

from pathlib import Path
import mcp_memory_service.storage as storage_pkg
from mcp_memory_service.storage.migration_runner import MigrationRunner


FACTS_VERSION = 22
FACTS_PROBE = {FACTS_VERSION: "SELECT 1 FROM pragma_table_info('memories') WHERE name='facts_extracted_at'"}


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


def test_probe_stamps_when_facts_column_preexists(tmp_path):
    """Column already present + no facts-version row -> probe stamps it, no duplicate-column crash."""
    db = tmp_path / "hub_like.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE memories (id INTEGER PRIMARY KEY, content_hash TEXT, "
        "facts_extracted_at TEXT DEFAULT NULL)"
    )
    _registry(conn)

    runner = _runner()
    stamped = runner._stamp_probes(conn, FACTS_PROBE)

    assert FACTS_VERSION in stamped, f"probe did not stamp v{FACTS_VERSION}; stamped={stamped}"
    applied = {r[0] for r in conn.execute("SELECT version FROM migration_registry").fetchall()}
    assert FACTS_VERSION in applied
    conn.close()


def test_probe_does_not_stamp_when_column_absent(tmp_path):
    """Fresh DB without the column -> probe is a no-op (normal ALTER path applies it later)."""
    db = tmp_path / "fresh.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY, content_hash TEXT)")
    _registry(conn)

    runner = _runner()
    stamped = runner._stamp_probes(conn, FACTS_PROBE)

    assert FACTS_VERSION not in stamped, "probe stamped the facts version on a DB that lacks the column"
    conn.close()
