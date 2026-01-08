#!/usr/bin/env python3
"""
QA script for trajectory completeness.

Verifies that trajectories built from resolutions contain all the documents
referenced in the resolution's related_documents and agenda fields.
"""

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List, Any, Set
from collections import defaultdict

from .trace_genealogy import UNDocumentIndex, DocumentGenealogy
from .build_trajectory import TrajectoryBuilder


class TrajectoryQA:
    """Quality assurance for trajectory building."""

    def __init__(self, index: UNDocumentIndex):
        self.index = index
        self.genealogy = DocumentGenealogy(index)
        self.builder = TrajectoryBuilder(index)

        # Track results
        self.results = []
        self.missing_documents = defaultdict(list)

    def check_resolution(self, resolution_symbol: str) -> Dict[str, Any]:
        """Check if trajectory has all expected documents for a resolution."""

        # Load resolution data
        resolution = self.index.load(resolution_symbol)
        if not resolution:
            return {
                "resolution": resolution_symbol,
                "status": "error",
                "error": "Resolution not found",
                "expected": {},
                "found": {},
                "missing": {}
            }

        # Extract expected documents from resolution metadata
        expected = self._extract_expected_documents(resolution)

        # Build trajectory and extract found documents
        tree = self.genealogy.trace_backwards(resolution_symbol)
        if "error" in tree:
            return {
                "resolution": resolution_symbol,
                "status": "error",
                "error": tree["error"],
                "expected": expected,
                "found": {},
                "missing": expected
            }

        found = self._extract_found_documents(tree)

        # Compare expected vs found
        missing = self._compare_documents(expected, found)

        # Determine status
        status = "complete" if all(len(m) == 0 for m in missing.values()) else "incomplete"

        result = {
            "resolution": resolution_symbol,
            "status": status,
            "expected": expected,
            "found": found,
            "missing": missing,
            "expected_count": sum(len(v) for v in expected.values()),
            "found_count": sum(len(v) for v in found.values()),
            "missing_count": sum(len(v) for v in missing.values())
        }

        return result

    def _extract_expected_documents(self, resolution: Dict[str, Any]) -> Dict[str, Set[str]]:
        """Extract expected documents from resolution metadata."""
        expected = {
            "drafts": set(),
            "committee_reports": set(),
            "meeting_records": set(),
            "agenda_items": set()
        }

        # Related documents
        related = resolution.get("related_documents", {})

        for draft_ref in related.get("drafts", []):
            symbol = draft_ref.get("text")
            if symbol:
                expected["drafts"].add(self.index._normalize_symbol(symbol))

        for report_ref in related.get("committee_reports", []):
            symbol = report_ref.get("text")
            if symbol:
                expected["committee_reports"].add(self.index._normalize_symbol(symbol))

        for meeting_ref in related.get("meeting_records", []):
            symbol = meeting_ref.get("text")
            if symbol:
                expected["meeting_records"].add(self.index._normalize_symbol(symbol))

        # Agenda items
        for agenda_item in resolution.get("agenda", []):
            symbol = agenda_item.get("agenda_symbol")
            if symbol:
                expected["agenda_items"].add(self.index._normalize_symbol(symbol))

        return expected

    def _extract_found_documents(self, tree: Dict[str, Any]) -> Dict[str, Set[str]]:
        """Extract documents found in trajectory tree."""
        found = {
            "drafts": set(),
            "committee_reports": set(),
            "meeting_records": set(),
            "agenda_items": set()
        }

        # Drafts
        for draft in tree.get("drafts", []):
            if draft.get("found"):
                symbol = draft.get("symbol")
                if symbol:
                    found["drafts"].add(self.index._normalize_symbol(symbol))

        # Committee reports
        for report in tree.get("committee_reports", []):
            if report.get("found"):
                symbol = report.get("symbol")
                if symbol:
                    found["committee_reports"].add(self.index._normalize_symbol(symbol))

        # Meeting records
        for meeting in tree.get("meeting_records", []):
            if meeting.get("found"):
                symbol = meeting.get("symbol")
                if symbol:
                    found["meeting_records"].add(self.index._normalize_symbol(symbol))

        # Agenda items
        for item in tree.get("agenda_items", []):
            if item.get("found"):
                symbol = item.get("symbol")
                if symbol:
                    found["agenda_items"].add(self.index._normalize_symbol(symbol))

        return found

    def _compare_documents(self, expected: Dict[str, Set[str]], found: Dict[str, Set[str]]) -> Dict[str, List[str]]:
        """Compare expected vs found documents."""
        missing = {}

        for doc_type in expected.keys():
            missing_docs = expected[doc_type] - found[doc_type]
            missing[doc_type] = sorted(list(missing_docs))

        return missing

    def run_qa(self, resolutions: List[str]) -> Dict[str, Any]:
        """Run QA on multiple resolutions."""
        print(f"\n🔍 Running QA on {len(resolutions)} resolutions...\n")

        results = []
        complete_count = 0
        incomplete_count = 0
        error_count = 0

        for i, resolution_symbol in enumerate(resolutions, 1):
            print(f"[{i}/{len(resolutions)}] Checking {resolution_symbol}...", end=" ")

            result = self.check_resolution(resolution_symbol)
            results.append(result)

            if result["status"] == "complete":
                print("✅ Complete")
                complete_count += 1
            elif result["status"] == "incomplete":
                print(f"⚠️  Incomplete (missing {result['missing_count']} documents)")
                incomplete_count += 1
                self._print_missing(result)
            else:
                print(f"❌ Error: {result.get('error')}")
                error_count += 1

        # Summary
        summary = {
            "total_checked": len(resolutions),
            "complete": complete_count,
            "incomplete": incomplete_count,
            "errors": error_count,
            "results": results
        }

        print("\n" + "="*80)
        print("📊 QA SUMMARY")
        print("="*80)
        print(f"Total resolutions checked: {summary['total_checked']}")
        print(f"  ✅ Complete:    {summary['complete']} ({100*complete_count/len(resolutions):.1f}%)")
        print(f"  ⚠️  Incomplete:  {summary['incomplete']} ({100*incomplete_count/len(resolutions):.1f}%)")
        print(f"  ❌ Errors:      {summary['errors']} ({100*error_count/len(resolutions):.1f}%)")

        # Document type breakdown
        print("\n📋 MISSING DOCUMENT BREAKDOWN")
        print("-"*80)
        missing_by_type = defaultdict(int)
        for result in results:
            if result["status"] == "incomplete":
                for doc_type, missing_docs in result["missing"].items():
                    missing_by_type[doc_type] += len(missing_docs)

        if missing_by_type:
            for doc_type, count in sorted(missing_by_type.items()):
                print(f"  {doc_type:20s}: {count} missing")
        else:
            print("  No missing documents!")

        return summary

    def _print_missing(self, result: Dict[str, Any]):
        """Print missing documents for a result."""
        for doc_type, missing_docs in result["missing"].items():
            if missing_docs:
                for doc in missing_docs:
                    print(f"      Missing {doc_type}: {doc}")


def get_sample_resolutions(data_dir: Path, sample_size: int = 15) -> List[str]:
    """Get a sample of resolution symbols."""
    resolution_dir = data_dir / "resolutions"

    if not resolution_dir.exists():
        return []

    # Get all resolution files
    resolution_files = list(resolution_dir.glob("A_RES_78_*.json"))

    # Sample randomly
    if len(resolution_files) > sample_size:
        resolution_files = random.sample(resolution_files, sample_size)

    # Extract symbols from files
    symbols = []
    for file_path in resolution_files:
        try:
            with open(file_path) as f:
                data = json.load(f)
                symbol = data.get("metadata", {}).get("symbol")
                if symbol:
                    symbols.append(symbol)
        except Exception as e:
            print(f"Warning: Failed to load {file_path}: {e}")

    return sorted(symbols)


def main():
    parser = argparse.ArgumentParser(
        description="QA check for UN document trajectories"
    )
    parser.add_argument(
        "-r", "--resolutions",
        nargs="+",
        help="Specific resolution symbols to check (e.g., A/RES/78/220 A/RES/78/300)"
    )
    parser.add_argument(
        "-n", "--sample-size",
        type=int,
        default=15,
        help="Number of random resolutions to sample if --resolutions not specified (default: 15)"
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help="Root directory for parsed HTML data (default: data/parsed/html)"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output JSON file for QA results"
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Random seed for reproducible sampling"
    )

    args = parser.parse_args()

    # Set random seed if provided
    if args.seed is not None:
        random.seed(args.seed)

    # Build index
    data_root = args.data_root or Path("data/parsed/html")
    print(f"Building document index from {data_root}...")
    index = UNDocumentIndex(data_root)
    print(f"Indexed {len(index.documents)} documents")

    # Get resolutions to check
    if args.resolutions:
        resolutions = args.resolutions
        print(f"Checking {len(resolutions)} specified resolutions")
    else:
        resolutions = get_sample_resolutions(data_root, args.sample_size)
        print(f"Sampled {len(resolutions)} random resolutions")

    if not resolutions:
        print("❌ No resolutions to check!")
        return

    # Run QA
    qa = TrajectoryQA(index)
    summary = qa.run_qa(resolutions)

    # Save results if requested
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"\n💾 Detailed results saved to {args.output}")


if __name__ == "__main__":
    main()
