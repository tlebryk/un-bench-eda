"""Tool definitions and executors for multi-step RAG queries."""

from typing import Dict, Any, List, Optional
import logging
from sqlalchemy import or_, text

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
    - Meetings (relationship_type='meeting_record_for')
    - Agenda items (relationship_type='agenda_item_for')

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
            if rel_type == "meeting_record_for" or doc_type in {"meeting", "committee_meeting"}:
                if doc_symbol not in meetings:
                    meetings.append(doc_symbol)
            elif rel_type == "draft_of" or doc_type == "draft":
                if doc_symbol not in drafts:
                    drafts.append(doc_symbol)
            elif rel_type == "committee_report_for" or doc_type == "committee_report":
                if doc_symbol not in committee_reports:
                    committee_reports.append(doc_symbol)
            elif rel_type == "agenda_item_for" or doc_type in {"agenda", "agenda_item"}:
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
        "description": "Get voting records showing which countries voted for, against, or abstained. Filter by document symbol and/or vote_event_id. Returns votes grouped by type: 'in_favour', 'against', 'abstaining'.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Resolution symbol with slashes, e.g., 'A/RES/78/220'"
                },
                "vote_event_id": {
                    "type": "integer",
                    "description": "Filter by a specific vote event ID (optional), e.g., for procedural votes or amendments"
                },
                "vote_type": {
                    "type": "string",
                    "enum": ["in_favour", "against", "abstaining"],
                    "description": "Filter by vote type (optional). Use exact values: 'in_favour' (not 'yes'), 'against' (not 'no'), 'abstaining'"
                }
            },
            "required": []
        }
    }


def execute_get_votes(
    symbol: Optional[str] = None,
    vote_type: Optional[str] = None,
    vote_event_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Execute vote query using database.

    Args:
        symbol: Resolution symbol
        vote_type: Optional filter by vote type ("in_favour", "against", "abstaining")
        vote_event_id: Optional filter by vote event ID

    Returns:
        Dict with votes grouped by type and total_countries count
    """
    from db.config import get_session
    from db.models import Document, Vote, Actor

    session = get_session()
    try:
        if not symbol and not vote_event_id:
            return {
                "symbol": symbol,
                "votes": {},
                "total_countries": 0,
                "error": "Provide at least one of: symbol or vote_event_id"
            }

        logger.info(f"Getting votes for {symbol}, type={vote_type}, event_id={vote_event_id}")

        query = session.query(Vote, Actor).join(
            Actor, Vote.actor_id == Actor.id
        )

        if symbol:
            query = query.join(
                Document, Vote.document_id == Document.id
            ).filter(Document.symbol == symbol)

        if vote_type:
            query = query.filter(Vote.vote_type == vote_type)

        if vote_event_id:
            query = query.filter(Vote.vote_event_id == vote_event_id)

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


# Tool 3: Get Vote Events

def get_vote_events_tool() -> Dict[str, Any]:
    """Get vote events (adoption, amendment, motions) for meetings or documents."""
    return {
        "type": "function",
        "name": "get_vote_events",
        "description": "Get vote events (adoption, amendment, motion for division) with optional rollup vote counts. Filter by target document symbol and/or meeting symbols.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Target document symbol (resolution/draft) to filter vote events (optional)"
                },
                "meeting_symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of meeting symbols to filter vote events (optional)"
                },
                "event_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by event types (optional): ['adoption', 'vote_on_amendment', 'motion_for_division']"
                },
                "include_vote_tallies": {
                    "type": "boolean",
                    "description": "Include per-event vote counts grouped by vote_type"
                }
            },
            "required": []
        }
    }


def execute_get_vote_events(
    symbol: Optional[str] = None,
    meeting_symbols: Optional[List[str]] = None,
    event_types: Optional[List[str]] = None,
    include_vote_tallies: bool = False
) -> Dict[str, Any]:
    """
    Execute vote event query.

    Args:
        symbol: Optional target document symbol
        meeting_symbols: Optional list of meeting symbols
        event_types: Optional list of event types to filter
        include_vote_tallies: Include per-event vote counts

    Returns:
        Dict with vote events and count
    """
    from db.config import get_session

    if not symbol and not meeting_symbols:
        return {
            "events": [],
            "count": 0,
            "error": "Provide at least one of: symbol or meeting_symbols"
        }

    session = get_session()
    try:
        logger.info(
            "Getting vote events for symbol=%s, meetings=%s, event_types=%s, tallies=%s",
            symbol, meeting_symbols, event_types, include_vote_tallies
        )

        base_query = """
            SELECT
                ve.id,
                ve.event_type,
                ve.description,
                ve.result,
                m.symbol AS meeting_symbol,
                d.symbol AS target_symbol
            FROM vote_events ve
            JOIN documents m ON m.id = ve.meeting_id
            LEFT JOIN documents d ON d.id = ve.target_document_id
            WHERE 1=1
        """

        if symbol:
            base_query += " AND d.symbol = :symbol"
        if meeting_symbols:
            base_query += " AND m.symbol = ANY(:meeting_symbols)"
        if event_types:
            base_query += " AND ve.event_type = ANY(:event_types)"

        if include_vote_tallies:
            base_query = f"""
                WITH base_events AS (
                    {base_query}
                )
                SELECT
                    be.*,
                    COALESCE(SUM(CASE WHEN v.vote_type = 'in_favour' THEN 1 ELSE 0 END), 0) AS in_favour,
                    COALESCE(SUM(CASE WHEN v.vote_type = 'against' THEN 1 ELSE 0 END), 0) AS against,
                    COALESCE(SUM(CASE WHEN v.vote_type = 'abstaining' THEN 1 ELSE 0 END), 0) AS abstaining
                FROM base_events be
                LEFT JOIN votes v ON v.vote_event_id = be.id
                GROUP BY be.id, be.event_type, be.description, be.result, be.meeting_symbol, be.target_symbol
                ORDER BY be.meeting_symbol, be.id
            """
        else:
            base_query += " ORDER BY m.symbol, ve.id"

        params = {
            "symbol": symbol,
            "meeting_symbols": meeting_symbols,
            "event_types": event_types
        }

        results = session.execute(text(base_query), params).fetchall()

        events = []
        for row in results:
            event = {
                "id": row[0],
                "event_type": row[1],
                "description": row[2],
                "result": row[3],
                "meeting_symbol": row[4],
                "target_symbol": row[5]
            }
            if include_vote_tallies:
                event["vote_tallies"] = {
                    "in_favour": row[6],
                    "against": row[7],
                    "abstaining": row[8]
                }
            events.append(event)

        logger.info("Found %s vote events", len(events))

        return {
            "events": events,
            "count": len(events)
        }
    except Exception as e:
        logger.error("Error getting vote events: %s", e, exc_info=True)
        return {
            "events": [],
            "count": 0,
            "error": str(e)
        }
    finally:
        session.close()


# Tool 4: Get Utterances

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
                },
                "include_full_text": {
                    "type": "boolean",
                    "description": "Return full utterance text instead of a preview (default false)"
                }
            },
            "required": ["meeting_symbols"]
        }
    }


def execute_get_utterances(
    meeting_symbols: List[str],
    speaker_countries: Optional[List[str]] = None,
    include_full_text: bool = False
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

        utterance_payloads = []
        for u in utterances:
            payload = {
                "speaker_affiliation": u.speaker_affiliation,
                "speaker_name": u.speaker_name,
                "text": u.text if include_full_text else (u.text[:500] if u.text else ""),
                "meeting_symbol": u.meeting.symbol if u.meeting else None,
                "agenda_item": u.agenda_item_number
            }
            utterance_payloads.append(payload)

        return {
            "utterances": utterance_payloads,
            "count": len(utterance_payloads)
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


# Tool 5: Get Related Utterances

def get_related_utterances_tool() -> Dict[str, Any]:
    """Get utterances directly tied to one or more UN documents."""
    return {
        "type": "function",
        "name": "get_related_utterances",
        "description": "Get utterances tied to a specific resolution/draft symbol (no recursive traversal). Filters utterances to those that explicitly reference the requested documents via utterance_documents.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Document symbol to seed the chain (e.g., 'A/RES/78/220')"
                },
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of document symbols to include in the query (use when you already know multiple symbols)."
                },
                "reference_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by reference_type in utterance_documents (optional)"
                },
                "speaker_countries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by speaker country names (optional)"
                },
                "include_full_text": {
                    "type": "boolean",
                    "description": "Return full utterance text instead of a preview (default false)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max utterances to return (default 200)"
                }
            }
        }
    }


def execute_get_related_utterances(
    symbol: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    reference_types: Optional[List[str]] = None,
    speaker_countries: Optional[List[str]] = None,
    include_full_text: bool = False,
    limit: int = 200
) -> Dict[str, Any]:
    """
    Execute utterance query for a document chain.

    Args:
        symbol: Primary document symbol
        symbols: Optional additional document symbols
        reference_types: Optional filter on utterance_documents.reference_type
        speaker_countries: Optional filter on speaker affiliations
        limit: Max utterances to return

    Returns:
        Dict with utterances, referenced symbols, and count
    """
    from db.config import get_session

    document_symbols: List[str] = []
    if symbols:
        document_symbols.extend([s for s in symbols if s])
    if symbol:
        document_symbols.append(symbol)

    # De-duplicate while preserving order of appearance
    seen = set()
    ordered_symbols: List[str] = []
    for sym in document_symbols:
        if sym not in seen:
            ordered_symbols.append(sym)
            seen.add(sym)

    if not ordered_symbols:
        raise ValueError("Must supply at least one document symbol")

    session = get_session()
    try:
        logger.info(
            "Getting related utterances for symbols=%s ref_types=%s speakers=%s limit=%s",
            ordered_symbols, reference_types, speaker_countries, limit
        )

        query = """
            SELECT
                u.id,
                u.speaker_name,
                u.speaker_affiliation,
                u.agenda_item_number,
                u.text,
                u.position_in_meeting,
                m.symbol AS meeting_symbol,
                d.symbol AS referenced_symbol,
                ud.reference_type
            FROM utterances u
            JOIN utterance_documents ud ON ud.utterance_id = u.id
            JOIN documents d ON d.id = ud.document_id
            JOIN documents m ON m.id = u.meeting_id
            WHERE d.symbol = ANY(:symbols)
        """

        if reference_types:
            query += " AND ud.reference_type = ANY(:reference_types)"

        if speaker_countries:
            speaker_filters = " OR ".join(
                [
                    f"(u.speaker_affiliation ILIKE :speaker_{i} OR "
                    f"u.speaker_name ILIKE :speaker_{i})"
                    for i in range(len(speaker_countries))
                ]
            )
            query += f" AND ({speaker_filters})"

        query += " ORDER BY d.symbol, m.date, u.position_in_meeting LIMIT :limit"

        params = {
            "symbols": ordered_symbols,
            "reference_types": reference_types,
            "limit": limit
        }

        if speaker_countries:
            for i, country in enumerate(speaker_countries):
                params[f"speaker_{i}"] = f"%{country}%"

        results = session.execute(text(query), params).fetchall()

        utterances = []
        referenced_symbols = set()
        for row in results:
            referenced_symbols.add(row[7])
            payload = {
                "utterance_id": row[0],
                "speaker_name": row[1],
                "speaker_affiliation": row[2],
                "agenda_item": row[3],
                "text": row[4] if include_full_text else (row[4][:500] if row[4] else ""),
                "position_in_meeting": row[5],
                "meeting_symbol": row[6],
                "referenced_symbol": row[7],
                "reference_type": row[8]
            }
            utterances.append(payload)

        logger.info("Found %s related utterances", len(utterances))

        return {
            "utterances": utterances,
            "referenced_symbols": [sym for sym in ordered_symbols if sym in referenced_symbols],
            "count": len(utterances),
            "truncated": len(utterances) >= limit
        }
    except Exception as e:
        logger.error("Error getting related utterances: %s", e, exc_info=True)
        return {
            "utterances": [],
            "referenced_symbols": [],
            "count": 0,
            "error": str(e)
        }
    finally:
        session.close()


# Tool 5b: Get Chain Utterances (meetings + utterances for a doc chain)

def get_chain_utterances_tool() -> Dict[str, Any]:
    """Get meetings and utterances for a document chain."""
    return {
        "type": "function",
        "name": "get_chain_utterances",
        "description": "Traverse a document chain (resolution/drafts/reports) and return linked meetings plus utterances that reference any doc in the chain. Falls back to utterance-linked meetings if meeting_record_for edges are missing.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Seed document symbol, e.g., 'A/RES/78/156'"
                },
                "speaker_countries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter utterances by speaker affiliation (optional)"
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max traversal depth through document_relationships (default 4)"
                },
                "include_full_text": {
                    "type": "boolean",
                    "description": "Return full utterance text (default false)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max utterances to return (default 100)"
                }
            },
            "required": ["symbol"]
        }
    }


def execute_get_chain_utterances(
    symbol: str,
    speaker_countries: Optional[List[str]] = None,
    max_depth: int = 4,
    include_full_text: bool = False,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Traverse a document chain and fetch meetings + utterances that reference the chain docs.
    Falls back to meetings observed via utterance_documents if meeting_record_for edges are missing.
    """
    from db.config import get_session

    session = get_session()
    try:
        logger.info(
            "Getting chain meetings + utterances for %s depth=%s speakers=%s limit=%s",
            symbol, max_depth, speaker_countries, limit
        )

        query = """
            WITH RECURSIVE chain AS (
                SELECT d.id, d.symbol, d.doc_type, 0 AS depth
                FROM documents d WHERE d.symbol = :symbol
                UNION ALL
                SELECT other.id, other.symbol, other.doc_type, c.depth + 1
                FROM chain c
                JOIN document_relationships dr
                  ON dr.source_id = c.id OR dr.target_id = c.id
                JOIN documents other
                  ON other.id = CASE WHEN dr.source_id = c.id THEN dr.target_id ELSE dr.source_id END
                WHERE c.depth < :max_depth
                  AND other.doc_type NOT IN ('meeting','committee_meeting')
            ),
            chain_ids AS (SELECT DISTINCT id FROM chain),
            rel_meetings AS (
                SELECT DISTINCT m.id, m.symbol, m.date
                FROM chain_ids c
                JOIN document_relationships dr
                  ON (dr.source_id = c.id OR dr.target_id = c.id)
                 AND dr.relationship_type = 'meeting_record_for'
                JOIN documents m
                  ON m.id = CASE WHEN dr.source_id = c.id THEN dr.target_id ELSE dr.source_id END
                WHERE m.doc_type IN ('meeting','committee_meeting')
            ),
            utt_meetings AS (
                SELECT DISTINCT m.id, m.symbol, m.date
                FROM utterances u
                JOIN utterance_documents ud ON ud.utterance_id = u.id
                JOIN documents m ON m.id = u.meeting_id
                WHERE ud.document_id IN (SELECT id FROM chain_ids)
            ),
            meetings AS (
                SELECT * FROM rel_meetings
                UNION
                SELECT * FROM utt_meetings
            )
            SELECT
                u.id AS utterance_id,
                u.speaker_name,
                u.speaker_affiliation,
                u.agenda_item_number,
                u.text,
                u.position_in_meeting,
                m.symbol AS meeting_symbol,
                ref.symbol AS referenced_symbol,
                ud.reference_type
            FROM utterances u
            JOIN meetings m ON m.id = u.meeting_id
            LEFT JOIN utterance_documents ud ON ud.utterance_id = u.id
            LEFT JOIN documents ref ON ref.id = ud.document_id
            WHERE (ud.document_id IS NULL OR ud.document_id IN (SELECT id FROM chain_ids))
        """

        params: Dict[str, Any] = {
            "symbol": symbol,
            "max_depth": max_depth,
            "limit": limit
        }

        if speaker_countries:
            speaker_filters = " OR ".join(
                f"u.speaker_affiliation ILIKE :speaker_{i}"
                for i in range(len(speaker_countries))
            )
            query += f" AND ({speaker_filters})"
            for i, country in enumerate(speaker_countries):
                params[f"speaker_{i}"] = f"%{country}%"

        query += " ORDER BY m.date, u.position_in_meeting LIMIT :limit"

        results = session.execute(text(query), params).fetchall()

        utterances = []
        referenced_symbols = set()
        meetings = set()
        for row in results:
            if row[7]:
                referenced_symbols.add(row[7])
            meetings.add(row[6])
            payload = {
                "utterance_id": row[0],
                "speaker_name": row[1],
                "speaker_affiliation": row[2],
                "agenda_item": row[3],
                "text": row[4] if include_full_text else (row[4][:500] if row[4] else ""),
                "position_in_meeting": row[5],
                "meeting_symbol": row[6],
                "referenced_symbol": row[7],
                "reference_type": row[8]
            }
            utterances.append(payload)

        # Chain docs for context
        chain_rows = session.execute(text("""
            WITH RECURSIVE chain AS (
                SELECT d.id, d.symbol, d.doc_type, 0 AS depth
                FROM documents d WHERE d.symbol = :symbol
                UNION ALL
                SELECT other.id, other.symbol, other.doc_type, c.depth + 1
                FROM chain c
                JOIN document_relationships dr
                  ON dr.source_id = c.id OR dr.target_id = c.id
                JOIN documents other
                  ON other.id = CASE WHEN dr.source_id = c.id THEN dr.target_id ELSE dr.source_id END
                WHERE c.depth < :max_depth
                  AND other.doc_type NOT IN ('meeting','committee_meeting')
            )
            SELECT DISTINCT id, symbol, doc_type, depth FROM chain ORDER BY depth, symbol
        """), {"symbol": symbol, "max_depth": max_depth}).fetchall()
        chain_docs = [
            {"id": r[0], "symbol": r[1], "doc_type": r[2], "depth": r[3]}
            for r in chain_rows
        ]

        return {
            "utterances": utterances,
            "count": len(utterances),
            "truncated": len(utterances) >= limit,
            "referenced_symbols": sorted(referenced_symbols),
            "meetings": sorted(meetings),
            "chain": chain_docs
        }
    except Exception as e:
        logger.error("Error getting chain utterances: %s", e, exc_info=True)
        return {
            "utterances": [],
            "count": 0,
            "error": str(e)
        }
    finally:
        session.close()


# Tool 6: Get Document Details

def get_document_details_tool() -> Dict[str, Any]:
    """Get basic document metadata (title, date, type)."""
    return {
        "type": "function",
        "name": "get_document_details",
        "description": "Get basic metadata for one or more document symbols (type, title, date, session).",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Single document symbol (optional if symbols provided)"
                },
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of document symbols (optional)"
                },
                "include_metadata": {
                    "type": "boolean",
                    "description": "Include doc_metadata JSON blob (default false)"
                }
            },
            "required": []
        }
    }


def execute_get_document_details(
    symbol: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    include_metadata: bool = False
) -> Dict[str, Any]:
    """
    Execute document metadata lookup.

    Args:
        symbol: Single document symbol
        symbols: List of document symbols
        include_metadata: Whether to include doc_metadata blob

    Returns:
        Dict with documents list and count
    """
    from db.config import get_session
    from db.models import Document

    targets = []
    if symbol:
        targets.append(symbol)
    if symbols:
        targets.extend(symbols)

    if not targets:
        return {
            "documents": [],
            "count": 0,
            "error": "Provide symbol or symbols"
        }

    session = get_session()
    try:
        logger.info("Getting document details for %s symbols", len(targets))
        docs = session.query(Document).filter(Document.symbol.in_(targets)).all()

        payloads = []
        for doc in docs:
            payload = {
                "symbol": doc.symbol,
                "doc_type": doc.doc_type,
                "title": doc.title,
                "date": str(doc.date) if doc.date else None,
                "session": doc.session
            }
            if include_metadata:
                payload["doc_metadata"] = doc.doc_metadata
            payloads.append(payload)

        return {
            "documents": payloads,
            "count": len(payloads)
        }
    except Exception as e:
        logger.error("Error getting document details: %s", e, exc_info=True)
        return {
            "documents": [],
            "count": 0,
            "error": str(e)
        }
    finally:
        session.close()


# Tool 7: Execute SQL Query

def execute_sql_query_tool() -> Dict[str, Any]:
    """Execute a SQL query to search for documents, votes, or other data."""
    return {
        "type": "function",
        "name": "execute_sql_query",
        "description": "Execute a SQL query to find documents, votes, utterances, or other data matching specific criteria. Use this when you need to search or discover documents without knowing specific symbols. Returns structured results with columns and rows. Examples: finding resolutions where countries voted differently, searching by topic/keywords, analyzing voting patterns.",
        "parameters": {
            "type": "object",
            "properties": {
                "natural_language_query": {
                    "type": "string",
                    "description": "Natural language description of what data you want to query. Examples: 'Find resolutions where China voted against and US voted in favour', 'Find meetings about climate change in session 78', 'Which countries most often vote against human rights resolutions'"
                }
            },
            "required": ["natural_language_query"]
        }
    }


def execute_execute_sql_query(
    natural_language_query: str,
    conversation_context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute SQL query using text-to-sql system.

    Args:
        natural_language_query: Natural language description of what to query
        conversation_context: Optional string with previous Q&A for multi-turn context

    Returns:
        Dict with columns, rows, and row_count
    """
    from rag.text_to_sql import generate_sql
    from db.config import engine

    try:
        logger.info(f"Executing SQL query: {natural_language_query}")
        if conversation_context:
            logger.info(f"With conversation context provided")

        # Generate SQL from natural language (with context if available)
        sql_query = generate_sql(natural_language_query, conversation_context=conversation_context)
        logger.info(f"Generated SQL: {sql_query}")

        # Execute query
        with engine.connect() as connection:
            result = connection.execute(text(sql_query))
            columns = list(result.keys())
            rows = result.fetchall()

        # Convert rows to list of dicts
        row_dicts = []
        for row in rows[:100]:  # Limit to 100 rows for performance
            row_dict = {}
            for col in columns:
                value = row._mapping.get(col)
                # Convert to string for JSON serialization
                if value is not None:
                    row_dict[col] = str(value)
                else:
                    row_dict[col] = None
            row_dicts.append(row_dict)

        logger.info(f"SQL query returned {len(rows)} rows")

        return {
            "columns": columns,
            "rows": row_dicts,
            "row_count": len(rows),
            "sql_query": sql_query,
            "truncated": len(rows) > 100
        }

    except Exception as e:
        logger.error(f"SQL query execution failed: {e}", exc_info=True)
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": str(e)
        }


# Tool 8: Semantic Search

def semantic_search_tool() -> Dict[str, Any]:
    """Search documents and utterances by semantic meaning using vector embeddings."""
    return {
        "type": "function",
        "name": "semantic_search",
        "description": """Search for documents and utterances by semantic meaning (concepts, themes) rather than exact keywords.

Use this when:
- Looking for conceptual/thematic content (e.g., 'human rights violations', 'climate adaptation')
- The user's question is about ideas/concepts rather than specific symbols/countries
- Keyword search might miss relevant results due to synonyms or paraphrasing

Returns documents and utterances ranked by semantic similarity to the query.
Optionally filter by doc_type, session, or speaker countries.""",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The semantic search query describing what you're looking for"
                },
                "search_type": {
                    "type": "string",
                    "enum": ["documents", "utterances", "both"],
                    "description": "What to search: 'documents' (resolutions, drafts), 'utterances' (speeches), or 'both'"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results per type (default: 10)"
                },
                "doc_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter documents by type: ['resolution', 'draft', 'meeting', 'committee_report']"
                },
                "session": {
                    "type": "integer",
                    "description": "Filter by UN session number (e.g., 78)"
                },
                "speaker_countries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter utterances by speaker country (e.g., ['France', 'Germany'])"
                },
                "min_similarity": {
                    "type": "number",
                    "description": "Minimum cosine similarity threshold (0-1, default: 0.5)"
                }
            },
            "required": ["query", "search_type"]
        }
    }


def execute_semantic_search(
    query: str,
    search_type: str = "both",
    limit: int = 10,
    doc_types: Optional[List[str]] = None,
    session: Optional[int] = None,
    speaker_countries: Optional[List[str]] = None,
    min_similarity: float = 0.5
) -> Dict[str, Any]:
    """
    Execute semantic search using pgvector.

    Args:
        query: Search query text
        search_type: 'documents', 'utterances', or 'both'
        limit: Max results per type
        doc_types: Filter by document types
        session: Filter by session number
        speaker_countries: Filter utterances by speaker
        min_similarity: Minimum similarity threshold (0-1)

    Returns:
        Dict with documents and/or utterances lists, each with similarity scores
    """
    from db.config import get_session
    from db.models import PGVECTOR_AVAILABLE

    db_session = get_session()
    results: Dict[str, Any] = {
        "query": query,
        "documents": [],
        "utterances": [],
        "document_count": 0,
        "utterance_count": 0
    }

    # Check if pgvector is available
    if not PGVECTOR_AVAILABLE:
        logger.warning("pgvector not available - semantic search disabled")
        results["error"] = "Semantic search not available (pgvector not installed)"
        return results

    try:
        # Generate query embedding
        from rag.embeddings import embed_text
        query_embedding = embed_text(query)
        if not query_embedding:
            results["error"] = "Failed to generate query embedding"
            return results

        # Convert to pgvector format
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        logger.info(
            "Semantic search: query=%s, type=%s, limit=%d, min_sim=%.2f",
            query[:50], search_type, limit, min_similarity
        )

        # Search documents
        if search_type in ["documents", "both"]:
            doc_sql = """
                SELECT
                    d.id,
                    d.symbol,
                    d.doc_type,
                    d.title,
                    d.date,
                    d.session,
                    LEFT(d.body_text, 500) as text_preview,
                    1 - (d.body_text_embedding <=> :embedding::vector) as similarity
                FROM documents d
                WHERE d.body_text_embedding IS NOT NULL
                  AND 1 - (d.body_text_embedding <=> :embedding::vector) >= :min_similarity
            """

            params: Dict[str, Any] = {
                "embedding": embedding_str,
                "min_similarity": min_similarity
            }

            if doc_types:
                doc_sql += " AND d.doc_type = ANY(:doc_types)"
                params["doc_types"] = doc_types

            if session:
                doc_sql += " AND d.session = :session"
                params["session"] = session

            doc_sql += " ORDER BY similarity DESC LIMIT :limit"
            params["limit"] = limit

            doc_results = db_session.execute(text(doc_sql), params).fetchall()

            results["documents"] = [
                {
                    "id": row[0],
                    "symbol": row[1],
                    "doc_type": row[2],
                    "title": row[3],
                    "date": str(row[4]) if row[4] else None,
                    "session": row[5],
                    "text_preview": row[6],
                    "similarity": round(row[7], 4)
                }
                for row in doc_results
            ]

        # Search utterances
        if search_type in ["utterances", "both"]:
            utt_sql = """
                SELECT
                    u.id,
                    u.speaker_affiliation,
                    u.speaker_name,
                    u.agenda_item_number,
                    LEFT(u.text, 500) as text_preview,
                    m.symbol as meeting_symbol,
                    1 - (u.text_embedding <=> :embedding::vector) as similarity
                FROM utterances u
                JOIN documents m ON m.id = u.meeting_id
                WHERE u.text_embedding IS NOT NULL
                  AND 1 - (u.text_embedding <=> :embedding::vector) >= :min_similarity
            """

            params = {
                "embedding": embedding_str,
                "min_similarity": min_similarity
            }

            if speaker_countries:
                country_filters = " OR ".join(
                    f"u.speaker_affiliation ILIKE :speaker_{i}"
                    for i in range(len(speaker_countries))
                )
                utt_sql += f" AND ({country_filters})"
                for i, country in enumerate(speaker_countries):
                    params[f"speaker_{i}"] = f"%{country}%"

            if session:
                utt_sql += " AND m.session = :session"
                params["session"] = session

            utt_sql += " ORDER BY similarity DESC LIMIT :limit"
            params["limit"] = limit

            utt_results = db_session.execute(text(utt_sql), params).fetchall()

            results["utterances"] = [
                {
                    "id": row[0],
                    "speaker_affiliation": row[1],
                    "speaker_name": row[2],
                    "agenda_item": row[3],
                    "text_preview": row[4],
                    "meeting_symbol": row[5],
                    "similarity": round(row[6], 4)
                }
                for row in utt_results
            ]

        results["document_count"] = len(results["documents"])
        results["utterance_count"] = len(results["utterances"])

        logger.info(
            "Semantic search found %d documents, %d utterances",
            results["document_count"], results["utterance_count"]
        )
        return results

    except Exception as e:
        logger.error("Semantic search failed: %s", e, exc_info=True)
        results["error"] = str(e)
        return results
    finally:
        db_session.close()


# Tool 9: Answer With Evidence

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
        }
    }


# Tool 10: Get Full Text Context (New Baseline)

def get_full_text_context_tool() -> Dict[str, Any]:
    """Get full text of a resolution and all its related documents."""
    return {
        "type": "function",
        "name": "get_full_text_context",
        "description": "Get the FULL text content of a resolution and all its directly related documents (drafts, committee reports, meeting records). Use this as the primary tool to understand the complete context of a resolution, including what was said in meetings (meeting records contain the full transcript/text).",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Resolution symbol, e.g., 'A/RES/78/225'"
                }
            },
            "required": ["symbol"]
        }
    }


def execute_get_full_text_context(symbol: str) -> Dict[str, Any]:
    """
    Execute full text context fetch.
    
    Args:
        symbol: Resolution symbol
        
    Returns:
        Dict with full text of resolution, drafts, reports, and meetings.
    """
    from db.config import get_session
    from db.models import Document, DocumentRelationship
    
    session = get_session()
    try:
        logger.info(f"Getting full text context for {symbol}")
        
        # 1. Get the main document
        doc = session.query(Document).filter(Document.symbol == symbol).first()
        if not doc:
            return {
                "symbol": symbol,
                "error": "Document not found"
            }
            
        result = {
            "symbol": symbol,
            "resolution": {
                "symbol": doc.symbol,
                "title": doc.title,
                "date": str(doc.date) if doc.date else None,
                "text": doc.body_text
            },
            "drafts": [],
            "committee_reports": [],
            "meetings": [],
            "agenda_items": []
        }
        
        # 2. Get related documents
        # We query for documents that are sources of relationships to this target
        query = text("""
            SELECT 
                d.symbol, 
                d.doc_type, 
                d.title,
                d.date,
                d.body_text,
                dr.relationship_type
            FROM documents d
            JOIN document_relationships dr ON dr.source_id = d.id
            WHERE dr.target_id = :doc_id
            ORDER BY d.date DESC, d.symbol
        """)
        
        related_docs = session.execute(query, {"doc_id": doc.id}).fetchall()
        
        meetings_buffer = []
        
        for row in related_docs:
            r_symbol, r_type, r_title, r_date, r_text, rel_type = row
            
            item = {
                "symbol": r_symbol,
                "title": r_title,
                "date": str(r_date) if r_date else None,
                "text": r_text
            }
            
            # Map by relationship or doc type
            if rel_type == "meeting_record_for" or r_type in ["meeting", "committee_meeting"]:
                result["meetings"].append(item)
            elif rel_type == "draft_of" or r_type == "draft":
                result["drafts"].append(item)
            elif rel_type == "committee_report_for" or r_type == "committee_report":
                result["committee_reports"].append(item)
            elif rel_type == "agenda_item_for" or r_type in ["agenda", "agenda_item"]:
                # Agenda items usually don't have text, but include for metadata
                result["agenda_items"].append({
                    "symbol": r_symbol,
                    "title": r_title
                })
        
        # Calculate stats for logging
        stats = {
            "drafts": len(result["drafts"]),
            "reports": len(result["committee_reports"]),
            "meetings": len(result["meetings"])
        }
        logger.info(f"Found context: {stats}")
        
        return result

    except Exception as e:
        logger.error(f"Error fetching full context for {symbol}: {e}", exc_info=True)
        return {
            "symbol": symbol,
            "error": str(e)
        }
    finally:
        session.close()
