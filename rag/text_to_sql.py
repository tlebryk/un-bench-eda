"""Text-to-SQL service using OpenAI to convert natural language queries to SQL."""

import os
import sys
import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Set up logging (use project root logs directory)
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "text_to_sql_generation.log"

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

def get_client():
    """Get or create OpenAI client."""
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables. Please set it in your .env file.")
        _client = OpenAI(api_key=api_key)
    return _client

# Database schema description for the LLM
SCHEMA_DESCRIPTION = """
PostgreSQL database schema for UN General Assembly documents:

Tables:
1. documents
   - id (integer, primary key)
   - symbol (text, unique, indexed) - e.g., "A/RES/78/220", "A/C.3/78/L.41"
   - doc_type (text, indexed) - 'resolution', 'draft', 'meeting', 'committee_report', 'agenda'
   - session (integer, indexed) - e.g., 78
   - title (text) - document title
   - date (date)
   - body_text (text) - full text content from PDFs (available for resolutions, drafts; use for text search and summarization)
   - doc_metadata (jsonb) - flexible metadata stored as JSON
   - created_at (timestamp)

2. actors
   - id (integer, primary key)
   - name (text, unique, indexed) - country or organization name
   - actor_type (text) - 'country', 'observer', 'un_official'
   - created_at (timestamp)

3. votes
   - id (integer, primary key)
   - document_id (integer, foreign key to documents.id, indexed)
   - actor_id (integer, foreign key to actors.id, indexed)
   - vote_type (text) - 'in_favour', 'against', 'abstaining'
   - vote_context (text) - 'plenary', 'committee'
   - created_at (timestamp)

4. document_relationships
   - id (integer, primary key)
   - source_id (integer, foreign key to documents.id, indexed)
   - target_id (integer, foreign key to documents.id, indexed)
   - relationship_type (text, indexed) - 'draft_of', 'committee_report_for', 'meeting_for', 'agenda_item'
   - rel_metadata (jsonb)
   - created_at (timestamp)

5. utterances
   - id (integer, primary key)
   - meeting_id (integer, foreign key to documents.id, indexed)
   - section_id (text) - e.g., "A/78/PV.80_section_11"
   - agenda_item_number (text, indexed) - e.g., "11", "20"
   - speaker_actor_id (integer, foreign key to actors.id, nullable, indexed)
   - speaker_name (text) - parsed name (e.g., "El-Sonni")
   - speaker_role (text) - e.g., "The President", "delegate"
   - speaker_raw (text) - original speaker string from PDF
   - speaker_affiliation (text) - country or organization
   - text (text) - utterance content
   - word_count (integer)
   - position_in_meeting (integer)
   - position_in_section (integer)
   - utterance_metadata (jsonb)
   - created_at (timestamp)

6. utterance_documents
   - id (integer, primary key)
   - utterance_id (integer, foreign key to utterances.id, indexed)
   - document_id (integer, foreign key to documents.id, indexed)
   - reference_type (text) - 'mentioned', 'about', 'voting_on', etc.
   - context (text) - sentence/context where document was mentioned
   - created_at (timestamp)

Common query patterns:
- Join documents with votes: JOIN votes ON votes.document_id = documents.id
- Join votes with actors: JOIN actors ON actors.id = votes.actor_id
- Join documents with relationships: JOIN document_relationships ON document_relationships.source_id = documents.id OR document_relationships.target_id = documents.id
- Join utterances with meetings: JOIN documents ON documents.id = utterances.meeting_id WHERE documents.doc_type = 'meeting'
- Join utterances with actors: JOIN actors ON actors.id = utterances.speaker_actor_id

Note: Use ILIKE for case-insensitive text matching. Use JSONB operators (->, ->>) to access metadata fields.
"""

SYSTEM_PROMPT = """You are a PostgreSQL expert. Convert natural language questions into valid PostgreSQL SELECT queries.

Rules:
1. Only generate SELECT, WITH, or EXPLAIN queries (read-only)
2. Use proper JOIN syntax
3. Use ILIKE for case-insensitive text searches
4. Always include appropriate WHERE clauses
5. Use LIMIT when appropriate (default to 100 if not specified)
6. Return only the SQL query, no explanations or markdown formatting
7. Use proper table and column names from the schema
8. For country/actor name matching, use ILIKE with patterns like '%country name%' to handle variations
9. Use proper date comparisons and ordering
10. When querying JSONB fields, use -> for objects and ->> for text values
11. For document text content, use the 'body_text' column (contains full PDF text for resolutions/drafts)
12. For meeting statements, query the 'utterances' table which has a 'text' column
13. Avoid selecting the large doc_metadata or body_text fields unless specifically requested (use title for previews)

The database contains UN General Assembly documents, votes, actors (countries), and meeting utterances."""


def generate_sql(natural_language_query: str, model: str = "gpt-4o-mini") -> Optional[str]:
    """
    Convert a natural language query to SQL using OpenAI.
    
    Args:
        natural_language_query: The natural language question
        model: OpenAI model to use (default: gpt-5-mini-2025-08-07 for cost/speed)
    
    Returns:
        SQL query string or None if generation fails
    """
    logger.info(f"Generating SQL from natural language query (model: {model}): {natural_language_query}")
    
    client = get_client()
    
    try:
        # Use standard OpenAI chat completions API
        prompt = SYSTEM_PROMPT + "\n\n" + SCHEMA_DESCRIPTION + f"\n\nConvert this question to SQL: {natural_language_query}"
        result = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )

        sql_query = result.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        if sql_query.startswith("```sql"):
            sql_query = sql_query[6:]
        if sql_query.startswith("```"):
            sql_query = sql_query[3:]
        if sql_query.endswith("```"):
            sql_query = sql_query[:-3]
        
        sql_query = sql_query.strip()
        logger.info(f"Successfully generated SQL: {sql_query}")
        
        return sql_query
    
    except Exception as e:
        logger.error(f"Failed to generate SQL: {str(e)}", exc_info=True)
        raise RuntimeError(f"Failed to generate SQL: {str(e)}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert natural language to SQL")
    parser.add_argument("query", help="Natural language query")
    parser.add_argument("--model", default="gpt-5-nano-2025-08-07", help="OpenAI model to use")
    args = parser.parse_args()
    
    try:
        sql = generate_sql(args.query, args.model)
        print(sql)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
