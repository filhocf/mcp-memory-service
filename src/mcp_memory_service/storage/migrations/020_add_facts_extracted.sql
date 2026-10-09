-- Migration 020: Add facts_extracted_at column for incremental fact extraction (RFC-MM-02)
-- Tracks which memories have already been processed by the LLM fact extraction pipeline.
-- NULL = pending processing. Timestamp = already processed (never reprocess).

ALTER TABLE memories ADD COLUMN facts_extracted_at TEXT DEFAULT NULL;

-- Index for efficient pending chunk retrieval
CREATE INDEX IF NOT EXISTS idx_memories_facts_pending
    ON memories(facts_extracted_at) WHERE facts_extracted_at IS NULL;