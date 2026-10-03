-- Usage Telemetry: PROVEITO/USO instrumentation events (v1, sqlite-vec).
-- Privacy: raw queries and content are NEVER stored. Only a truncated sha256
-- query_hash plus length are kept.
-- Additive and best-effort: telemetry failures must never break the read path.
CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT,
    tool TEXT,
    content_hash TEXT,
    query_hash TEXT,
    n_results INTEGER,
    latency_ms REAL,
    rating INTEGER,
    source TEXT,
    agent_id TEXT,
    timestamp TEXT,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_usage_events_ts_type ON usage_events(timestamp, event_type);
