-- RFC-MM-03: Gap detection table
-- Records queries where semantic search returned low-confidence results (score < threshold)
-- Used to identify knowledge gaps and guide future ingestion priorities.

CREATE TABLE IF NOT EXISTS memory_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    normalized_query TEXT NOT NULL,
    max_score REAL NOT NULL,
    agent_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_gaps_normalized ON memory_gaps(normalized_query);
CREATE INDEX IF NOT EXISTS idx_memory_gaps_resolved ON memory_gaps(resolved_at);
CREATE INDEX IF NOT EXISTS idx_memory_gaps_created ON memory_gaps(created_at);
