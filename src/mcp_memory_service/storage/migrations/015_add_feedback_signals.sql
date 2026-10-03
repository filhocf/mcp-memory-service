-- RFC-MM-01: Feedback Loop - passive signal tracking table
CREATE TABLE IF NOT EXISTS feedback_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    agent_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_feedback_hash ON feedback_signals(content_hash);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback_signals(created_at);
