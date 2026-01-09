"""Tool definitions and executors for multi-step RAG queries."""

from typing import Dict, Any, List, Optional
import logging
from sqlalchemy import or_

logger = logging.getLogger(__name__)


# Tool 1: Get Related Documents

def get_related_documents_tool() -> Dict[str, Any]:
    """Get related documents for a resolution (drafts, meetings, committee reports, agenda items)."""
    return {
        "type": "function",
        "name": "get_related_documents",
        "description": "Get all documents related to a resolution (drafts, meetings, committee reports, agenda items) by traversing document relationships. Use this to find meetings where a resolution was discussed. Returns lists of meeting symbols (e.g., A/78/PV.16), draft symbols (e.g., A/78/L.2), committee report symbols, and agenda item symbols.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Document symbol with slashes (resolution, draft, etc.), e.g., 'A/RES/78/220', 'A/78/L.2'"
                }
            },
            "required": ["symbol"]
        }
    }


def execute_get_related_documents(symbol: str) -> Dict[str, Any]:
    """
    Execute related documents lookup using SQL database.

    Traverses document_relationships table to find all related documents:
    - Drafts (relationship_type='draft_of')
    - Committee reports (relationship_type='committee_report_for')
    - Meetings (relationship_type='meeting_for')
    - Agenda items (relationship_type='agenda_item')

    Args:
        symbol: Document symbol (e.g., "A/RES/78/220")

    Returns:
        Dict with meetings, drafts, committee_reports, and agenda_items lists
    """
    from db.config import get_session
    from db.models import Document, DocumentRelationship
    from sqlalchemy import text

    session = get_session()
    try:
        logger.info(f"Getting related documents for {symbol}")

        # First, get the document ID
        doc = session.query(Document).filter(Document.symbol == symbol).first()
        if not doc:
            logger.warning(f"Document {symbol} not found in database")
            return {
                "symbol": symbol,
                "meetings": [],
                "drafts": [],
                "committee_reports": [],
                "agenda_items": [],
                "error": "Document not found"
            }

        # Query for related documents using recursive CTE
        # We traverse backwards (find documents that point TO this one)
        # and forwards (documents this one points TO)
        query = text("""
            WITH RECURSIVE related_docs AS (
                -- Base case: Start with the target document
                SELECT
                    id,
                    symbol,
                    doc_type,
                    CAST('self' AS VARCHAR) as relationship_type,
                    0 as depth
                FROM documents
                WHERE symbol = :symbol

                UNION ALL

                -- Recursive case: Find related documents in both directions
                SELECT
                    d.id,
                    d.symbol,
                    d.doc_type,
                    dr.relationship_type,
                    rd.depth + 1
                FROM related_docs rd
                JOIN document_relationships dr ON (
                    dr.target_id = rd.id OR dr.source_id = rd.id
                )
                JOIN documents d ON (
                    d.id = dr.source_id OR d.id = dr.target_id
                )
                WHERE rd.depth < 3  -- Limit depth to prevent infinite loops
                  AND d.id != rd.id  -- Don't include the same document twice
            )
            SELECT DISTINCT symbol, doc_type, relationship_type
            FROM related_docs
            WHERE relationship_type != 'self'
            ORDER BY doc_type, symbol;
        """)

        results = session.execute(query, {"symbol": symbol}).fetchall()

        # Group by relationship type and doc_type
        meetings = []
        drafts = []
        committee_reports = []
        agenda_items = []

        for row in results:
            doc_symbol = row[0]
            doc_type = row[1]
            rel_type = row[2]

            # Categorize by relationship type and doc_type
            if rel_type == "meeting_for" or doc_type == "meeting":
                if doc_symbol not in meetings:
                    meetings.append(doc_symbol)
            elif rel_type == "draft_of" or doc_type == "draft":
                if doc_symbol not in drafts:
                    drafts.append(doc_symbol)
            elif rel_type == "committee_report_for" or doc_type == "committee_report":
                if doc_symbol not in committee_reports:
                    committee_reports.append(doc_symbol)
            elif rel_type == "agenda_item" or doc_type == "agenda":
                if doc_symbol not in agenda_items:
                    agenda_items.append(doc_symbol)

        logger.info(f"Found {len(meetings)} meetings, {len(drafts)} drafts, "
                   f"{len(committee_reports)} committee reports, {len(agenda_items)} agenda items")

        return {
            "symbol": symbol,
            "meetings": meetings,
            "drafts": drafts,
            "committee_reports": committee_reports,
            "agenda_items": agenda_items
        }
    except Exception as e:
        logger.error(f"Error getting related documents for {symbol}: {e}", exc_info=True)
        return {
            "symbol": symbol,
            "meetings": [],
            "drafts": [],
            "committee_reports": [],
            "agenda_items": [],
            "error": str(e)
        }
    finally:
        session.close()


# Tool 2: Get Votes

def get_votes_tool() -> Dict[str, Any]:
    """Get voting records for a resolution."""
    return {
        "type": "function",
        "name": "get_votes",
        "description": "Get voting records showing which countries voted for, against, or abstained on a resolution. Returns votes grouped by type: 'in_favour', 'against', 'abstaining'.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Resolution symbol with slashes, e.g., 'A/RES/78/220'"
                },
                "vote_type": {
                    "type": "string",
                    "enum": ["in_favour", "against", "abstaining"],
                    "description": "Filter by vote type (optional). Use exact values: 'in_favour' (not 'yes'), 'against' (not 'no'), 'abstaining'"
                }
            },
            "required": ["symbol"]
        }
    }


def execute_get_votes(symbol: str, vote_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute vote query using database.

    Args:
        symbol: Resolution symbol
        vote_type: Optional filter by vote type ("in_favour", "against", "abstaining")

    Returns:
        Dict with votes grouped by type and total_countries count
    """
    from db.config import get_session
    from db.models import Document, Vote, Actor

    session = get_session()
    try:
        logger.info(f"Getting votes for {symbol}, type={vote_type}")

        query = session.query(Vote, Actor).join(
            Document, Vote.document_id == Document.id
        ).join(
            Actor, Vote.actor_id == Actor.id
        ).filter(Document.symbol == symbol)

        if vote_type:
            query = query.filter(Vote.vote_type == vote_type)

        results = query.all()

        votes_by_type = {}
        for vote, actor in results:
            vt = vote.vote_type
            if vt not in votes_by_type:
                votes_by_type[vt] = []
            votes_by_type[vt].append(actor.name)

        logger.info(f"Found {len(results)} votes")

        return {
            "symbol": symbol,
            "votes": votes_by_type,
            "total_countries": len(results)
        }
    except Exception as e:
        logger.error(f"Error getting votes for {symbol}: {e}")
        return {
            "symbol": symbol,
            "votes": {},
            "total_countries": 0,
            "error": str(e)
        }
    finally:
        session.close()


# Tool 3: Get Utterances

def get_utterances_tool() -> Dict[str, Any]:
    """Get statements from meetings."""
    return {
        "type": "function",
        "name": "get_utterances",
        "description": "Get statements/speeches made in UN meetings. Filter by meeting symbols and/or speaker countries. Returns utterances with speaker info, text, and agenda item context.",
        "parameters": {
            "type": "object",
            "properties": {
                "meeting_symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of meeting symbols with slashes, e.g., ['A/78/PV.80', 'A/78/PV.16']"
                },
                "speaker_countries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by speaker country names (optional), e.g., ['France', 'United States']"
                }
            },
            "required": ["meeting_symbols"]
        }
    }


def execute_get_utterances(
    meeting_symbols: List[str],
    speaker_countries: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Execute utterance query.

    Args:
        meeting_symbols: List of meeting symbols
        speaker_countries: Optional list of country names to filter by

    Returns:
        Dict with utterances list and count
    """
    from db.config import get_session
    from db.models import Document, Utterance

    session = get_session()
    try:
        logger.info(f"Getting utterances from {len(meeting_symbols)} meetings, "
                   f"countries={speaker_countries}")

        query = session.query(Utterance).join(
            Document, Utterance.meeting_id == Document.id
        ).filter(Document.symbol.in_(meeting_symbols))

        if speaker_countries:
            # ILIKE for case-insensitive partial match
            filters = [Utterance.speaker_affiliation.ilike(f"%{country}%")
                      for country in speaker_countries]
            query = query.filter(or_(*filters))

        utterances = query.order_by(Utterance.position_in_meeting).all()

        logger.info(f"Found {len(utterances)} utterances")

        return {
            "utterances": [
                {
                    "speaker_affiliation": u.speaker_affiliation,
                    "speaker_name": u.speaker_name,
                    "text": u.text[:500] if u.text else "",  # Truncate for context
                    "full_text": u.text,
                    "meeting": meeting_symbols,
                    "agenda_item": u.agenda_item_number
                }
                for u in utterances
            ],
            "count": len(utterances)
        }
    except Exception as e:
        logger.error(f"Error getting utterances: {e}")
        return {
            "utterances": [],
            "count": 0,
            "error": str(e)
        }
    finally:
        session.close()


# Tool 4: Answer With Evidence

def answer_with_evidence_tool() -> Dict[str, Any]:
    """Synthesize final answer from gathered evidence."""
    return {
        "type": "function",
        "name": "answer_with_evidence",
        "description": "Call this when you have gathered enough evidence to answer the question. This synthesizes the evidence into a final answer.",
        "parameters": {
            "type": "object",
            "properties": {
                "ready": {
                    "type": "boolean",
                    "description": "Set to true when ready to answer"
                }
            },
            "required": ["ready"]
        }
    }
