"""Batch test runner for RAG queries."""

import argparse
import yaml
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from rag.test_rag_queries import run_rag_query, compare_prompt_styles
from rag.prompt_config import get_default_model


def load_test_queries(queries_file: Path) -> List[Dict[str, Any]]:
    """Load test queries from YAML file."""
    with open(queries_file, 'r') as f:
        data = yaml.safe_load(f)
    return data.get("queries", [])


def run_batch_test(
    queries_file: Path,
    prompt_style: str = "analytical",
    model: str = "gpt-5-mini-2025-08-07",
    output_dir: Path = None,
    compare: bool = False
):
    """
    Run batch tests on multiple queries.

    Args:
        queries_file: Path to YAML file with test queries
        prompt_style: Prompt style to use
        model: OpenAI model to use (default: configured model)
        output_dir: Directory to save results
        compare: If True, compare all prompt styles for each query
    """
    if model is None:
        model = get_default_model()

    queries = load_test_queries(queries_file)

    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(f"test_results_{timestamp}")

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running {len(queries)} test queries...")
    print(f"Output directory: {output_dir}")
    print(f"{'='*60}\n")

    results = []

    for i, query_config in enumerate(queries, 1):
        query_id = query_config["id"]
        question = query_config["question"]

        print(f"\n[{i}/{len(queries)}] Testing: {query_id}")
        print(f"Question: {question}")
        print("-" * 60)

        query_output_dir = output_dir / query_id

        try:
            if compare:
                result = compare_prompt_styles(
                    question=question,
                    model=model,
                    output_dir=query_output_dir
                )
            else:
                result = run_rag_query(
                    question=question,
                    prompt_style=prompt_style,
                    model=model,
                    output_file=query_output_dir / f"{prompt_style}_result.json"
                )

                # Print answer
                print(f"\nAnswer ({prompt_style}):")
                print(result["answer"])

            results.append({
                "query_id": query_id,
                "status": "success",
                "result": result
            })

        except Exception as e:
            print(f"\nERROR: {e}")
            results.append({
                "query_id": query_id,
                "status": "error",
                "error": str(e)
            })

        print("\n" + "="*60)

    # Print summary
    print(f"\n{'='*60}")
    print("BATCH TEST SUMMARY")
    print(f"{'='*60}")
    success_count = sum(1 for r in results if r["status"] == "success")
    print(f"Total queries: {len(results)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {len(results) - success_count}")
    print(f"\nResults saved to: {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run batch RAG tests")
    parser.add_argument(
        "-q", "--queries",
        type=Path,
        default=Path(__file__).parent / "test_queries.yaml",
        help="YAML file with test queries"
    )
    parser.add_argument(
        "--style",
        choices=["strict", "analytical", "conversational"],
        default="analytical",
        help="Prompt style to use"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="OpenAI model to use (default: configured model)"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output directory for results"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare all prompt styles for each query"
    )
    args = parser.parse_args()

    run_batch_test(
        queries_file=args.queries,
        prompt_style=args.style,
        model=args.model,
        output_dir=args.output,
        compare=args.compare
    )
