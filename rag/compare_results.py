"""Helper script to compare RAG test results."""

import json
import argparse
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()


def load_result(file_path: Path) -> dict:
    """Load a test result JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)


def compare_results(result1_path: Path, result2_path: Path):
    """Compare two test results and display side-by-side."""
    result1 = load_result(result1_path)
    result2 = load_result(result2_path)

    console.print(f"\n[bold]Comparing Results:[/bold]")
    console.print(f"File 1: {result1_path}")
    console.print(f"File 2: {result2_path}")
    console.print()

    # Compare metadata
    console.print("[bold cyan]Metadata Comparison:[/bold cyan]")
    console.print(f"Prompt Style:  [yellow]{result1.get('prompt_style', 'N/A')}[/yellow] vs [yellow]{result2.get('prompt_style', 'N/A')}[/yellow]")
    console.print(f"Row Count:     {result1.get('row_count', 'N/A')} vs {result2.get('row_count', 'N/A')}")
    console.print(f"Evidence Count: {result1.get('evidence_count', 'N/A')} vs {result2.get('evidence_count', 'N/A')}")
    console.print()

    # Show answers
    console.print(Panel(
        result1.get('answer', 'No answer'),
        title=f"[bold green]Answer 1: {result1.get('prompt_style', 'Unknown')}[/bold green]",
        border_style="green"
    ))
    console.print()

    console.print(Panel(
        result2.get('answer', 'No answer'),
        title=f"[bold blue]Answer 2: {result2.get('prompt_style', 'Unknown')}[/bold blue]",
        border_style="blue"
    ))
    console.print()

    # Compare lengths
    len1 = len(result1.get('answer', ''))
    len2 = len(result2.get('answer', ''))
    console.print(f"[bold]Answer Lengths:[/bold] {len1} chars vs {len2} chars (diff: {len2 - len1:+d})")


def compare_directory(dir_path: Path):
    """Compare all results in a directory (strict vs analytical vs conversational)."""
    styles = ["strict", "analytical", "conversational"]
    results = {}

    for style in styles:
        result_file = dir_path / f"{style}_result.json"
        if result_file.exists():
            results[style] = load_result(result_file)

    if not results:
        console.print(f"[red]No result files found in {dir_path}[/red]")
        return

    console.print(f"\n[bold]Comparing All Styles in {dir_path}:[/bold]\n")

    # Show each answer
    for style, result in results.items():
        answer = result.get('answer', 'No answer')
        console.print(Panel(
            answer,
            title=f"[bold]{style.upper()}[/bold] ({len(answer)} chars)",
            border_style="cyan"
        ))
        console.print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare RAG test results")
    parser.add_argument(
        "path1",
        type=Path,
        help="First result file or directory with comparison.json"
    )
    parser.add_argument(
        "path2",
        type=Path,
        nargs="?",
        help="Second result file (optional if path1 is a directory)"
    )
    args = parser.parse_args()

    if args.path1.is_dir():
        # Compare all styles in the directory
        compare_directory(args.path1)
    elif args.path2:
        # Compare two specific files
        compare_results(args.path1, args.path2)
    else:
        console.print("[red]Error: Provide either a directory or two files to compare[/red]")
