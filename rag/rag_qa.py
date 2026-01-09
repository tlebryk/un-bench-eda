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
from utils.logging_config import get_logger
logger = get_logger(__name__, log_file="rag_qa.log")

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


def _find_column(row: Dict[str, Any], *possible_names: str) -> Optional[str]:
    """
    Find first matching column name from possible variations.
    Handles cases where SQL uses aliases like 'utterance_text' vs 'text'.
    """
    for name in possible_names:
        if name in row:
            return name
    return None


def extract_evidence_context(
    query_results: Dict[str, Any],
    max_results: int = MAX_RESULTS_FOR_EVIDENCE
) -> List[Dict[str, Any]]:
    """
    Extract evidence context from query results.

    NEW APPROACH: Captures ALL columns from each row to handle arbitrary SQL aliases.
    The LLM will interpret the structured data rather than us trying to guess column meanings.

    Args:
        query_results: Result dictionary from execute_sql with 'columns' and 'rows'
        max_results: Maximum number of rows to process

    Returns:
        List of evidence dictionaries with all column data
    """
    if not query_results.get("rows"):
        return []

    evidence_list = []
    rows = query_results["rows"][:max_results]

    for row in rows:
        evidence = {
            "type": "data_row",
            "data": {}
        }

        # Extract ALL columns from the row
        for column, cell_data in row.items():
            value = get_value(cell_data)
            if value is not None and value != "":
                # Store with original column name
                evidence["data"][column] = str(value) if not isinstance(value, (dict, list)) else value

        # Only add if we have meaningful data
        if evidence["data"]:
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

    NEW APPROACH: Format all data fields clearly in a structured way,
    letting the LLM interpret what they mean.

    Args:
        evidence_context: List of evidence dictionaries

    Returns:
        Formatted string with all evidence
    """
    if not evidence_context:
        return "No evidence found."

    formatted_parts = []

    for idx, evidence in enumerate(evidence_context, 1):
        data = evidence.get("data", {})
        if not data:
            continue

        # Format each row as a structured record
        parts = [f"Record {idx}:"]
        for column, value in data.items():
            # Truncate very long text fields
            if isinstance(value, str) and len(value) > 2000:
                value = f"{value[:1500]}... [truncated] ...{value[-500:]}"
            parts.append(f"  {column}: {value}")

        formatted_parts.append("\n".join(parts))

    return "\n\n".join(formatted_parts)


def answer_question(
    query_results: Dict[str, Any],
    original_question: str,
    sql_query: Optional[str] = None,
    model: str = "gpt-5-mini-2025-08-07",
    prompt_style: str = "analytical"
) -> Dict[str, Any]:
    """
    Answer a question using RAG with configurable prompt styles.

    Args:
        query_results: Result dictionary from execute_sql
        original_question: The original natural language question
        sql_query: Optional SQL query that generated the results
        model: OpenAI model to use
        prompt_style: Prompt style to use ("strict", "analytical", "conversational")

    Returns:
        Dictionary with 'answer', 'evidence', and 'sources' keys
    """
    logger.info(f"Answering question (model: {model}, style: {prompt_style}): {original_question}")

    # Extract evidence context (now captures all columns)
    evidence_context = extract_evidence_context(query_results)

    if not evidence_context:
        return {
            "answer": "Insufficient data: No relevant information found in the database to answer this question.",
            "evidence": [],
            "sources": []
        }
    
    # Format evidence for prompt
    formatted_evidence = format_evidence_for_prompt(evidence_context)

    # Extract sources (document symbols) - look for symbol-like columns
    sources = []
    for evidence in evidence_context:
        data = evidence.get("data", {})
        for column, value in data.items():
            # Look for columns that contain document symbols
            if isinstance(value, str) and any(hint in column.lower() for hint in ['symbol', 'document']):
                # Check if it looks like a UN document symbol (has "/" and letters)
                if '/' in value and any(c.isalpha() for c in value):
                    sources.append(value)
    sources = list(set(sources))  # Deduplicate

    # Load prompt from registry
    from rag.prompt_registry import get_prompt
    system_instructions = get_prompt(prompt_style)

    # Build prompt with configurable style
    sql_section = f"\nSQL Query used: {sql_query}\n" if sql_query else ""

    prompt = f"""{system_instructions}

Question: {original_question}
{sql_section}
Retrieved Data:
{formatted_evidence}

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

        # Format evidence list for response (simplified structure)
        evidence_list = []
        for evidence in evidence_context:
            ev_dict = {
                "type": evidence.get("type", "data_row"),
                "data": evidence.get("data", {})
            }
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
    parser.add_argument("--model", default="gpt-5-mini-2025-08-07", help="OpenAI model to use")
    args = parser.parse_args()
    
    print("This module is designed to be used programmatically.")
    print("Use answer_question(query_results, question) function directly.")

