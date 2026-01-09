"""Test RAG Q&A end-to-end with configurable prompts."""

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from rag.text_to_sql import generate_sql
from rag.rag_qa import answer_question
from rag.prompt_config import load_prompt_config
from sqlalchemy import create_engine, text

# Load environment variables
load_dotenv()


def execute_sql(sql_query: str) -> Dict[str, Any]:
    """
    Execute SQL query for testing.
    Uses DATABASE_URL from environment, with helpful error if not set.
    """
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL not set. For local testing with Docker on port 5433:\n"
            "export DATABASE_URL='postgresql://un_user:un_password@localhost:5433/un_documents'\n"
            "Or set it in your .env file."
        )

    # Create engine for this test session
    engine = create_engine(database_url)

    with engine.connect() as connection:
        result = connection.execute(text(sql_query))
        columns = list(result.keys())
        rows = result.fetchall()

    # Convert to simple dict format for RAG
    simple_rows = []
    for row in rows:
        row_dict = dict(row._mapping)
        simple_rows.append(row_dict)

    return {
        "columns": columns,
        "rows": simple_rows,
        "row_count": len(rows),
        "truncated": False
    }

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_rag_query(
    question: str,
    prompt_style: str = "analytical",
    model: str = "gpt-5-mini-2025-08-07",
    output_file: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Run a complete RAG query end-to-end.

    Args:
        question: Natural language question
        prompt_style: Prompt style from config ("strict" or "analytical")
        model: OpenAI model to use
        output_file: Optional file to save results

    Returns:
        Dictionary with question, sql, results, and answer
    """
    logger.info(f"Running RAG query: {question}")
    logger.info(f"Prompt style: {prompt_style}, Model: {model}")

    # Step 1: Generate SQL
    logger.info("Step 1: Generating SQL...")
    sql_query = generate_sql(question, model=model)
    logger.info(f"Generated SQL: {sql_query}")

    # Step 2: Execute SQL
    logger.info("Step 2: Executing SQL...")
    query_results = execute_sql(sql_query)
    row_count = len(query_results.get("rows", []))
    logger.info(f"Retrieved {row_count} rows")

    # Step 3: Answer with RAG
    logger.info(f"Step 3: Generating answer with {prompt_style} prompt...")
    answer_result = answer_question(
        query_results=query_results,
        original_question=question,
        sql_query=sql_query,
        model=model,
        prompt_style=prompt_style
    )

    # Compile results
    result = {
        "question": question,
        "prompt_style": prompt_style,
        "model": model,
        "sql_query": sql_query,
        "row_count": row_count,
        "answer": answer_result["answer"],
        "sources": answer_result.get("sources", []),
        "evidence_count": len(answer_result.get("evidence", []))
    }

    # Save to file if requested
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        logger.info(f"Saved results to {output_file}")

    return result


def compare_prompt_styles(
    question: str,
    model: str = "gpt-5-mini-2025-08-07",
    output_dir: Optional[Path] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Run the same query with different prompt styles and compare.

    Args:
        question: Natural language question
        model: OpenAI model to use
        output_dir: Optional directory to save comparison results

    Returns:
        Dictionary with results for each prompt style
    """
    styles = ["strict", "analytical"]
    results = {}

    for style in styles:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing with {style.upper()} prompt style")
        logger.info(f"{'='*60}\n")

        output_file = None
        if output_dir:
            output_file = output_dir / f"{style}_result.json"

        results[style] = run_rag_query(
            question=question,
            prompt_style=style,
            model=model,
            output_file=output_file
        )

        # Print answer
        print(f"\n{'='*60}")
        print(f"{style.upper()} ANSWER:")
        print(f"{'='*60}")
        print(results[style]["answer"])
        print()

    # Save comparison if output_dir provided
    if output_dir:
        comparison_file = output_dir / "comparison.json"
        with open(comparison_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Saved comparison to {comparison_file}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test RAG Q&A end-to-end")
    parser.add_argument("question", help="Natural language question")
    parser.add_argument(
        "--style",
        choices=["strict", "analytical", "compare"],
        default="analytical",
        help="Prompt style to use (or 'compare' to test both)"
    )
    parser.add_argument(
        "--model",
        default="gpt-5-mini-2025-08-07",
        help="OpenAI model to use"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output directory for results"
    )
    args = parser.parse_args()

    try:
        if args.style == "compare":
            results = compare_prompt_styles(
                question=args.question,
                model=args.model,
                output_dir=args.output
            )
        else:
            result = run_rag_query(
                question=args.question,
                prompt_style=args.style,
                model=args.model,
                output_file=args.output / "result.json" if args.output else None
            )
            print(f"\n{'='*60}")
            print("ANSWER:")
            print(f"{'='*60}")
            print(result["answer"])
            print(f"\nSources: {', '.join(result['sources'][:10])}")
            if len(result['sources']) > 10:
                print(f"... and {len(result['sources']) - 10} more")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise
