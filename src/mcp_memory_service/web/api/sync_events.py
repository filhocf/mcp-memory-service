"""
Sync Events API endpoint for delta-sync Phase 4a.

Provides GET /api/sync/events for pulling event feed with pagination.
Implements ADR-0020 (pagination by seq) and ADR-0021 (enriched create events).
"""

import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query, Depends, HTTPException
from pydantic import BaseModel

from ...storage.base import MemoryStorage
from ..dependencies import get_storage
from ..oauth.middleware import require_read_access

logger = logging.getLogger(__name__)

router = APIRouter()


class SyncEventData(BaseModel):
    """Individual sync event in the feed response."""
    seq: int
    event_id: str
    op: str
    content_hash: str
    agent_id: Optional[str]
    hlc_physical: int
    hlc_logical: int
    embedding_model: Optional[str]
    embedding_dim: Optional[int]
    payload: Dict[str, Any]


class SyncEventsResponse(BaseModel):
    """Response for GET /api/sync/events endpoint."""
    events: List[SyncEventData]
    next_seq: int
    has_more: bool


@router.get("/sync/events", response_model=SyncEventsResponse)
async def get_sync_events(
    since_seq: int = Query(0, description="Return events with seq > since_seq"),
    limit: int = Query(100, description="Maximum number of events to return", le=1000),
    _auth: bool = Depends(require_read_access),
    storage: MemoryStorage = Depends(get_storage),
) -> SyncEventsResponse:
    """
    Get sync events feed for delta-sync pull.
    
    Returns events with seq > since_seq, ordered by seq.
    Create events are enriched with content from memories table if available.
    
    Args:
        since_seq: Return events with seq greater than this value
        limit: Maximum events to return (capped at 1000)
        
    Returns:
        SyncEventsResponse with events, next_seq, and has_more flag
    """
    try:
        # Validate parameters
        if limit <= 0:
            raise HTTPException(status_code=400, detail="limit must be positive")
        if limit > 1000:
            limit = 1000
            
        # Get events from sync_events table
        cursor = storage.conn.execute("""
            SELECT 
                seq, event_id, op, content_hash, agent_id, hlc_physical, hlc_logical,
                embedding_model, embedding_dim, payload
            FROM sync_events 
            WHERE seq > ?
            ORDER BY seq 
            LIMIT ?
        """, (since_seq, limit))
        
        rows = cursor.fetchall()
        events = []
        
        for row in rows:
            seq, event_id, op, content_hash, agent_id, hlc_physical, hlc_logical, embedding_model, embedding_dim, payload = row
            
            # Parse payload JSON
            payload_dict = json.loads(payload) if payload else {}
            
            # For create events, enrich with content from memories table if available
            if op == "create":
                memory_cursor = storage.conn.execute(
                    "SELECT content FROM memories WHERE content_hash = ? AND deleted_at IS NULL",
                    (content_hash,)
                )
                memory_row = memory_cursor.fetchone()
                if memory_row:
                    payload_dict["content"] = memory_row[0]
            
            events.append(SyncEventData(
                seq=seq,
                event_id=event_id,
                op=op,
                content_hash=content_hash,
                agent_id=agent_id,
                hlc_physical=hlc_physical,
                hlc_logical=hlc_logical,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                payload=payload_dict
            ))
        
        # Determine next_seq and has_more
        if events:
            next_seq = events[-1].seq
        else:
            next_seq = since_seq
            
        # Check if there are more events beyond what we returned
        has_more = False
        if events and len(events) == limit:
            # Check if there's at least one more event beyond our result
            check_cursor = storage.conn.execute(
                "SELECT 1 FROM sync_events WHERE seq > ? LIMIT 1",
                (next_seq,)
            )
            has_more = check_cursor.fetchone() is not None
        
        return SyncEventsResponse(
            events=events,
            next_seq=next_seq,
            has_more=has_more
        )
        
    except Exception as e:
        logger.error(f"Error retrieving sync events: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")