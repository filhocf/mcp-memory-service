#!/usr/bin/env python3
"""Adversarial evaluation for freshness (frente C) and forgetting (frente B)."""

import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from mcp_memory_service.models.memory import Memory
from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage

logger = logging.getLogger(__name__)

# Fixed seed for deterministic timestamps
FIXED_SEED_DATE = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)


def _get_versioned_pairs() -> List[Dict[str, str]]:
    """Generate synthetic versioned fact pairs (v1 older, v2 newer).
    
    Returns list of dicts with keys: v1_content, v2_content, query.
    The query should retrieve both versions, and we test if v2 ranks above v1.
    
    v1 and v2 are semantically VERY similar (minor updates) so that freshness
    boost can be the tiebreaker.
    """
    return [
        {
            "v1_content": "Redis supports atomic operations for data consistency",
            "v2_content": "Redis supports atomic operations for data consistency and performance",
            "query": "How does Redis handle data consistency?"
        },
        {
            "v1_content": "Docker containers use kernel namespaces for isolation",
            "v2_content": "Docker containers use kernel namespaces for strong isolation",
            "query": "How do Docker containers achieve isolation?"
        },
        {
            "v1_content": "PostgreSQL autovacuum cleans up deleted tuple storage",
            "v2_content": "PostgreSQL autovacuum efficiently cleans up deleted tuple storage",
            "query": "How does PostgreSQL handle storage cleanup?"
        },
    ]


def _get_unused_beliefs() -> List[Dict[str, str]]:
    """Generate synthetic beliefs that will be injected but never used.
    
    These beliefs test the forgetting mechanism (frente B).
    Returns list of dicts with keys: content, confidence.
    """
    return [
        {"content": "Kafka partitions enable parallel message processing", "confidence": 0.75},
        {"content": "Elasticsearch sharding distributes data across nodes", "confidence": 0.8},
        {"content": "RabbitMQ exchanges route messages to queues", "confidence": 0.7},
    ]


async def _ingest_versioned_pairs(
    storage: SqliteVecMemoryStorage,
    pairs: List[Dict[str, str]],
) -> None:
    """Ingest versioned pairs as both memories AND beliefs with deterministic timestamps."""
    old_timestamp = (FIXED_SEED_DATE - timedelta(days=2)).timestamp()
    new_timestamp = (FIXED_SEED_DATE - timedelta(hours=1)).timestamp()
    
    old_iso = datetime.fromtimestamp(old_timestamp).isoformat() + "Z"
    new_iso = datetime.fromtimestamp(new_timestamp).isoformat() + "Z"
    
    conn = storage.conn
    
    for i, pair in enumerate(pairs):
        # Store v1 (older) as memory
        v1_hash = hashlib.sha256(f"v1_{i}_{pair['v1_content']}".encode()).hexdigest()
        v1_memory = Memory(
            content=pair["v1_content"],
            content_hash=v1_hash,
            tags=["adversarial", "versioned", f"pair_{i}", "v1"],
            memory_type="observation",
            created_at=old_timestamp,
        )
        await storage.store(v1_memory, skip_semantic_dedup=True)
        
        # Also create v1 as belief
        conn.execute("""
            INSERT OR IGNORE INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            f"belief_v1_{i}",
            pair["v1_content"],
            0.85,
            "active",
            old_iso,
            old_iso,
            json.dumps([v1_hash]),
        ))
        
        # Store v2 (newer) as memory
        v2_hash = hashlib.sha256(f"v2_{i}_{pair['v2_content']}".encode()).hexdigest()
        v2_memory = Memory(
            content=pair["v2_content"],
            content_hash=v2_hash,
            tags=["adversarial", "versioned", f"pair_{i}", "v2"],
            memory_type="observation",
            created_at=new_timestamp,
        )
        await storage.store(v2_memory, skip_semantic_dedup=True)
        
        # Also create v2 as belief
        conn.execute("""
            INSERT OR IGNORE INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            f"belief_v2_{i}",
            pair["v2_content"],
            0.85,  # Same confidence to isolate freshness effect
            "active",
            new_iso,
            new_iso,
            json.dumps([v2_hash]),
        ))
    
    conn.commit()


async def _ingest_unused_beliefs(
    storage: SqliteVecMemoryStorage,
    beliefs: List[Dict[str, str]],
) -> None:
    """Ingest unused beliefs into storage for forgetting measurement."""
    timestamp = FIXED_SEED_DATE.timestamp()
    
    # Insert directly into beliefs table (not memories)
    conn = storage.conn
    
    for i, belief in enumerate(beliefs):
        belief_hash = hashlib.sha256(f"unused_{i}_{belief['content']}".encode()).hexdigest()
        
        conn.execute("""
            INSERT OR IGNORE INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            belief_hash,
            belief["content"],
            belief["confidence"],
            "active",
            datetime.fromtimestamp(timestamp).isoformat(),
            datetime.fromtimestamp(timestamp).isoformat(),
            json.dumps([f"mem_{i}"]),
        ))
    
    conn.commit()


def _find_belief_ranks(beliefs: List[Dict], v1_hash: str, v2_hash: str) -> tuple:
    """Find ranks of v1 and v2 beliefs in result list."""
    v1_rank = None
    v2_rank = None
    
    for rank, belief in enumerate(beliefs, start=1):
        belief_hash = belief.get("belief_hash", "")
        if belief_hash == v1_hash:
            v1_rank = rank
        if belief_hash == v2_hash:
            v2_rank = rank
    
    return v1_rank, v2_rank


async def _measure_freshness(
    storage: SqliteVecMemoryStorage,
    pairs: List[Dict[str, str]],
) -> float:
    """Measure taxa_freshness: fraction of pairs where v2 ranks above v1.
    
    Uses memory_context (which applies freshness boost if MCP_INJECT_FRESHNESS=true).
    Returns fraction in [0, 1].
    """
    if not pairs:
        return 0.0
    
    # Import memory_context from context_injection
    from mcp_memory_service.storage.context_injection import memory_context
    
    freshness_wins = 0
    
    for i, pair in enumerate(pairs):
        # Use memory_context (not retrieve) to get beliefs with freshness boosting
        result = await memory_context(storage, task=pair["query"], limit=10)
        beliefs = result.get("beliefs", [])
        
        # Find ranks of v1 and v2 by belief_hash
        v1_hash = f"belief_v1_{i}"
        v2_hash = f"belief_v2_{i}"
        v1_rank, v2_rank = _find_belief_ranks(beliefs, v1_hash, v2_hash)
        
        # Count as win if v2 ranks above v1 (lower rank number = better)
        if v2_rank is not None and v1_rank is not None and v2_rank < v1_rank:
            freshness_wins += 1
    
    return freshness_wins / len(pairs)


def _get_initial_confidences(storage: SqliteVecMemoryStorage, belief_hashes: List[str]) -> Dict[str, float]:
    """Read initial confidence values for beliefs."""
    conn = storage.conn
    placeholders = ",".join("?" * len(belief_hashes))
    cursor = conn.execute(
        f"SELECT belief_hash, confidence FROM beliefs WHERE belief_hash IN ({placeholders})",
        belief_hashes
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


def _count_confidence_drops(storage: SqliteVecMemoryStorage, initial_confidences: Dict[str, float]) -> int:
    """Count how many beliefs had confidence drop from initial values."""
    if not initial_confidences:
        return 0
    
    conn = storage.conn
    placeholders = ",".join("?" * len(initial_confidences))
    cursor = conn.execute(
        f"SELECT belief_hash, confidence FROM beliefs WHERE belief_hash IN ({placeholders})",
        list(initial_confidences.keys())
    )
    
    dropped_count = 0
    for belief_hash, current_confidence in cursor.fetchall():
        initial_confidence = initial_confidences.get(belief_hash, 0.0)
        if current_confidence < initial_confidence:
            dropped_count += 1
    
    return dropped_count


def _get_belief_hashes_from_contents(storage: SqliteVecMemoryStorage, contents: List[str]) -> List[str]:
    """Get belief hashes for given content strings."""
    conn = storage.conn
    placeholders = ",".join("?" * len(contents))
    cursor = conn.execute(
        f"SELECT belief_hash FROM beliefs WHERE content IN ({placeholders})",
        contents
    )
    return [row[0] for row in cursor.fetchall()]


async def _create_unused_injection_events(
    storage: SqliteVecMemoryStorage,
    belief_hashes: List[str],
    threshold: int,
    agent_id: str,
    now: datetime
) -> None:
    """Create synthetic injection events for unused beliefs."""
    from mcp_memory_service.storage.usage_telemetry import log_usage_event
    
    # Fetch derived_from for each belief to construct source_hashes
    conn = storage.conn
    placeholders = ",".join("?" * len(belief_hashes))
    cursor = conn.execute(
        f"SELECT belief_hash, derived_from FROM beliefs WHERE belief_hash IN ({placeholders})",
        belief_hashes
    )
    belief_sources = {row[0]: json.loads(row[1]) if row[1] else [] for row in cursor.fetchall()}
    
    for belief_hash in belief_hashes:
        # Get source_hashes from derived_from (mirroring production context_injection)
        source_hashes = belief_sources.get(belief_hash, [])
        
        for i in range(threshold + 1):  # Exceed threshold to trigger penalty
            injection_time = (now - timedelta(minutes=i*10)).isoformat()
            metadata = {
                "belief_hashes": [belief_hash],
                "source_hashes": source_hashes
            }
            
            await log_usage_event(
                storage,
                "injection",
                agent_id=agent_id,
                query_hash=f"synthetic_query_{i}_{belief_hash}",
                timestamp=injection_time,
                metadata=json.dumps(metadata)
            )


async def _apply_penalty_to_beliefs(
    storage: SqliteVecMemoryStorage,
    belief_hashes: List[str],
    now: datetime
) -> None:
    """Apply penalty to beliefs using production code."""
    from mcp_memory_service.consolidation.belief_service import BeliefService
    
    belief_service = BeliefService(storage)
    
    for belief_hash in belief_hashes:
        existing = await belief_service._get_belief(belief_hash)
        if not existing:
            continue
        
        current_confidence = existing["confidence"]
        penalized_confidence = await belief_service._apply_unused_penalty(
            belief_hash, current_confidence, existing
        )
        
        if penalized_confidence != current_confidence:
            await belief_service._update_belief(
                belief_hash, penalized_confidence,
                json.loads(existing["derived_from"]),
                json.loads(existing["contradicted_by"]),
                now
            )


async def _measure_forgetting(
    storage: SqliteVecMemoryStorage,
    initial_beliefs: List[Dict[str, str]],
) -> float:
    """Measure taxa_forgetting: fraction of unused beliefs with confidence drop.
    
    Calls REAL production code (BeliefService._apply_unused_penalty) to apply the
    negative use-signal penalty. This ensures the eval measures the actual frente B
    behavior, not a simulation.
    
    Returns fraction in [0, 1].
    """
    if not initial_beliefs:
        return 0.0
    
    # Check if feedback is enabled
    use_feedback = os.environ.get("MCP_BELIEF_USE_FEEDBACK", "false").lower() == "true"
    if not use_feedback:
        return 0.0
    
    # Get belief hashes from content
    contents = [b["content"] for b in initial_beliefs]
    belief_hashes = _get_belief_hashes_from_contents(storage, contents)
    
    if not belief_hashes:
        return 0.0
    
    # Record initial confidences BEFORE applying penalty
    initial_confidences = _get_initial_confidences(storage, belief_hashes)
    
    # Create injection events and apply penalty using REAL production code
    now = datetime.now(timezone.utc)
    threshold = int(os.getenv("MCP_BELIEF_UNUSED_THRESHOLD", "3"))
    agent_id = "adversarial_eval_agent"
    
    await _create_unused_injection_events(storage, belief_hashes, threshold, agent_id, now)
    await _apply_penalty_to_beliefs(storage, belief_hashes, now)
    
    # Count how many beliefs had confidence drop
    dropped_count = _count_confidence_drops(storage, initial_confidences)
    
    return dropped_count / len(initial_confidences) if initial_confidences else 0.0


def _match_evidence_labels(results: List, qa_evidence: set) -> List[str]:
    """Match retrieved results to evidence labels."""
    retrieved_labels = []
    
    for result in results:
        tags = result.memory.tags or []
        matched_label = None
        
        for dia_id in qa_evidence:
            if f"dia:{dia_id}" in tags:
                matched_label = f"ev_{dia_id}"
                break
        
        if matched_label:
            retrieved_labels.append(matched_label)
        else:
            retrieved_labels.append(f"irrelevant_{len(retrieved_labels)}")
    
    return retrieved_labels


async def _measure_mrr_locomo_subset(storage: SqliteVecMemoryStorage) -> float:
    """Measure MRR using LoCoMo dataset subset.
    
    Reuses existing LoCoMo harness to get MRR comparable to baseline 0.4140.
    Dataset must be pre-cached offline (auto_download=False per R4).
    """
    try:
        from locomo_dataset import load_dataset
        from locomo_evaluator import mrr
        from benchmark_locomo import ingest_conversation
        
        # Load with auto_download=False to enforce offline operation (R4)
        conversations = load_dataset(data_path=None, auto_download=False)
        
        if not conversations:
            logger.warning("LoCoMo dataset not available offline, MRR will be 0.0")
            return 0.0
        
        # Use first conversation for quick eval
        conv = conversations[0]
        await ingest_conversation(storage, conv)
        
        # Evaluate on first few QA pairs
        total_mrr = 0.0
        count = 0
        
        for qa in conv.qa_pairs[:5]:  # Use first 5 QA pairs for speed
            results = await storage.retrieve(qa.question, n_results=10)
            
            # Match evidence labels
            relevant_labels = {f"ev_{dia_id}" for dia_id in qa.evidence}
            retrieved_labels = _match_evidence_labels(results, qa.evidence)
            
            total_mrr += mrr(retrieved_labels, relevant_labels)
            count += 1
        
        return total_mrr / count if count > 0 else 0.0
        
    except FileNotFoundError as e:
        logger.warning("LoCoMo dataset file not found (must be pre-cached): %s", e)
        return 0.0
    except ImportError as e:
        logger.warning("LoCoMo modules not available: %s", e)
        return 0.0


async def run_adversarial_eval(storage: SqliteVecMemoryStorage) -> Dict[str, float]:
    """Run adversarial evaluation measuring freshness, forgetting, and MRR.
    
    Args:
        storage: Initialized memory storage (may be empty or pre-populated)
        
    Returns:
        Dict with keys:
            - mrr: MRR score from LoCoMo subset (0.0 if not available)
            - taxa_freshness: fraction [0,1] of v1/v2 pairs where v2 ranks above v1
            - taxa_forgetting: fraction [0,1] of unused beliefs with confidence drop
    """
    # Get synthetic data
    versioned_pairs = _get_versioned_pairs()
    unused_beliefs = _get_unused_beliefs()
    
    # Always ingest adversarial data (self-contained eval)
    await _ingest_versioned_pairs(storage, versioned_pairs)
    await _ingest_unused_beliefs(storage, unused_beliefs)
    
    # Measure freshness
    taxa_freshness = await _measure_freshness(storage, versioned_pairs)
    
    # Measure forgetting
    taxa_forgetting = await _measure_forgetting(storage, unused_beliefs)
    
    # Measure MRR (LoCoMo subset)
    mrr_score = await _measure_mrr_locomo_subset(storage)
    
    return {
        "mrr": mrr_score,
        "taxa_freshness": taxa_freshness,
        "taxa_forgetting": taxa_forgetting,
    }


if __name__ == "__main__":
    # Standalone CLI for manual testing
    import tempfile
    import shutil
    from benchmark_locomo import create_isolated_storage
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s"
    )
    
    async def main():
        storage, tmp_dir = create_isolated_storage()
        await storage.initialize()
        
        try:
            result = await run_adversarial_eval(storage)
            
            print("\n" + "=" * 60)
            print("  Adversarial Evaluation Results")
            print("=" * 60)
            print(f"  MRR (LoCoMo subset):     {result['mrr']:.4f}")
            print(f"  Taxa Freshness:          {result['taxa_freshness']:.4f}")
            print(f"  Taxa Forgetting:         {result['taxa_forgetting']:.4f}")
            print("=" * 60 + "\n")
            
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    
    asyncio.run(main())
