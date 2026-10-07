"""
Delta-sync Phase 4b: pull orchestration (sync_from_peer).

Orchestrates the complete pull flow: cursor → get_events_since → apply → advance cursor.
Operates over a local MemoryStorage and a peer adapter (RemoteHTTPStorage or test adapter).

ADR-0023: Separate from hybrid sync loop (no fusion with state-based sync)
ADR-0026: Manual invocation first (no scheduler)
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol, Tuple

from ..base import MemoryStorage
from .apply import apply_remote_event, advance_sync_cursor

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of sync_from_peer operation."""
    events_applied: int
    pages_processed: int
    final_cursor: int
    events_failed: int = 0


class PeerAdapter(Protocol):
    """Protocol for peer adapters (RemoteHTTPStorage or test adapter)."""
    
    async def get_events_since(self, since_seq: int, limit: int) -> Tuple[List[Dict[str, Any]], int, bool]:
        """
        Get events from peer since given sequence number.
        
        Returns: (events, next_seq, has_more)
        """
        ...


async def sync_from_peer(
    local_storage: MemoryStorage, 
    peer: PeerAdapter, 
    peer_id: str, 
    limit: int = 100
) -> SyncResult:
    """
    Orchestrate pulling and applying events from a peer.
    
    Implements the complete pull flow:
    1. Read current sync cursor (default 0 if not exists)
    2. Loop: get_events_since → apply_remote_event → advance_sync_cursor
    3. Continue until has_more is false
    4. Return summary result
    
    Args:
        local_storage: Local memory storage instance
        peer: Peer adapter implementing get_events_since
        peer_id: Unique identifier for the peer
        limit: Maximum events per page (default 100)
        
    Returns:
        SyncResult with events_applied, pages_processed, and final_cursor
    """
    logger.info(f"Starting sync from peer {peer_id}")
    
    # Step 1: Read current cursor (default to 0 if not exists)
    cursor_result = local_storage.conn.execute(
        "SELECT last_seq_seen FROM sync_cursor WHERE peer_id = ?",
        (peer_id,)
    ).fetchone()
    
    cursor = cursor_result[0] if cursor_result else 0
    initial_cursor = cursor
    
    logger.debug(f"Starting sync from cursor {cursor}")
    
    # Initialize result counters
    events_applied = 0
    pages_processed = 0
    events_failed = 0
    
    # Step 2: Loop through pages until no more events
    while True:
        logger.debug(f"Fetching events since seq {cursor} with limit {limit}")
        
        # Get events from peer
        try:
            events, next_seq, has_more = await peer.get_events_since(cursor, limit)
        except Exception as e:
            logger.error(f"Failed to get events from peer {peer_id}: {e}")
            raise
        
        # If no events returned, we're done
        if not events:
            logger.debug("No more events to process")
            break
            
        pages_processed += 1
        logger.debug(f"Processing page {pages_processed} with {len(events)} events")

        # Step 3: Apply each event in the page. FAIL-STOP (§8.5): on the first event
        # that fails to apply, stop and advance the cursor ONLY to the last event that
        # applied successfully — never past an unapplied event, or it would be lost
        # permanently (re-sync starts after the cursor).
        last_good_seq = cursor
        page_failed = False
        for event in events:
            event_seq = event.get("seq")
            try:
                result = apply_remote_event(local_storage, event)
            except Exception as e:
                logger.error(f"Error applying event {event.get('event_id', 'unknown')} (seq={event_seq}): {e}")
                events_failed += 1
                page_failed = True
                break
            if result.applied:
                events_applied += 1
                if event_seq is not None:
                    last_good_seq = event_seq
                logger.debug(f"Applied event {event.get('event_id', 'unknown')}: {result.reason}")
            else:
                # applied=False means the event was not accepted (not a benign dup).
                logger.warning(f"Event {event.get('event_id', 'unknown')} (seq={event_seq}) not applied: {result.reason}")
                events_failed += 1
                page_failed = True
                break

        # Step 4: Advance cursor to the last successfully applied seq (durably). On a
        # partial-failure page this is < next_seq, so the failed event is re-pulled next
        # time; on a clean page last_good_seq == next_seq.
        advance_target = last_good_seq if page_failed else next_seq
        try:
            advance_sync_cursor(local_storage, peer_id, advance_target)
            cursor = advance_target
            logger.debug(f"Advanced cursor to {cursor}")
        except Exception as e:
            logger.error(f"Failed to advance cursor for peer {peer_id}: {e}")
            raise

        # Step 5: Stop on partial failure (do not silently skip the failed event) or when
        # the feed is exhausted.
        if page_failed:
            logger.warning(f"Stopping sync from {peer_id} at seq {cursor} due to apply failure")
            break
        if not has_more:
            logger.debug("No more pages available")
            break
    
    final_cursor = cursor
    logger.info(
        f"Completed sync from peer {peer_id}: "
        f"{events_applied} events applied, "
        f"{pages_processed} pages processed, "
        f"cursor: {initial_cursor} → {final_cursor}"
    )
    
    return SyncResult(
        events_applied=events_applied,
        pages_processed=pages_processed,
        final_cursor=final_cursor,
        events_failed=events_failed
    )