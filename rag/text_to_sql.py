"""Text-to-SQL service using OpenAI to convert natural language queries to SQL."""

import os
import sys
import logging
import re
from pathlib import Path
from typing import Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Set up logging
from utils.logging_config import get_logger
logger = get_logger(__name__, log_file="text_to_sql_generation.log")

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
   - symbol (text, unique, indexed) - Document identifier with slashes (e.g., "A/RES/78/220", "A/C.3/78/L.41", "A/78/PV.16")
   - doc_type (text, indexed) - Document type. MUST use exact values:
     * 'resolution' - UN resolutions (e.g., A/RES/78/220)
     * 'draft' - Draft resolutions (e.g., A/78/L.2, A/C.3/78/L.41)
     * 'meeting' - Plenary meetings (e.g., A/78/PV.16)
     * 'committee_report' - Committee reports
     * 'agenda_item' - Agenda items (e.g., A/78/251_item_125)
   - session (integer, indexed) - Session number (e.g., 78, 79)
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
   - vote_type (text) - Vote type. MUST use exact values:
     * 'in_favour' - yes votes
     * 'against' - no votes
     * 'abstaining' - abstentions
   - vote_context (text) - Voting context. MUST use exact values:
     * 'plenary' - plenary votes
     * 'committee' - committee votes
   - created_at (timestamp)

4. document_relationships
   - id (integer, primary key)
   - source_id (integer, foreign key to documents.id, indexed)
   - target_id (integer, foreign key to documents.id, indexed)
   - relationship_type (text, indexed) - Relationship type. MUST use exact values:
     * 'draft_of' - draft → resolution
     * 'committee_report_for' - committee report → resolution
     * 'meeting_record_for' - meeting → resolution
     * 'agenda_item_for' - agenda item → resolution
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
   - reference_type (text) - Reference type. Common values:
     * 'mentioned' - document mentioned in utterance
     * 'voting_on' - utterance is about voting on this document
   - context (text) - sentence/context where document was mentioned
   - created_at (timestamp)

7. subjects
   - id (integer, primary key)
   - name (text, unique, indexed) - e.g. "SUSTAINABLE DEVELOPMENT", "HUMAN RIGHTS"

8. document_subjects
   - document_id (integer, foreign key to documents.id, primary key)
   - subject_id (integer, foreign key to subjects.id, primary key)

9. sponsorships
   - id (integer, primary key)
   - document_id (integer, foreign key to documents.id, indexed)
   - actor_id (integer, foreign key to actors.id, indexed)
   - sponsorship_type (text) - 'initial' (from authors list) or 'additional' (from meeting notes)
   - created_at (timestamp)

Example document symbols:
- Resolutions: A/RES/78/3, A/RES/78/220, A/RES/78/271
- Drafts: A/78/L.2, A/C.3/78/L.41
- Meetings: A/78/PV.16, A/78/PV.93
- Agenda items: A/78/251_item_125

Common query patterns:
- Join documents with votes: JOIN votes ON votes.document_id = documents.id
- Join votes with actors: JOIN actors ON actors.id = votes.actor_id
- Join documents with relationships: JOIN document_relationships ON document_relationships.source_id = documents.id OR document_relationships.target_id = documents.id
- Join utterances with meetings: JOIN documents ON documents.id = utterances.meeting_id WHERE documents.doc_type = 'meeting'
- Join utterances with actors: JOIN actors ON actors.id = utterances.speaker_actor_id
- Join documents with subjects: JOIN document_subjects ON document_subjects.document_id = documents.id JOIN subjects ON subjects.id = document_subjects.subject_id
- Join documents with sponsors: JOIN sponsorships ON sponsorships.document_id = documents.id JOIN actors ON actors.id = sponsorships.actor_id

Note: Use ILIKE for case-insensitive text matching. Use JSONB operators (->, ->>) to access metadata fields.
"""

SYSTEM_PROMPT = """You are a PostgreSQL expert. Convert natural language questions into valid PostgreSQL SELECT queries.

CRITICAL: Use EXACT enum values from the schema. Do NOT use variations:
- doc_type: 'resolution' (NOT 'resolutions'), 'draft', 'meeting', 'committee_report', 'agenda_item'
- vote_type: 'in_favour' (NOT 'yes'), 'against' (NOT 'no'), 'abstaining'
- relationship_type: 'draft_of', 'committee_report_for', 'meeting_record_for', 'agenda_item_for'
- Document symbols use slashes: 'A/RES/78/220' (NOT 'A_RES_78_220')

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

Example queries:
- "Show me all resolutions from session 78"
  → SELECT symbol, title FROM documents WHERE doc_type = 'resolution' AND session = 78 LIMIT 100;

- "Which countries voted against A/RES/78/220?"
  → SELECT actors.name FROM votes JOIN actors ON votes.actor_id = actors.id JOIN documents ON votes.document_id = documents.id WHERE documents.symbol = 'A/RES/78/220' AND votes.vote_type = 'against';

- "Find all drafts that became resolutions"
  → SELECT d1.symbol as draft, d2.symbol as resolution FROM document_relationships dr JOIN documents d1 ON dr.source_id = d1.id JOIN documents d2 ON dr.target_id = d2.id WHERE dr.relationship_type = 'draft_of' LIMIT 100;

The database contains UN General Assembly documents, votes, actors (countries), and meeting utterances."""


class SQLValidationError(Exception):
    """Raised when SQL query fails validation checks."""
    pass


def validate_sql(sql: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that SQL query is read-only and safe to execute.

    Args:
        sql: SQL query string to validate

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.

    Raises:
        SQLValidationError: If query contains forbidden operations
    """
    if not sql or not sql.strip():
        return False, "Empty SQL query"

    sql_upper = sql.upper()

    # List of forbidden write operations and DDL/DCL statements
    FORBIDDEN_KEYWORDS = [
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
        'TRUNCATE', 'REPLACE', 'MERGE', 'GRANT', 'REVOKE',
        'EXECUTE', 'EXEC', 'CALL',  # Stored procedure execution
        'SET', 'RESET',  # Session/config changes
        'COPY',  # Data import/export
        'VACUUM', 'ANALYZE',  # Maintenance operations
        'LOCK',  # Table locking
        'COMMENT',  # Metadata changes
    ]

    # Check for forbidden keywords (not in strings)
    # Simple approach: remove single-quoted strings first, then check
    sql_no_strings = re.sub(r"'[^']*'", "", sql_upper)

    for keyword in FORBIDDEN_KEYWORDS:
        # Use word boundary to avoid false positives (e.g., "INSERT" in "INSERTION")
        if re.search(rf'\b{keyword}\b', sql_no_strings):
            return False, f"Forbidden operation detected: {keyword}. Only read-only queries (SELECT, WITH, EXPLAIN) are allowed."

    # Check that query starts with allowed operations
    ALLOWED_START_KEYWORDS = ['SELECT', 'WITH', 'EXPLAIN', '(']  # ( allows for subqueries

    stripped_sql = sql_upper.strip()
    if not any(stripped_sql.startswith(keyword) for keyword in ALLOWED_START_KEYWORDS):
        return False, f"Query must start with SELECT, WITH, or EXPLAIN. Found: {sql[:50]}..."

    # Check for multiple statements (SQL injection risk)
    # Count semicolons that aren't in strings
    semicolons_outside_strings = sql_no_strings.count(';')
    # Allow one trailing semicolon
    if semicolons_outside_strings > 1:
        return False, "Multiple SQL statements detected. Only single queries are allowed."

    # Check for dangerous functions that could be used for side effects
    DANGEROUS_FUNCTIONS = [
        'PG_SLEEP',  # Time-based attacks
        'PG_READ_FILE', 'PG_WRITE_FILE',  # File system access
        'DBLINK', 'DBLINK_EXEC',  # Remote database access
        'LO_IMPORT', 'LO_EXPORT',  # Large object file access
    ]

    for func in DANGEROUS_FUNCTIONS:
        if re.search(rf'\b{func}\b', sql_no_strings):
            return False, f"Forbidden function detected: {func}"

    # Check for SQL comments that might hide malicious code
    # Block inline comments with -- but allow /* */ style (though unusual in generated SQL)
    if re.search(r'--', sql):
        return False, "SQL comments (--) are not allowed"

    return True, None


def generate_sql(natural_language_query: str, model: str = "gpt-5-mini-2025-08-07", validate: bool = True) -> Optional[str]:
    """
    Convert a natural language query to SQL using OpenAI.

    Args:
        natural_language_query: The natural language question
        model: OpenAI model to use (default: gpt-5-mini-2025-08-07 for cost/speed)
        validate: Whether to validate the generated SQL for security (default: True)

    Returns:
        SQL query string or None if generation fails

    Raises:
        SQLValidationError: If generated SQL fails validation checks
        RuntimeError: If SQL generation fails
    """
    logger.info(f"Generating SQL from natural language query (model: {model}): {natural_language_query}")

    client = get_client()

    try:
        # Use standard OpenAI chat completions API
        prompt = SYSTEM_PROMPT + "\n\n" + SCHEMA_DESCRIPTION + f"\n\nConvert this question to SQL: {natural_language_query}"
        result = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            # temperature=0.3,
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

        # Validate SQL if requested
        if validate:
            is_valid, error_msg = validate_sql(sql_query)
            if not is_valid:
                logger.error(f"SQL validation failed: {error_msg}")
                logger.error(f"Rejected SQL: {sql_query}")
                raise SQLValidationError(f"Generated SQL failed validation: {error_msg}")
            logger.info("SQL validation passed")

        return sql_query

    except SQLValidationError:
        # Re-raise validation errors
        raise
    except Exception as e:
        logger.error(f"Failed to generate SQL: {str(e)}", exc_info=True)
        raise RuntimeError(f"Failed to generate SQL: {str(e)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert natural language to SQL")
    parser.add_argument("query", help="Natural language query")
    parser.add_argument("--model", "-m", default="gpt-5-mini-2025-08-07", help="OpenAI model to use")
    parser.add_argument("--no-validate", action="store_true", help="Skip SQL validation (not recommended)")
    args = parser.parse_args()

    try:
        sql = generate_sql(args.query, args.model, validate=not args.no_validate)
        print(sql)
    except SQLValidationError as e:
        print(f"Validation Error: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
