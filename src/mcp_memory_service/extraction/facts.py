"""Batch incremental fact extraction from memory chunks via LLM (RFC-MM-02).

Extracts atomic (Subject, Predicate, Object) triples from unprocessed memory
chunks and stores them as typed edges in memory_graph for multi-hop navigation.

Uses the same NLI LLM cascade env vars: MCP_NLI_LLM_BASE_URL, MCP_NLI_LLM_MODEL,
MCP_NLI_LLM_API_KEY.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# LLM configuration from environment
_ENV_BASE_URL = "MCP_NLI_LLM_BASE_URL"
_ENV_MODEL = "MCP_NLI_LLM_MODEL"
_ENV_API_KEY = "MCP_NLI_LLM_API_KEY"

BATCH_SIZE = 20
MAX_CHUNKS_PER_RUN = 200
THROTTLE_SECONDS = 1.0
LLM_TIMEOUT = 30.0
LLM_MAX_RETRIES = 1

EXTRACTION_PROMPT = """Extract atomic facts from these text chunks.
Return ONLY valid JSON: an array of objects, one per chunk that has facts.
Format: [{{"chunk": N, "facts": [{{"s": "subject", "p": "predicate", "o": "object", "confidence": 0.9}}]}}]

Rules:
- Only extract facts that are EXPLICITLY stated. Do not infer.
- Subject and Object should be named entities, concepts, or specific values.
- Predicate should be a concise verb phrase (e.g. "uses", "depends_on", "is_part_of").
- Confidence: 0.9 for clearly stated facts, 0.7 for implied but likely, 0.5 for uncertain.
- If a chunk has no extractable facts, omit it from the array.
- Return empty array [] if no facts found in any chunk.

{chunks}"""


def get_llm_config() -> Optional[dict]:
    """Get LLM configuration from environment. Returns None if not configured."""
    base_url = os.environ.get(_ENV_BASE_URL, "")
    model = os.environ.get(_ENV_MODEL, "")
    if not base_url or not model:
        return None
    return {
        "base_url": base_url,
        "model": model,
        "api_key": os.environ.get(_ENV_API_KEY, ""),
    }


def get_pending_chunks(conn: sqlite3.Connection, limit: int = MAX_CHUNKS_PER_RUN) -> list[dict]:
    """Get memory chunks that haven't been processed for fact extraction.

    Returns list of dicts with keys: content_hash, content.
    """
    cursor = conn.execute(
        "SELECT content_hash, content FROM memories "
        "WHERE facts_extracted_at IS NULL "
        "ORDER BY created_at DESC "
        "LIMIT ?",
        (limit,),
    )
    return [{"content_hash": row[0], "content": row[1]} for row in cursor.fetchall()]


def mark_processed(conn: sqlite3.Connection, hashes: list[str]) -> None:
    """Mark chunks as processed by setting facts_extracted_at timestamp."""
    if not hashes:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    placeholders = ",".join("?" * len(hashes))
    conn.execute(
        f"UPDATE memories SET facts_extracted_at = ? "
        f"WHERE content_hash IN ({placeholders})",
        [now] + hashes,
    )
    conn.commit()


def store_facts(conn: sqlite3.Connection, facts: list[dict]) -> int:
    """Store extracted facts in memory_graph with dedup.

    Each fact has: s (subject), p (predicate), o (object), confidence, source_chunk.
    Uses source_hash='entity:Subject', target_hash='entity:Object',
    relationship_type=predicate.

    Dedup: same (source, target, relationship_type) → update if higher confidence.
    Returns number of facts stored/updated.
    """
    stored = 0
    for fact in facts:
        subject = fact.get("s", "").strip()
        predicate = fact.get("p", "").strip()
        obj = fact.get("o", "").strip()
        confidence = float(fact.get("confidence", 0.7))
        source_chunk = fact.get("source_chunk", "")

        if not subject or not predicate or not obj:
            continue

        source_hash = f"entity:{subject}"
        target_hash = f"entity:{obj}"
        # Normalize predicate to snake_case-ish
        relationship_type = predicate.lower().replace(" ", "_")

        metadata_dict = {
            "confidence": confidence,
            "source_chunk": source_chunk,
            "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
        metadata_json = json.dumps(metadata_dict)

        # Check existing
        existing = conn.execute(
            "SELECT metadata FROM memory_graph "
            "WHERE source_hash = ? AND target_hash = ? AND relationship_type = ?",
            (source_hash, target_hash, relationship_type),
        ).fetchone()

        if existing:
            # Update only if new confidence is higher
            try:
                old_meta = json.loads(existing[0]) if existing[0] else {}
                old_confidence = old_meta.get("confidence", 0)
            except (json.JSONDecodeError, TypeError):
                old_confidence = 0

            if confidence > old_confidence:
                conn.execute(
                    "UPDATE memory_graph SET metadata = ?, similarity = ? "
                    "WHERE source_hash = ? AND target_hash = ? AND relationship_type = ?",
                    (metadata_json, confidence, source_hash, target_hash, relationship_type),
                )
                stored += 1
        else:
            # Insert new fact edge
            now_ts = datetime.now(timezone.utc).timestamp()
            conn.execute(
                "INSERT INTO memory_graph "
                "(source_hash, target_hash, similarity, connection_types, "
                "relationship_type, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    source_hash,
                    target_hash,
                    confidence,
                    json.dumps(["fact"]),
                    relationship_type,
                    metadata_json,
                    now_ts,
                ),
            )
            stored += 1

    conn.commit()
    return stored


async def extract_facts_batch(
    chunks: list[dict], provider_config: dict
) -> list[dict]:
    """Send batch of chunks to LLM and extract facts.

    Args:
        chunks: list of dicts with 'content_hash' and 'content'.
        provider_config: dict with 'base_url', 'model', 'api_key'.

    Returns:
        List of fact dicts: {s, p, o, confidence, source_chunk}.
    """
    import httpx

    if not chunks:
        return []

    # Build prompt with numbered chunks
    chunk_text = ""
    for i, chunk in enumerate(chunks, 1):
        # Truncate content to avoid token overflow
        content = chunk["content"][:600]
        chunk_text += f"\nCHUNK {i} (hash: {chunk['content_hash'][:8]}):\n{content}\n"

    prompt = EXTRACTION_PROMPT.format(chunks=chunk_text)

    headers = {"Content-Type": "application/json"}
    api_key = provider_config.get("api_key", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": provider_config["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2000,
    }

    all_facts = []
    last_error = None

    for attempt in range(1 + LLM_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
                resp = await client.post(
                    f"{provider_config['base_url']}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"] or ""
                all_facts = _parse_llm_response(content, chunks)
                return all_facts
        except Exception as e:
            last_error = e
            logger.warning(
                f"Fact extraction LLM call failed (attempt {attempt + 1}): {e}"
            )
            if attempt < LLM_MAX_RETRIES:
                import asyncio
                await asyncio.sleep(2)

    logger.error(f"Fact extraction failed after retries: {last_error}")
    return []


def _parse_llm_response(content: str, chunks: list[dict]) -> list[dict]:
    """Parse LLM JSON response into flat list of fact dicts."""
    facts = []

    # Try to extract JSON from the response (may have markdown wrapping)
    content = content.strip()
    if content.startswith("```"):
        # Strip markdown code block
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # Try to find JSON array in the response
        import re
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM fact extraction response")
                return []
        else:
            logger.warning("No JSON array found in LLM response")
            return []

    if not isinstance(parsed, list):
        return []

    for item in parsed:
        if not isinstance(item, dict):
            continue
        chunk_idx = item.get("chunk", 0) - 1  # 1-indexed in prompt
        chunk_hash = ""
        if 0 <= chunk_idx < len(chunks):
            chunk_hash = chunks[chunk_idx]["content_hash"]

        for fact in item.get("facts", []):
            if isinstance(fact, dict) and "s" in fact and "p" in fact and "o" in fact:
                facts.append({
                    "s": fact["s"],
                    "p": fact["p"],
                    "o": fact["o"],
                    "confidence": float(fact.get("confidence", 0.7)),
                    "source_chunk": chunk_hash,
                })

    return facts


async def run_extraction(conn: sqlite3.Connection, limit: int = MAX_CHUNKS_PER_RUN) -> dict:
    """Run a full extraction cycle: get pending → extract → store → mark.

    Returns stats dict.
    """
    import asyncio

    config = get_llm_config()
    if not config:
        logger.debug("Fact extraction skipped: LLM not configured")
        return {"status": "skipped", "reason": "llm_not_configured"}

    pending = get_pending_chunks(conn, limit=limit)
    if not pending:
        return {"status": "ok", "pending": 0, "facts_stored": 0, "chunks_processed": 0}

    total_facts = 0
    total_processed = 0

    # Process in batches of BATCH_SIZE
    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i : i + BATCH_SIZE]
        facts = await extract_facts_batch(batch, config)

        if facts:
            stored = store_facts(conn, facts)
            total_facts += stored

        # Mark as processed regardless of whether facts were found
        batch_hashes = [c["content_hash"] for c in batch]
        mark_processed(conn, batch_hashes)
        total_processed += len(batch)

        # Throttle between batches
        if i + BATCH_SIZE < len(pending):
            await asyncio.sleep(THROTTLE_SECONDS)

    return {
        "status": "ok",
        "pending": len(pending),
        "facts_stored": total_facts,
        "chunks_processed": total_processed,
    }


def get_extraction_status(conn: sqlite3.Connection) -> dict:
    """Get status of fact extraction pipeline."""
    total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    # Check if column exists (migration may not have run)
    try:
        pending = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE facts_extracted_at IS NULL"
        ).fetchone()[0]
        processed = total - pending
    except sqlite3.OperationalError:
        # Column doesn't exist yet
        return {
            "total_memories": total,
            "pending": total,
            "processed": 0,
            "facts_total": 0,
            "last_run": None,
            "migration_pending": True,
        }

    # Count fact edges in graph
    try:
        facts_total = conn.execute(
            "SELECT COUNT(*) FROM memory_graph WHERE connection_types LIKE '%fact%'"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        facts_total = 0

    # Last extraction timestamp
    last_run_row = conn.execute(
        "SELECT MAX(facts_extracted_at) FROM memories WHERE facts_extracted_at IS NOT NULL"
    ).fetchone()
    last_run = last_run_row[0] if last_run_row else None

    return {
        "total_memories": total,
        "pending": pending,
        "processed": processed,
        "facts_total": facts_total,
        "last_run": last_run,
        "migration_pending": False,
    }
