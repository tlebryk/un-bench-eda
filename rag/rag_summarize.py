"""RAG summarization service using OpenAI to summarize SQL query results."""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Set up logging
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "rag_summarize.log"

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

# Maximum number of results to include in summarization
MAX_RESULTS_FOR_SUMMARIZATION = 5


def get_client():
    """Get or create OpenAI client."""
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables. Please set it in your .env file.")
        _client = OpenAI(api_key=api_key)
    return _client


def extract_text_fields(query_results: Dict[str, Any]) -> List[str]:
    """
    Extract text content from query results for summarization.
    
    Prioritizes:
    1. 'text' column (for utterances)
    2. 'doc_metadata' JSONB field with 'text' key (for resolutions/documents)
    3. 'title' column as fallback
    
    Args:
        query_results: Result dictionary from execute_sql with 'columns' and 'rows'
    
    Returns:
        List of text strings (limited to MAX_RESULTS_FOR_SUMMARIZATION)
    """
    if not query_results.get("rows"):
        return []
    
    texts = []
    rows = query_results["rows"][:MAX_RESULTS_FOR_SUMMARIZATION]
    
    for row in rows:
        text_content = None
        
        # Priority 1: Direct 'text' column (for utterances)
        if "text" in row:
            text_content = row["text"].get("full", "")
        
        # Priority 2: 'doc_metadata' JSONB with 'text' key (for resolutions)
        elif "doc_metadata" in row:
            metadata_str = row["doc_metadata"].get("full", "")
            if metadata_str:
                try:
                    metadata = json.loads(metadata_str)
                    if isinstance(metadata, dict) and "text" in metadata:
                        text_content = metadata["text"]
                except (json.JSONDecodeError, TypeError):
                    pass
        
        if text_content and text_content.strip():
            texts.append(text_content.strip())
    
    return texts


def summarize_results(
    query_results: Dict[str, Any],
    original_question: str,
    model: str = "gpt-5-mini-2025-08-07"
) -> str:
    """
    Summarize SQL query results using RAG (Retrieval-Augmented Generation).
    
    Extracts text content from results and feeds it to an LLM along with the
    original question to generate a contextual summary.
    
    Args:
        query_results: Result dictionary from execute_sql
        original_question: The original natural language question that generated the query
        model: OpenAI model to use (default: gpt-5-mini-2025-08-07)
    
    Returns:
        Summary string, or error message if summarization fails
    """
    logger.info(f"Summarizing query results (model: {model}) for question: {original_question}")
    
    # Extract text fields
    texts = extract_text_fields(query_results)
    
    if not texts:
        logger.warning("No text content found in query results for summarization")
        return "No results with text content found to summarize."
    
    logger.info(f"Extracted {len(texts)} text fields for summarization")
    
    # Build prompt
    texts_section = "\n\n---\n\n".join([f"Result {i+1}:\n{text}" for i, text in enumerate(texts)])
    
    prompt = f"""You are analyzing UN General Assembly documents and meeting records.

Original question: {original_question}

The following text content was retrieved from the database query results. Please provide a concise summary that directly addresses the original question.

{texts_section}

Please provide a summary that:
1. Directly answers the original question
2. Highlights key points from the retrieved content
3. Is concise but informative (2-4 sentences)
4. Focuses on the most relevant information to the question

Summary:"""
    
    client = get_client()
    
    try:
        result = client.responses.create(
            model=model,
            input=prompt,
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
        )
        
        summary = result.output_text.strip()
        logger.info(f"Successfully generated summary (length: {len(summary)} chars)")
        
        return summary
    
    except Exception as e:
        logger.error(f"Failed to summarize results: {str(e)}", exc_info=True)
        raise RuntimeError(f"Failed to summarize results: {str(e)}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Summarize SQL query results using RAG")
    parser.add_argument("question", help="Original natural language question")
    parser.add_argument("--model", default="gpt-5-mini-2025-08-07", help="OpenAI model to use")
    args = parser.parse_args()
    
    # For CLI usage, would need to pass query results as JSON
    # This is mainly for testing
    print("This module is designed to be used programmatically.")
    print("Use summarize_results(query_results, question) function directly.")

