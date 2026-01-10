"""Text-to-SQL service using OpenAI to convert natural language queries to SQL."""

import os
import sys
import logging
import re
from pathlib import Path
from typing import Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI
import yaml
from jinja2 import Template

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

# Load prompts from YAML config
def load_text_to_sql_config():
    """Load text-to-SQL configuration from YAML file with Jinja2 support."""
    config_path = Path(__file__).parent / "prompts" / "text_to_sql.yaml"
    with open(config_path, 'r') as f:
        content = f.read()
    
    # Render with Jinja2 using environment variables
    template = Template(content)
    rendered_content = template.render(env=os.environ)
    
    return yaml.safe_load(rendered_content)

# Load configuration
_config = load_text_to_sql_config()
SCHEMA_DESCRIPTION = _config['schema_description']
SYSTEM_PROMPT = _config['system_prompt']
DEFAULT_MODEL = _config.get('model', 'gpt-5-mini-2025-08-07')


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


def generate_sql(natural_language_query: str, model: Optional[str] = None, validate: bool = True) -> Optional[str]:
    """
    Convert a natural language query to SQL using OpenAI.

    Args:
        natural_language_query: The natural language question
        model: OpenAI model to use (default: configured model)
        validate: Whether to validate the generated SQL for security (default: True)

    Returns:
        SQL query string or None if generation fails

    Raises:
        SQLValidationError: If generated SQL fails validation checks
        RuntimeError: If SQL generation fails
    """
    if model is None:
        model = DEFAULT_MODEL

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
    parser.add_argument("--model", "-m", default=None, help="OpenAI model to use (default: configured model)")
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
