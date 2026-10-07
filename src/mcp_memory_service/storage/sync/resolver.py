"""Delta-sync resolver: deterministic conflict resolution for concurrent events.

This module provides pure functions (no I/O, no network) for resolving conflicts
between concurrent events for the same content_hash. Implements ADR-0012/0013.

The resolver uses a strict ordering hierarchy:
1. HLC (Hybrid Logical Clock) ordering - later wins
2. Delete-vs-update semantics - delete wins on equal HLC  
3. Quality score - higher wins on exact HLC tie
4. Agent ID and event ID - deterministic final tie-break

All functions are deterministic and commutative: resolve(a,b) == resolve(b,a).
"""

from dataclasses import dataclass
from typing import Optional, Iterable
import functools


@dataclass(frozen=True)
class EventView:
    """Immutable view of a sync event for conflict resolution.
    
    This represents the minimal data needed for the resolver to make decisions.
    The resolver operates on EventView instances, not database rows.
    """
    hlc_physical: int       # Physical time component of HLC (epoch milliseconds)
    hlc_logical: int        # Logical counter component of HLC
    agent_id: Optional[str] # Agent that created this event (None for legacy/unattributed)
    event_id: str          # Unique event identifier (UUID)
    op: str                # Operation type ('create', 'delete', 'update_metadata')
    content_hash: str      # Hash of the content being modified
    quality_score: float = 0.5  # Importance/quality metric (0.0-1.0, default 0.5)


def resolve(a: EventView, b: EventView) -> EventView:
    """Resolve conflict between two concurrent events for the same content_hash.
    
    This is a pure function that implements the deterministic ordering rules
    from ADR-0012/0013. The function is commutative: resolve(a,b) == resolve(b,a).
    
    Ordering hierarchy:
    1. HLC ordering - (hlc_physical, hlc_logical) tuple, higher wins
    2. Delete-vs-update - on equal HLC, delete wins over update/create  
    3. Quality score - on exact HLC tie, higher quality_score wins
    4. Agent/event ID - final deterministic tie-break, smaller wins
    
    Args:
        a: First event
        b: Second event
        
    Returns:
        The winning event (either a or b)
    """
    # Step 1: HLC (Hybrid Logical Clock) ordering - ADR-0010
    # Compare (physical, logical) as tuple - later wins
    hlc_a = (a.hlc_physical, a.hlc_logical)
    hlc_b = (b.hlc_physical, b.hlc_logical)
    
    if hlc_a > hlc_b:
        return a
    elif hlc_b > hlc_a:
        return b
    
    # Step 2: Equal HLC - apply delete-vs-update rule (ADR-0012)
    # Delete wins over update/create when HLC is exactly equal
    if a.op == 'delete' and b.op in ('create', 'update', 'update_metadata'):
        return a
    elif b.op == 'delete' and a.op in ('create', 'update', 'update_metadata'):
        return b
    
    # Step 3: Equal HLC, compatible ops - use quality score (ADR-0013)  
    # Higher quality wins on exact logical tie
    if a.quality_score > b.quality_score:
        return a
    elif b.quality_score > a.quality_score:
        return b
    
    # Step 4: Total tie - deterministic final tie-break
    # Use agent_id (None sorts last), then event_id lexicographically
    # Smaller (earlier) values win to ensure determinism
    
    # Handle None agent_id - None sorts after any string value
    if a.agent_id is None and b.agent_id is not None:
        return b  # b wins (non-None agent_id)
    elif b.agent_id is None and a.agent_id is not None:
        return a  # a wins (non-None agent_id)
    elif a.agent_id != b.agent_id:
        # Both non-None or both None, compare directly
        if (a.agent_id or "") < (b.agent_id or ""):
            return a
        else:
            return b
    
    # Same agent_id, compare event_id
    if a.event_id != b.event_id:
        return a if a.event_id < b.event_id else b

    # Same event_id too: break by op in a canonical, commutative order so that
    # resolve(a, b) == resolve(b, a) even when the two differ only by op.
    if a.op != b.op:
        return a if a.op < b.op else b

    # Fully identical on every ordering key: the events are equivalent. Return a
    # deterministic, commutative choice (they carry the same ordering identity).
    return a if (a.content_hash, a.quality_score) <= (b.content_hash, b.quality_score) else b


def reduce_events(events: Iterable[EventView]) -> Optional[EventView]:
    """Reduce a collection of events to the single winner using resolve().
    
    This applies the resolve() function across all events to find the ultimate
    winner. The order of iteration doesn't matter due to resolve's commutativity.
    
    Args:
        events: Iterable of EventView instances
        
    Returns:
        The winning event, or None if the input is empty
        
    Raises:
        ValueError: If the input iterable is empty
    """
    events_list = list(events)
    
    if not events_list:
        return None
        
    if len(events_list) == 1:
        return events_list[0]
    
    # Use functools.reduce to apply resolve() across all events
    # The commutativity of resolve() ensures consistent results regardless of order
    return functools.reduce(resolve, events_list)