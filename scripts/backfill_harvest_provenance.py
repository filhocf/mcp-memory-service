#!/usr/bin/env python3
"""Backfill harvest provenance on legacy memories (RFC-harvest-provenance R5/R6).

Marks existing `session-harvest` / `mining` memories that have no
`harvest_method` as `harvest:method:heuristic-legacy` (+ metadata), so the
legacy corpus becomes identifiable and re-harvestable.

Idempotent (R14): skips memories already carrying a `harvest:method:*` tag.
Dry-run by default (R15): pass --apply to write.

Usage:
    python backfill_harvest_provenance.py            # dry-run
    python backfill_harvest_provenance.py --apply    # write
"""
import argparse
import json
import sqlite3
import sys

METHOD_TAG_PREFIX = "harvest:method:"
LEGACY_TAG = "harvest:method:heuristic-legacy"


def backfill(db_path: str, apply: bool) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Candidates: harvested memories (session-harvest OR mining) WITHOUT a method tag.
    rows = cur.execute(
        """
        SELECT content_hash, tags, metadata FROM memories
        WHERE (tags LIKE '%session-harvest%' OR tags LIKE '%mining%')
          AND tags NOT LIKE '%harvest:method:%'
        """
    ).fetchall()

    stats = {"candidates": len(rows), "updated": 0, "skipped": 0}
    for r in rows:
        tags = r["tags"] or ""
        # Idempotency guard (belt + suspenders vs the SQL filter)
        if METHOD_TAG_PREFIX in tags:
            stats["skipped"] += 1
            continue
        new_tags = tags + ("," if tags else "") + LEGACY_TAG
        try:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            if not isinstance(meta, dict):
                raise ValueError("metadata is not a JSON object")
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            # Do NOT silently overwrite corrupted metadata — skip and report,
            # so we never destroy data we can't parse.
            print(f"  WARN: skipping {r['content_hash'][:8]} — unparseable metadata ({e})")
            stats["skipped"] += 1
            continue
        meta.setdefault("harvest_method", "heuristic-legacy")
        meta.setdefault("harvest_pipeline_version", 0)
        if apply:
            cur.execute(
                "UPDATE memories SET tags = ?, metadata = ? WHERE content_hash = ?",
                (new_tags, json.dumps(meta), r["content_hash"]),
            )
        stats["updated"] += 1

    if apply:
        conn.commit()
    conn.close()
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/home/claudio/local-data/mcp/sqlite_vec.db")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args()

    stats = backfill(args.db, args.apply)
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] candidates={stats['candidates']} updated={stats['updated']} skipped={stats['skipped']}")
    if not args.apply:
        print("Re-run with --apply to write.")
