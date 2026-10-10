"""
RED tests for FRESHNESS in context injection - frente C (learning-loop).

Feature (spec-learning-loop-c-freshness.md): when the same fact exists in v1 (old updated_at) 
and v2 (new updated_at), both ACTIVE and relevant, memory_context should rank v2 ABOVE v1 
in the top-k with taxa_freshness=1.0. 

The implementation should:
1. Propagate updated_at (fallback created_at) from belief to scored item (context_injection.py:245-258)
2. Use recency as TIEBREAKER/boost in sort (context_injection.py:274) - freshness refines ties, 
   NEVER inverts materially higher relevance
3. Opt-in via MCP_INJECT_FRESHNESS flag (default on, off = byte-identical ordering)
4. Zero DDL route (timestamps already exist)

ALL tests are RED: the freshness feature does not exist yet, so assertions about
timestamp propagation, recency boosting, and ranking behavior will fail.
"""

import json
import os
import tempfile
import pytest
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

# Skip if sqlite-vec not available  
try:
    import sqlite_vec  # noqa: F401
    SQLITE_VEC_AVAILABLE = True
except ImportError:
    SQLITE_VEC_AVAILABLE = False

# Import the target module - will exist but freshness feature is not implemented yet
from mcp_memory_service.storage.context_injection import memory_context

if SQLITE_VEC_AVAILABLE:
    from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage

pytestmark = pytest.mark.skipif(not SQLITE_VEC_AVAILABLE, reason="sqlite-vec not available")


@pytest.fixture
async def real_storage():
    """Real storage with sqlite-vec for belief persistence and retrieval."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    
    storage = SqliteVecMemoryStorage(db_path)
    await storage.initialize()
    
    yield storage
    
    # Cleanup
    await storage.close()
    try:
        os.remove(db_path)
        os.rmdir(temp_dir)
    except (OSError, FileNotFoundError):
        pass


@pytest.fixture
async def storage_with_versioned_beliefs(real_storage):
    """Storage with two versions of the same fact at different timestamps."""
    from mcp_memory_service.consolidation.belief_service import BeliefService
    
    service = BeliefService(real_storage)
    
    # Create belief v1 (older - 2 days ago)
    old_time = (datetime.now() - timedelta(days=2)).isoformat()
    
    # Create belief v2 (newer - 1 hour ago)  
    new_time = (datetime.now() - timedelta(hours=1)).isoformat()
    
    # Insert beliefs directly into DB with controlled timestamps
    conn = real_storage.conn
    
    # Insert v1 (older version of the fact)
    conn.execute("""
        INSERT INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "belief_v1_hash", 
        "Python FastAPI uses async/await for concurrent request handling",
        0.85,  # same fact, same confidence — only updated_at differs (true tie)
        "active", 
        old_time,
        old_time,
        json.dumps(["mem1", "mem2"])
    ))
    
    # Insert v2 (newer version of the same fact)
    conn.execute("""
        INSERT INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "belief_v2_hash",
        "Python FastAPI uses async/await for concurrent request handling",
        0.85,  # same fact/content/confidence as v1 — freshness is the only differentiator
        "active",
        new_time, 
        new_time,
        json.dumps(["mem3", "mem4"])
    ))
    
    conn.commit()
    
    return real_storage


@pytest.mark.asyncio 
async def test_r1_freshness_timestamps_propagated_to_scored_items(storage_with_versioned_beliefs):
    """R1: Injection scorer SHALL propagate belief's updated_at into scored item."""
    
    task = "How does FastAPI handle concurrent requests"
    
    result = await memory_context(storage_with_versioned_beliefs, task, budget_tokens=1000)
    
    # Should have beliefs in response
    assert result["count"] > 0, "Should find relevant beliefs"
    assert len(result["items"]) > 0, "Should have items in result"
    
    # RED TEST: Each scored item should have timestamp fields propagated from belief
    for item in result["items"]:
        # These fields don't exist yet - feature not implemented
        assert "updated_at" in item, "Scored item should have updated_at field from belief"
        assert "created_at" in item, "Scored item should have created_at field from belief"
        assert item["updated_at"] is not None, "updated_at should not be None"


@pytest.mark.asyncio
async def test_r2_newer_version_wins_in_ranking(storage_with_versioned_beliefs):
    """R2: WHEN two beliefs are similarly relevant, newer updated_at should rank higher."""
    
    task = "FastAPI async concurrent request handling"
    
    result = await memory_context(storage_with_versioned_beliefs, task, budget_tokens=1000)
    
    # Should find both versions
    assert result["count"] >= 2, "Should find both versions of the fact"
    
    # Extract the two beliefs by their hashes
    belief_v1 = None
    belief_v2 = None
    
    for item in result["items"]:
        if item["belief_hash"] == "belief_v1_hash":
            belief_v1 = item
        elif item["belief_hash"] == "belief_v2_hash":
            belief_v2 = item
    
    assert belief_v1 is not None, "Should find v1 belief in results"
    assert belief_v2 is not None, "Should find v2 belief in results"
    
    # RED TEST: v2 (newer) should appear before v1 (older) in the ranked list
    v1_index = result["items"].index(belief_v1)
    v2_index = result["items"].index(belief_v2)
    
    assert v2_index < v1_index, "Newer version (v2) should rank higher than older version (v1)"


@pytest.mark.asyncio
async def test_r2_guard_freshness_does_not_invert_materially_higher_relevance(real_storage):
    """R2-GUARD: Materially more relevant older belief should NOT be demoted below irrelevant newer."""
    
    from mcp_memory_service.consolidation.belief_service import BeliefService
    
    # Create beliefs with clear relevance difference
    old_time = (datetime.now() - timedelta(days=5)).isoformat() 
    new_time = (datetime.now() - timedelta(hours=1)).isoformat()
    
    conn = real_storage.conn
    
    # Highly relevant older belief
    conn.execute("""
        INSERT INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "highly_relevant_old",
        "Machine learning models require extensive training data and computational resources for optimal performance",
        0.92,  # High confidence
        "active",
        old_time,
        old_time, 
        json.dumps(["mem1"])
    ))
    
    # Irrelevant newer belief  
    conn.execute("""
        INSERT INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "irrelevant_new", 
        "The weather today is sunny with occasional clouds",
        0.75,  # Lower confidence and irrelevant topic
        "active",
        new_time,
        new_time,
        json.dumps(["mem2"])
    ))
    
    conn.commit()
    
    task = "machine learning model training requirements"
    
    result = await memory_context(real_storage, task, budget_tokens=1000)
    
    # Find the beliefs
    relevant_old = None
    irrelevant_new = None
    
    for item in result["items"]:
        if item["belief_hash"] == "highly_relevant_old":
            relevant_old = item
        elif item["belief_hash"] == "irrelevant_new":
            irrelevant_new = item
    
    if relevant_old and irrelevant_new:
        # RED TEST: Freshness should NOT invert materially higher relevance
        old_index = result["items"].index(relevant_old) 
        new_index = result["items"].index(irrelevant_new)
        
        assert old_index < new_index, "Highly relevant older belief should still rank above irrelevant newer one"



@pytest.mark.asyncio
async def test_r2_guard_moderate_relevance_gap_not_inverted(real_storage):
    """R2-GUARD (moderate gap): two beliefs BOTH relevant to the theme, with a
    relevance*confidence gap above the 0.1 freshness cap. The more-relevant OLDER
    belief must still win — freshness (<=0.1) refines ties, it does not invert a
    materially higher relevance. This is the band the 0.0-relevance guard missed."""
    import os
    os.environ["MCP_INJECT_FRESHNESS"] = "true"
    from datetime import datetime, timedelta
    old_time = (datetime.now() - timedelta(days=10)).isoformat()
    new_time = (datetime.now() - timedelta(minutes=5)).isoformat()
    conn = real_storage.conn
    # Both about the SAME theme; old one clearly more on-point (higher relevance),
    # new one on-topic but weaker. Gap engineered to exceed the 0.1 cap.
    # Calibrated so the relevance*confidence gap lands in the CRITICAL band (~0.11-0.20,
    # just above the 0.1 freshness cap): old rc~0.547, new rc~0.370, gap ~0.177. With the
    # old (regressed) 0.3 cap the newer would win (0.370+0.273>0.547) → this test would
    # catch that regression. With the 0.1 cap the more-relevant OLDER belief holds.
    conn.execute(
        "INSERT INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from) VALUES (?,?,?,?,?,?,?)",
        ("more_relevant_old", "alpha beta gamma delta extra one",
         0.82, "active", old_time, old_time, json.dumps(["m1"])),
    )
    conn.execute(
        "INSERT INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from) VALUES (?,?,?,?,?,?,?)",
        ("less_relevant_new", "alpha beta gamma other two three",
         0.74, "active", new_time, new_time, json.dumps(["m2"])),
    )
    conn.commit()
    result = await memory_context(real_storage, "alpha beta gamma delta epsilon zeta", budget_tokens=1000)
    items = result["items"]
    old_i = next((i for i, it in enumerate(items) if it["belief_hash"] == "more_relevant_old"), None)
    new_i = next((i for i, it in enumerate(items) if it["belief_hash"] == "less_relevant_new"), None)
    assert old_i is not None and new_i is not None, "both beliefs must be present"
    assert old_i < new_i, (
        "more-relevant OLDER belief must outrank less-relevant NEWER one; "
        "freshness cap (0.1) must not invert a materially higher relevance"
    )


def test_freshness_boost_future_timestamp_is_capped_no_crash():
    """A future updated_at (clock skew across the 3 hosts + VPS) must NOT exceed the
    0.1 cap nor raise — it is clamped to 'now' (full capped boost). Guards the HIGH
    that an unbounded future decay would invert relevance (R2) / OverflowError-crash."""
    from datetime import datetime, timedelta, timezone
    from mcp_memory_service.storage.context_injection import _calculate_freshness_boost
    for delta in (timedelta(days=1), timedelta(days=10), timedelta(days=3650)):
        future = (datetime.now(timezone.utc) + delta).isoformat()
        boost = _calculate_freshness_boost(future)
        assert 0.0 <= boost <= 0.1, f"future stamp must stay within [0,0.1], got {boost}"
@pytest.mark.asyncio
async def test_r4_mcp_inject_freshness_flag_off_byte_identical_ordering(storage_with_versioned_beliefs):
    """R4: MCP_INJECT_FRESHNESS off should produce byte-identical ordering to current behavior."""
    
    task = "FastAPI async concurrent request handling"  # Match test_r2 for consistent relevance
    
    # Get result with freshness OFF (should be current behavior)
    with patch.dict(os.environ, {"MCP_INJECT_FRESHNESS": "false"}):
        result_off = await memory_context(storage_with_versioned_beliefs, task, budget_tokens=1000)
    
    # Get result with freshness ON (new behavior) 
    with patch.dict(os.environ, {"MCP_INJECT_FRESHNESS": "true"}):
        result_on = await memory_context(storage_with_versioned_beliefs, task, budget_tokens=1000)
    
    # RED TEST: When flag is off, should be identical to current sort behavior
    # (This fails because current code doesn't check the flag at all)
    
    if result_off["count"] > 1 and result_on["count"] > 1:
        # Extract just the belief hashes in order for comparison
        hashes_off = [item["belief_hash"] for item in result_off["items"]]
        hashes_on = [item["belief_hash"] for item in result_on["items"]]
        
        # When freshness is ON and there are version conflicts, ordering should differ
        # When freshness is OFF, should match current behavior exactly
        if "belief_v1_hash" in hashes_off and "belief_v2_hash" in hashes_off:
            # With freshness ON, v2 (newer) should rank higher than v1 (older)
            v1_idx_on = hashes_on.index("belief_v1_hash")
            v2_idx_on = hashes_on.index("belief_v2_hash")
            
            # With freshness OFF, should use pure relevance*confidence ordering
            # v1 has higher confidence (0.85 vs 0.82), so should rank first when freshness is off
            v1_idx_off = hashes_off.index("belief_v1_hash")
            v2_idx_off = hashes_off.index("belief_v2_hash")
            
            # Verify the behaviors differ appropriately
            assert v2_idx_on < v1_idx_on, "With freshness ON, v2 (newer) should rank higher"
            assert v1_idx_off < v2_idx_off, "With freshness OFF, v1 (higher confidence) should rank higher"
            

@pytest.mark.asyncio
async def test_r5_no_schema_migration_required(real_storage):
    """R5: Freshness feature should work without schema changes (timestamps already exist)."""
    
    # Verify beliefs table already has the required timestamp columns
    conn = real_storage.conn
    cursor = conn.execute("PRAGMA table_info(beliefs)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}  # name -> type mapping
    
    assert "created_at" in columns, "beliefs table should already have created_at column"
    assert "updated_at" in columns, "beliefs table should already have updated_at column"
    
    # RED TEST: The feature should use existing columns, no new ones needed
    # This test passes for the schema part but will fail when we check that the feature uses them


@pytest.mark.asyncio
async def test_freshness_boost_calculation_contract(storage_with_versioned_beliefs):
    """Test the contract for how freshness boost should be calculated and applied."""
    
    task = "FastAPI async patterns"
    
    # This test exercises the expected contract that the implementer (reg) needs to follow
    result = await memory_context(storage_with_versioned_beliefs, task, budget_tokens=1000)
    
    # RED TEST: The implementation should include freshness score in item metadata for debugging
    for item in result["items"]:
        # These diagnostic fields don't exist yet
        assert "freshness_score" in item, "Item should include freshness_score for debugging"
        assert isinstance(item["freshness_score"], (int, float)), "freshness_score should be numeric"
        
        # Should preserve original relevance and confidence
        assert "relevance" in item, "Original relevance should be preserved"
        assert "confidence" in item, "Original confidence should be preserved"


# Contract for the implementer (reg):
"""
EXPECTED CONTRACT for implementation in context_injection.py:

1. In the scored item creation loop (around line 245-258):
   - Add "updated_at": b.get("updated_at", b.get("created_at")) to each scored dict
   - Add "created_at": b.get("created_at") to each scored dict

2. In the sort call (line 274):
   - Check os.environ.get("MCP_INJECT_FRESHNESS", "true").lower() != "false"
   - If freshness enabled, modify sort key to include recency boost
   - Suggested approach: 
     * Calculate recency_boost from updated_at (newer = higher score, bounded)
     * Use compound key: (relevance * confidence + limited_recency_boost, confidence, recency_boost)
   - If freshness disabled, use exact current key: (relevance * confidence, confidence)

3. Freshness boost calculation should be:
   - Bounded (e.g., max 0.1 boost to avoid inverting major relevance differences)
   - Monotonic with recency (newer always >= older)
   - Deterministic tiebreaker when times are equal

4. Optional: Add freshness_score to scored items for debugging/telemetry

The tests above verify these behaviors end-to-end through the real memory_context flow.
"""