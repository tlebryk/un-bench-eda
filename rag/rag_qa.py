"""RAG question-answering service with evidence grounding from all database tables."""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import text

from db.config import engine, get_session
from db.models import Document, Actor, Vote, Utterance, DocumentRelationship

# Load environment variables
load_dotenv()

# Set up logging
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "rag_qa.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# OpenAI client will be initialized lazily when needed
_client = None

# Maximum number of results to include in evidence extraction
MAX_RESULTS_FOR_EVIDENCE = 20


def get_client():
    """Get or create OpenAI client."""
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables. Please set it in your .env file.")
        _client = OpenAI(api_key=api_key)
    return _client


def get_value(cell_data: Any) -> Any:
    """Extract value from either UI-formatted or raw cell data."""
    if cell_data is None:
        return None
    # UI-formatted: {"full": "value", "display": "...", "truncated": False}
    if isinstance(cell_data, dict) and "full" in cell_data:
        return cell_data["full"]
    # Raw string/value
    return cell_data


def extract_evidence_context(
    query_results: Dict[str, Any],
    max_results: int = MAX_RESULTS_FOR_EVIDENCE
) -> List[Dict[str, Any]]:
    """
    Extract evidence context from query results, handling ALL database tables.
    
    Extracts from:
    - documents: symbol, title, date, body_text, doc_type, session
    - votes: vote_type, vote_context, actor names
    - utterances: text, speaker_affiliation, speaker_name, meeting context
    - actors: name, normalized_name, actor_type
    - document_relationships: relationship_type, source/target symbols
    
    Args:
        query_results: Result dictionary from execute_sql with 'columns' and 'rows'
        max_results: Maximum number of rows to process
    
    Returns:
        List of evidence dictionaries with type, symbol, data, and text fields
    """
    if not query_results.get("rows"):
        return []
    
    evidence_list = []
    rows = query_results["rows"][:max_results]
    columns = query_results.get("columns", [])
    
    for row in rows:
        evidence = {
            "type": "unknown",
            "symbol": None,
            "data": {},
            "text": None
        }
        
        # Extract document information
        if "symbol" in row:
            evidence["symbol"] = get_value(row["symbol"])
            evidence["type"] = "document"
            
            # Extract document fields
            if "title" in row:
                evidence["data"]["title"] = get_value(row["title"])
            if "date" in row:
                date_val = get_value(row["date"])
                if date_val:
                    evidence["data"]["date"] = str(date_val)
            if "doc_type" in row:
                evidence["data"]["doc_type"] = get_value(row["doc_type"])
            if "session" in row:
                evidence["data"]["session"] = get_value(row["session"])
            if "body_text" in row:
                body_text = get_value(row["body_text"])
                if body_text:
                    evidence["text"] = str(body_text)
        
        # Extract vote information
        if "vote_type" in row or "vote_context" in row:
            if evidence["type"] == "unknown":
                evidence["type"] = "vote"
            if "vote_type" in row:
                evidence["data"]["vote_type"] = get_value(row["vote_type"])
            if "vote_context" in row:
                evidence["data"]["vote_context"] = get_value(row["vote_context"])
            # Try to get actor name from various column names
            for col in ["name", "actor_name", "speaker_affiliation", "country"]:
                if col in row:
                    actor_name = get_value(row[col])
                    if actor_name:
                        evidence["data"]["actor"] = str(actor_name)
                        break
        
        # Extract utterance information
        if "text" in row and evidence["type"] != "document":
            if evidence["type"] == "unknown":
                evidence["type"] = "utterance"
            utterance_text = get_value(row["text"])
            if utterance_text:
                evidence["text"] = str(utterance_text)
            # Extract utterance ID if present (for fetching missing text)
            if "id" in row:
                utterance_id = get_value(row["id"])
                if isinstance(utterance_id, int) or (isinstance(utterance_id, str) and utterance_id.isdigit()):
                    evidence["data"]["id"] = int(utterance_id) if isinstance(utterance_id, str) else utterance_id
            if "speaker_affiliation" in row:
                evidence["data"]["speaker_affiliation"] = get_value(row["speaker_affiliation"])
            if "speaker_name" in row:
                evidence["data"]["speaker_name"] = get_value(row["speaker_name"])
            if "meeting_id" in row or "meeting_symbol" in row:
                meeting_ref = get_value(row.get("meeting_id") or row.get("meeting_symbol"))
                if meeting_ref:
                    evidence["data"]["meeting"] = str(meeting_ref)
            if "agenda_item_number" in row:
                evidence["data"]["agenda_item"] = get_value(row["agenda_item_number"])
        
        # Extract actor information
        if "actor_type" in row and evidence["type"] == "unknown":
            evidence["type"] = "actor"
            if "name" in row:
                evidence["data"]["name"] = get_value(row["name"])
            if "normalized_name" in row:
                evidence["data"]["normalized_name"] = get_value(row["normalized_name"])
        
        # Extract relationship information
        if "relationship_type" in row:
            if evidence["type"] == "unknown":
                evidence["type"] = "relationship"
            evidence["data"]["relationship_type"] = get_value(row["relationship_type"])
            if "source_id" in row or "source_symbol" in row:
                source_ref = get_value(row.get("source_id") or row.get("source_symbol"))
                if source_ref:
                    evidence["data"]["source"] = str(source_ref)
            if "target_id" in row or "target_symbol" in row:
                target_ref = get_value(row.get("target_id") or row.get("target_symbol"))
                if target_ref:
                    evidence["data"]["target"] = str(target_ref)
        
        # Extract any remaining metadata
        if "doc_metadata" in row:
            metadata_str = get_value(row["doc_metadata"])
            if metadata_str:
                try:
                    if isinstance(metadata_str, str):
                        metadata = json.loads(metadata_str)
                    else:
                        metadata = metadata_str
                    if isinstance(metadata, dict):
                        evidence["data"]["metadata"] = metadata
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # Only add if we have meaningful data
        if evidence["symbol"] or evidence["text"] or evidence["data"]:
            evidence_list.append(evidence)
    
    logger.info(f"Extracted {len(evidence_list)} evidence items from query results")
    return evidence_list


def fetch_missing_text(symbols: Set[str], utterance_ids: Optional[Set[int]] = None) -> Dict[str, Any]:
    """
    Fetch missing text content for documents and utterances.
    
    Args:
        symbols: Set of document symbols to fetch body_text for
        utterance_ids: Optional set of utterance IDs to fetch text for
    
    Returns:
        Dictionary with 'documents' and 'utterances' keys containing fetched text
    """
    fetched = {"documents": {}, "utterances": {}}
    
    if not symbols and not utterance_ids:
        return fetched
    
    session = get_session()
    try:
        # Fetch document body_text
        if symbols:
            docs = session.query(Document).filter(Document.symbol.in_(list(symbols))).all()
            for doc in docs:
                if doc.body_text:
                    fetched["documents"][doc.symbol] = doc.body_text
        
        # Fetch utterance text
        if utterance_ids:
            utterances = session.query(Utterance).filter(Utterance.id.in_(list(utterance_ids))).all()
            for utt in utterances:
                if utt.text:
                    fetched["utterances"][utt.id] = {
                        "text": utt.text,
                        "speaker_affiliation": utt.speaker_affiliation,
                        "speaker_name": utt.speaker_name,
                        "meeting_id": utt.meeting_id
                    }
    finally:
        session.close()
    
    logger.info(f"Fetched text for {len(fetched['documents'])} documents and {len(fetched['utterances'])} utterances")
    return fetched


def format_evidence_for_prompt(evidence_context: List[Dict[str, Any]]) -> str:
    """
    Format evidence context into readable text for RAG prompt.
    
    Args:
        evidence_context: List of evidence dictionaries
    
    Returns:
        Formatted string with all evidence
    """
    formatted_parts = []
    
    for evidence in evidence_context:
        ev_type = evidence.get("type", "unknown")
        symbol = evidence.get("symbol", "Unknown")
        data = evidence.get("data", {})
        text = evidence.get("text")
        
        if ev_type == "document":
            parts = [f"Document: {symbol}"]
            if data.get("doc_type"):
                parts.append(f"Type: {data['doc_type']}")
            if data.get("date"):
                parts.append(f"Date: {data['date']}")
            if data.get("session"):
                parts.append(f"Session: {data['session']}")
            if data.get("title"):
                parts.append(f"Title: {data['title']}")
            if text:
                # Truncate long text (keep first 1000 chars + last 500 chars)
                if len(text) > 1500:
                    text_preview = f"{text[:1000]}... [truncated] ...{text[-500:]}"
                else:
                    text_preview = text
                parts.append(f"Text: {text_preview}")
            formatted_parts.append(" | ".join(parts))
        
        elif ev_type == "vote":
            parts = [f"Vote on {symbol}"]
            if data.get("actor"):
                parts.append(f"Actor: {data['actor']}")
            if data.get("vote_type"):
                parts.append(f"Vote: {data['vote_type']}")
            if data.get("vote_context"):
                parts.append(f"Context: {data['vote_context']}")
            formatted_parts.append(" | ".join(parts))
        
        elif ev_type == "utterance":
            parts = [f"Statement"]
            if data.get("meeting"):
                parts.append(f"Meeting: {data['meeting']}")
            if data.get("speaker_affiliation"):
                parts.append(f"Speaker: {data['speaker_affiliation']}")
            if data.get("speaker_name"):
                parts.append(f"Name: {data['speaker_name']}")
            if data.get("agenda_item"):
                parts.append(f"Agenda Item: {data['agenda_item']}")
            if text:
                # Truncate long utterances
                if len(text) > 1000:
                    text_preview = f"{text[:800]}... [truncated]"
                else:
                    text_preview = text
                parts.append(f"Text: '{text_preview}'")
            formatted_parts.append(" | ".join(parts))
        
        elif ev_type == "relationship":
            parts = [f"Relationship: {symbol}"]
            if data.get("relationship_type"):
                parts.append(f"Type: {data['relationship_type']}")
            if data.get("source"):
                parts.append(f"Source: {data['source']}")
            if data.get("target"):
                parts.append(f"Target: {data['target']}")
            formatted_parts.append(" | ".join(parts))
        
        elif ev_type == "actor":
            parts = [f"Actor: {symbol}"]
            if data.get("name"):
                parts.append(f"Name: {data['name']}")
            if data.get("actor_type"):
                parts.append(f"Type: {data['actor_type']}")
            formatted_parts.append(" | ".join(parts))
    
    return "\n\n---\n\n".join(formatted_parts) if formatted_parts else "No evidence found."


def answer_question(
    query_results: Dict[str, Any],
    original_question: str,
    sql_query: Optional[str] = None,
    model: str = "gpt-5-nano-2025-08-07"
) -> Dict[str, Any]:
    """
    Answer a question using RAG with strict evidence grounding.
    
    Args:
        query_results: Result dictionary from execute_sql
        original_question: The original natural language question
        sql_query: Optional SQL query that generated the results
        model: OpenAI model to use
    
    Returns:
        Dictionary with 'answer', 'evidence', and 'sources' keys
    """
    logger.info(f"Answering question (model: {model}): {original_question}")
    
    # Extract evidence context
    evidence_context = extract_evidence_context(query_results)
    
    # Check for missing text and fetch if needed
    symbols_to_fetch = set()
    utterance_ids_to_fetch = set()
    
    for evidence in evidence_context:
        if evidence.get("symbol") and not evidence.get("text"):
            # Check if this is a document that might have body_text
            if evidence.get("type") == "document":
                symbols_to_fetch.add(evidence["symbol"])
        # Check for utterance IDs that need text
        if evidence.get("type") == "utterance" and "id" in evidence.get("data", {}):
            utterance_ids_to_fetch.add(evidence["data"]["id"])
    
    # Fetch missing text
    if symbols_to_fetch or utterance_ids_to_fetch:
        fetched_text = fetch_missing_text(symbols_to_fetch, utterance_ids_to_fetch if utterance_ids_to_fetch else None)
        
        # Merge fetched text into evidence context
        for evidence in evidence_context:
            if evidence.get("symbol") in fetched_text["documents"]:
                evidence["text"] = fetched_text["documents"][evidence["symbol"]]
            if evidence.get("type") == "utterance" and "id" in evidence.get("data", {}):
                utt_id = evidence["data"]["id"]
                if utt_id in fetched_text["utterances"]:
                    utt_data = fetched_text["utterances"][utt_id]
                    evidence["text"] = utt_data["text"]
                    if not evidence["data"].get("speaker_affiliation"):
                        evidence["data"]["speaker_affiliation"] = utt_data.get("speaker_affiliation")
    
    if not evidence_context:
        return {
            "answer": "Insufficient data: No relevant information found in the database to answer this question.",
            "evidence": [],
            "sources": []
        }
    
    # Format evidence for prompt
    formatted_evidence = format_evidence_for_prompt(evidence_context)
    
    # Extract sources (document symbols)
    sources = []
    for evidence in evidence_context:
        if evidence.get("symbol"):
            sources.append(evidence["symbol"])
        # Also extract from relationships
        if evidence.get("type") == "relationship":
            if evidence.get("data", {}).get("source"):
                sources.append(evidence["data"]["source"])
            if evidence.get("data", {}).get("target"):
                sources.append(evidence["data"]["target"])
    sources = list(set(sources))  # Deduplicate
    
    # Build prompt with strict grounding rules
    sql_section = f"\nSQL Query used: {sql_query}\n" if sql_query else ""
    
    prompt = f"""You are a research assistant analyzing UN General Assembly documents and meeting records.

STRICT RULES:
1. Base answers ONLY on the provided database results. Do not use external knowledge.
2. Cite sources using document symbols (e.g., "According to A/RES/78/220..." or "As stated in A/RES/78/220...")
3. Quote exact text when making specific claims about document content.
4. If data is insufficient to answer the question, explicitly state what's missing.
5. Do NOT speculate, infer beyond what's stated, or use external knowledge.
6. Distinguish between:
   - What the data explicitly states
   - What can be reasonably inferred from the data
   - What is unknown/not in the data

Question: {original_question}
{sql_section}
Retrieved Data:
{formatted_evidence}

Provide a direct answer to the question, citing specific document symbols and quoting relevant passages where appropriate. If the data cannot fully answer the question, explain what information is available and what is missing.

Answer:"""
    
    client = get_client()
    
    try:
        # Use standard OpenAI chat completions API
        result = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            # temperature=0.3,
        )

        answer = result.choices[0].message.content.strip()
        
        # Format evidence list for response
        evidence_list = []
        for evidence in evidence_context:
            ev_dict = {
                "type": evidence.get("type"),
                "symbol": evidence.get("symbol"),
                "data": evidence.get("data", {})
            }
            if evidence.get("text"):
                ev_dict["text_excerpt"] = evidence["text"][:500]  # Include excerpt
            evidence_list.append(ev_dict)
        
        logger.info(f"Successfully generated answer (length: {len(answer)} chars, sources: {len(sources)})")
        
        return {
            "answer": answer,
            "evidence": evidence_list,
            "sources": sources
        }
    
    except Exception as e:
        logger.error(f"Failed to answer question: {str(e)}", exc_info=True)
        raise RuntimeError(f"Failed to answer question: {str(e)}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Answer questions using RAG with evidence grounding")
    parser.add_argument("question", help="Natural language question")
    parser.add_argument("--model", default="gpt-5-nano-2025-08-07", help="OpenAI model to use")
    args = parser.parse_args()
    
    print("This module is designed to be used programmatically.")
    print("Use answer_question(query_results, question) function directly.")

