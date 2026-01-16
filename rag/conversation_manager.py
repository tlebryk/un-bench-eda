"""
Conversation state management for multi-turn RAG queries.

Phase 1: In-memory storage (simple dict with thread safety)
Phase 2: Redis/database persistence (future)
"""

from typing import Dict, Optional, Set, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import secrets
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class SimpleTurn:
    """
    Represents a single turn in a Simple RAG conversation.
    """
    turn_number: int
    timestamp: datetime
    question: str
    sql_query: Optional[str]
    query_results: Dict[str, Any]
    answer: str
    evidence: List[Dict[str, Any]]
    sources: List[str]


@dataclass
class ConversationSession:
    """
    Represents a multi-turn conversation session.

    Attributes:
        conversation_id: Unique identifier (e.g., "conv_abc123")
        created_at: When conversation was created
        last_accessed: When conversation was last used
        rag_type: Type of RAG ("simple" or "multistep")
        simple_turns: History of Simple RAG turns
        multistep_input_list: Full OpenAI input_list for multi-step agent
        accumulated_evidence: Evidence accumulated across multi-step turns
        active_symbols: Set of document symbols referenced (e.g., {"A/RES/78/220"})
        total_turns: Total number of turns in conversation
    """
    conversation_id: str
    created_at: datetime
    last_accessed: datetime
    rag_type: str  # "simple" or "multistep"

    # Simple RAG history
    simple_turns: List[SimpleTurn] = field(default_factory=list)

    # Multi-step history
    multistep_input_list: List[Dict[str, Any]] = field(default_factory=list)
    accumulated_evidence: Dict[str, List[Any]] = field(default_factory=dict)

    # Metadata
    active_symbols: Set[str] = field(default_factory=set)
    total_turns: int = 0


# Thread-safe conversation store
_conversations_lock = threading.Lock()
_conversations: Dict[str, ConversationSession] = {}


def create_conversation_id() -> str:
    """
    Generate unique conversation ID.

    Returns:
        String in format "conv_{random_urlsafe_string}"
    """
    return f"conv_{secrets.token_urlsafe(16)}"


def get_conversation(conversation_id: str) -> Optional[ConversationSession]:
    """
    Get conversation by ID and update last_accessed timestamp.

    Args:
        conversation_id: Conversation identifier

    Returns:
        ConversationSession if found, None otherwise
    """
    with _conversations_lock:
        conv = _conversations.get(conversation_id)
        if conv:
            conv.last_accessed = datetime.utcnow()
            logger.info(f"Retrieved conversation {conversation_id} (rag_type={conv.rag_type}, turns={conv.total_turns})")
        else:
            logger.warning(f"Conversation {conversation_id} not found")
        return conv


def create_conversation(rag_type: str) -> ConversationSession:
    """
    Create new conversation session.

    Args:
        rag_type: Type of RAG ("simple" or "multistep")

    Returns:
        Newly created ConversationSession
    """
    if rag_type not in ("simple", "multistep"):
        raise ValueError(f"Invalid rag_type: {rag_type}. Must be 'simple' or 'multistep'")

    conv_id = create_conversation_id()
    session = ConversationSession(
        conversation_id=conv_id,
        created_at=datetime.utcnow(),
        last_accessed=datetime.utcnow(),
        rag_type=rag_type
    )

    with _conversations_lock:
        _conversations[conv_id] = session

    logger.info(f"Created new conversation {conv_id} (rag_type={rag_type})")
    return session


def save_simple_turn(
    conversation_id: str,
    turn: SimpleTurn,
    new_symbols: Set[str]
) -> None:
    """
    Save a simple RAG turn to conversation.

    Note: Both "simple" and "multistep" conversations can store simple_turns.
    Multistep conversations use simple_turns when running in fast mode.

    Args:
        conversation_id: Conversation identifier
        turn: SimpleTurn to save
        new_symbols: New document symbols from this turn
    """
    conv = get_conversation(conversation_id)
    if not conv:
        logger.error(f"Cannot save turn: conversation {conversation_id} not found")
        return

    with _conversations_lock:
        conv.simple_turns.append(turn)
        conv.active_symbols.update(new_symbols)
        conv.total_turns += 1

    logger.info(
        f"Saved turn {turn.turn_number} to conversation {conversation_id} (type={conv.rag_type}) "
        f"(sources={len(turn.sources)}, new_symbols={len(new_symbols)})"
    )


def save_multistep_state(
    conversation_id: str,
    input_list: List[Dict[str, Any]],
    accumulated_evidence: Dict[str, List[Any]],
    new_symbols: Set[str]
) -> None:
    """
    Save multi-step orchestrator state.

    Args:
        conversation_id: Conversation identifier
        input_list: Full OpenAI input_list (conversation history)
        accumulated_evidence: Evidence accumulated from tool calls
        new_symbols: New document symbols from this turn
    """
    conv = get_conversation(conversation_id)
    if not conv:
        logger.error(f"Cannot save state: conversation {conversation_id} not found")
        return

    if conv.rag_type != "multistep":
        logger.error(f"Cannot save multistep state to {conv.rag_type} conversation")
        return

    with _conversations_lock:
        conv.multistep_input_list = input_list
        conv.accumulated_evidence = accumulated_evidence
        conv.active_symbols.update(new_symbols)
        conv.total_turns += 1

    logger.info(
        f"Saved multistep state for conversation {conversation_id} "
        f"(input_list_length={len(input_list)}, evidence_keys={list(accumulated_evidence.keys())}, "
        f"new_symbols={len(new_symbols)})"
    )


def cleanup_old_conversations(max_age_hours: int = 24) -> int:
    """
    Remove stale conversations older than max_age_hours.

    Args:
        max_age_hours: Maximum age in hours before cleanup

    Returns:
        Number of conversations removed
    """
    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

    with _conversations_lock:
        to_remove = [
            cid for cid, conv in _conversations.items()
            if conv.last_accessed < cutoff
        ]

        for cid in to_remove:
            del _conversations[cid]

    if to_remove:
        logger.info(f"Cleaned up {len(to_remove)} old conversations (max_age={max_age_hours}h)")
    else:
        logger.debug(f"No conversations to clean up (max_age={max_age_hours}h)")

    return len(to_remove)


def get_conversation_stats() -> Dict[str, Any]:
    """
    Get statistics about current conversations.

    Returns:
        Dictionary with conversation stats
    """
    with _conversations_lock:
        total = len(_conversations)
        simple_count = sum(1 for c in _conversations.values() if c.rag_type == "simple")
        multistep_count = sum(1 for c in _conversations.values() if c.rag_type == "multistep")

        if total > 0:
            avg_turns = sum(c.total_turns for c in _conversations.values()) / total
            oldest = min(c.created_at for c in _conversations.values())
            newest = max(c.created_at for c in _conversations.values())
        else:
            avg_turns = 0
            oldest = None
            newest = None

    return {
        "total_conversations": total,
        "simple_rag_conversations": simple_count,
        "multistep_conversations": multistep_count,
        "average_turns_per_conversation": avg_turns,
        "oldest_conversation": oldest.isoformat() if oldest else None,
        "newest_conversation": newest.isoformat() if newest else None,
    }


def clear_all_conversations() -> int:
    """
    Clear all conversations (useful for testing).

    Returns:
        Number of conversations cleared
    """
    with _conversations_lock:
        count = len(_conversations)
        _conversations.clear()

    logger.warning(f"Cleared all {count} conversations")
    return count
