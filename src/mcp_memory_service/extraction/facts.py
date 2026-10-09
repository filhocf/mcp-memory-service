"""Batch incremental fact extraction from memory chunks via LLM (RFC-MM-02).

Extracts atomic (Subject, Predicate, Object) triples from unprocessed memory
chunks and stores them as typed edges in memory_graph for multi-hop navigation.

Uses HarvestRewriter configuration: HARVEST_LLM_PROVIDERS or GROQ_API_KEY.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

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
    """Get LLM configuration from environment. Returns None if not configured.
    
    FIXED H1: Now checks HarvestRewriter.is_configured to align gate with actual LLM usage.
    """
    from ..harvest.rewriter import HarvestRewriter
    
    rewriter = HarvestRewriter()
    if not rewriter.is_configured:
        return None
        
    # Return placeholder config since HarvestRewriter handles the actual calling
    return {"configured": True}


def get_pending_chunks(conn: sqlite3.Connection, limit: int = BATCH_SIZE) -> List[Dict[str, Any]]:
    """Get unprocessed memory chunks for fact extraction.
    
    Returns list of dicts with 'content_hash' and 'content' keys.
    """
    
    cursor = conn.execute("""
        SELECT content_hash, content 
        FROM memories 
        WHERE facts_extracted_at IS NULL 
        ORDER BY created_at ASC 
        LIMIT ?
    """, (limit,))
    
    chunks = [{"content_hash": row[0], "content": row[1]} for row in cursor.fetchall()]
    logger.debug("Found %d pending chunks for fact extraction", len(chunks))
    return chunks


async def extract_facts_batch(chunks: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Extract facts from a batch of chunks using LLM.
    
    Returns:
    - List of results on success (may be empty if no facts found)
    - None on failure (LLM unavailable, error, etc.) - chunks should not be marked processed
    
    FIXED H2: Uses None sentinel to distinguish failure from success-no-facts.
    """
    from ..compat import _sanitize_log_value
    
    if not chunks:
        return []  # Success: no chunks to process
        
    config = get_llm_config()
    if not config:
        logger.warning("LLM not configured for fact extraction, skipping batch")
        return None  # FAILURE: LLM not configured
    
    # Format chunks for prompt
    chunk_text = "\n\n".join(f"Chunk {i}: {chunk['content']}" 
                             for i, chunk in enumerate(chunks))
    prompt = EXTRACTION_PROMPT.format(chunks=chunk_text)
    
    try:
        # Import and use the HarvestRewriter for LLM calls
        from ..harvest.rewriter import HarvestRewriter
        
        rewriter = HarvestRewriter()
        if not rewriter.is_configured:
            logger.warning("HarvestRewriter not configured for fact extraction, skipping batch")
            return None  # FAILURE: Rewriter not configured
            
        response_tuple = await rewriter._call_llm(prompt, LLM_TIMEOUT, max_tokens=2000)
        response = response_tuple[0] if response_tuple else ""
        
        if not response or not response.strip():
            logger.warning("Empty response from LLM fact extraction")
            return None  # FAILURE: Empty response from LLM
            
        # Parse JSON response
        try:
            results = json.loads(response)
            if not isinstance(results, list):
                logger.warning("LLM returned non-list for fact extraction: %s", _sanitize_log_value(response[:100]))
                return None  # FAILURE: Invalid response format
            
            logger.debug("Extracted facts from %d chunks", len(results))
            return results  # SUCCESS: May be empty list if no facts found
            
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM response as JSON: %s", _sanitize_log_value(str(e)))
            return None  # FAILURE: JSON parse error
            
    except Exception as e:
        # FIXED H2: Return None for failure instead of empty list
        logger.warning("LLM fact extraction failed, skipping batch: %s", _sanitize_log_value(str(e)))
        return None  # FAILURE: Exception during LLM call


def store_facts(conn: sqlite3.Connection, chunk_hash: str, facts: List[Dict[str, Any]]) -> int:
    """Store extracted facts as typed edges in memory_graph.
    
    M2.4: Dedup by (source, target, rel_type), update if confidence higher.
    Returns number of facts stored/updated.
    """
    from ..compat import _sanitize_log_value
    
    if not facts:
        return 0
        
    stored_count = 0
    now = datetime.now(timezone.utc).timestamp()
    
    for fact in facts:
        try:
            subject = str(fact.get("s", "")).strip()
            predicate = str(fact.get("p", "")).strip()
            obj = str(fact.get("o", "")).strip()
            confidence = float(fact.get("confidence", 0.5))
            
            if not all([subject, predicate, obj]):
                logger.debug("Skipping incomplete fact: s=%s, p=%s, o=%s", 
                           _sanitize_log_value(subject), _sanitize_log_value(predicate), 
                           _sanitize_log_value(obj))
                continue
                
            # Normalize predicate for relationship type
            rel_type = predicate.lower().replace(" ", "_")
            
            # Create metadata with confidence and provenance
            metadata = json.dumps({
                "confidence": confidence,
                "source_chunk": chunk_hash,
                "extracted_at": datetime.now(timezone.utc).isoformat()
            })
            
            # Check if an edge for this pair already exists (M2.4 dedup).
            # memory_graph PK is (source_hash, target_hash) — only two columns —
            # so dedup/upsert MUST key on the pair, not on relationship_type (M1).
            # relationship_type is part of the mutable payload: a higher-confidence
            # fact overwrites the pair's predicate too.
            existing = conn.execute("""
                SELECT metadata FROM memory_graph
                WHERE source_hash = ? AND target_hash = ?
            """, (subject, obj)).fetchone()

            # connection_types is a JSON array across the codebase (not a bare string) — M2.
            connection_types = json.dumps(["extracted_fact"])

            if existing:
                # Update only if the new fact is more confident than the stored one.
                try:
                    existing_meta = json.loads(existing[0] or "{}")
                    existing_confidence = existing_meta.get("confidence", 0.0)
                except (json.JSONDecodeError, TypeError):
                    existing_confidence = -1.0  # corrupt metadata -> always overwrite

                if confidence > existing_confidence:
                    conn.execute("""
                        UPDATE memory_graph
                        SET metadata = ?, similarity = ?, relationship_type = ?, connection_types = ?
                        WHERE source_hash = ? AND target_hash = ?
                    """, (metadata, confidence, rel_type, connection_types, subject, obj))
                    stored_count += 1
                    logger.debug("Updated fact %s -> %s (confidence %.2f -> %.2f)",
                               _sanitize_log_value(subject), _sanitize_log_value(obj),
                               existing_confidence, confidence)
                else:
                    logger.debug("Skipping fact %s -> %s (lower confidence %.2f vs %.2f)",
                               _sanitize_log_value(subject), _sanitize_log_value(obj),
                               confidence, existing_confidence)
            else:
                # Insert new fact
                conn.execute("""
                    INSERT INTO memory_graph 
                    (source_hash, target_hash, similarity, connection_types, 
                     relationship_type, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (subject, obj, confidence, connection_types, rel_type, metadata, now))
                stored_count += 1
                logger.debug("Stored new fact: %s -[%s]-> %s (confidence %.2f)", 
                           _sanitize_log_value(subject), _sanitize_log_value(rel_type), 
                           _sanitize_log_value(obj), confidence)
                
        except Exception as e:
            logger.warning("Failed to store fact %s: %s", _sanitize_log_value(str(fact)), 
                         _sanitize_log_value(str(e)))
            continue
    
    if stored_count > 0:
        conn.commit()
        
    return stored_count


def mark_processed(conn: sqlite3.Connection, chunk_hashes: List[str]) -> None:
    """Mark chunks as processed to prevent reprocessing (M2.5 idempotency)."""
    if not chunk_hashes:
        return
        
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    placeholders = ",".join("?" * len(chunk_hashes))
    
    conn.execute(f"""
        UPDATE memories 
        SET facts_extracted_at = ? 
        WHERE content_hash IN ({placeholders})
    """, [now] + chunk_hashes)
    
    conn.commit()
    logger.debug("Marked %d chunks as processed", len(chunk_hashes))


def get_extraction_status(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Get current status of fact extraction pipeline."""
    # Count pending chunks
    pending_count = conn.execute("""
        SELECT COUNT(*) FROM memories WHERE facts_extracted_at IS NULL
    """).fetchone()[0]
    
    # Count processed chunks
    processed_count = conn.execute("""
        SELECT COUNT(*) FROM memories WHERE facts_extracted_at IS NOT NULL
    """).fetchone()[0]
    
    # Count extracted facts
    facts_count = conn.execute("""
        SELECT COUNT(*) FROM memory_graph WHERE connection_types LIKE '%extracted_fact%'
    """).fetchone()[0]
    
    # Last extraction time
    last_run = conn.execute("""
        SELECT MAX(facts_extracted_at) FROM memories WHERE facts_extracted_at IS NOT NULL
    """).fetchone()[0]
    
    return {
        "pending_chunks": pending_count,
        "processed_chunks": processed_count,
        "extracted_facts": facts_count,
        "last_extraction": last_run,
        "llm_configured": get_llm_config() is not None
    }


async def run_extraction(conn: sqlite3.Connection, limit: int = MAX_CHUNKS_PER_RUN) -> Dict[str, Any]:
    """Run fact extraction pipeline on pending chunks.
    
    Returns summary of extraction results.
    """
    from ..compat import _sanitize_log_value
    
    config = get_llm_config()
    if not config:
        return {
            "error": "LLM not configured. Set HARVEST_LLM_PROVIDERS or GROQ_API_KEY.",
            "processed": 0,
            "facts_stored": 0
        }
    
    start_time = datetime.now()
    total_processed = 0
    total_facts = 0
    
    logger.info("Starting fact extraction (limit=%d)", limit)
    
    while total_processed < limit:
        batch_limit = min(BATCH_SIZE, limit - total_processed)
        chunks = get_pending_chunks(conn, batch_limit)
        
        if not chunks:
            logger.info("No more pending chunks for extraction")
            break
            
        # Extract facts from batch
        extraction_results = await extract_facts_batch(chunks)
        
        # FIXED H2: Check for failure (None) vs success (list, may be empty)
        if extraction_results is None:
            # LLM failed - do NOT mark chunks as processed, retry next time
            logger.warning("Batch extraction failed, aborting run for retry in next scheduled execution")
            break  # FIXED H1: Break instead of continue to avoid infinite loop
        
        # Process results and store facts
        batch_facts = 0
        processed_hashes = []
        
        for i, chunk in enumerate(chunks):
            chunk_hash = chunk["content_hash"]
            processed_hashes.append(chunk_hash)
            
            # Find facts for this chunk
            chunk_results = [r for r in extraction_results if r.get("chunk") == i]
            
            for result in chunk_results:
                facts = result.get("facts", [])
                if facts:
                    stored = store_facts(conn, chunk_hash, facts)
                    batch_facts += stored
        
        # Mark chunks as processed only on SUCCESS (extraction_results is not None)
        mark_processed(conn, processed_hashes)
        
        total_processed += len(chunks)
        total_facts += batch_facts
        
        logger.debug("Batch complete: %d chunks, %d facts stored", len(chunks), batch_facts)
        
        # Throttle between batches
        if len(chunks) == batch_limit and total_processed < limit:
            import asyncio
            await asyncio.sleep(THROTTLE_SECONDS)
    
    duration = (datetime.now() - start_time).total_seconds()
    
    result = {
        "processed": total_processed,
        "facts_stored": total_facts,
        "duration_seconds": duration,
        "batches": (total_processed + BATCH_SIZE - 1) // BATCH_SIZE
    }
    
    logger.info("Fact extraction complete: %s", _sanitize_log_value(str(result)))
    return result