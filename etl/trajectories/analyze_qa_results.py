#!/usr/bin/env python3
"""
Analyze QA results to identify patterns in missing documents.
"""

import argparse
import json
from pathlib import Path
from collections import Counter
from typing import Dict, Any, List


def analyze_qa_results(results_file: Path) -> Dict[str, Any]:
    """Analyze QA results and generate insights."""

    with open(results_file) as f:
        data = json.load(f)

    results = data.get("results", [])

    analysis = {
        "summary": {
            "total_resolutions": data.get("total_checked", 0),
            "complete": data.get("complete", 0),
            "incomplete": data.get("incomplete", 0),
            "errors": data.get("errors", 0),
            "completion_rate": f"{100 * data.get('complete', 0) / max(data.get('total_checked', 1), 1):.1f}%"
        },
        "missing_documents_by_type": {},
        "most_common_missing": {},
        "incomplete_resolutions": []
    }

    # Count missing documents by type
    missing_by_type = {
        "drafts": [],
        "committee_reports": [],
        "meeting_records": [],
        "agenda_items": []
    }

    for result in results:
        if result.get("status") == "incomplete":
            analysis["incomplete_resolutions"].append({
                "resolution": result["resolution"],
                "missing_count": result["missing_count"],
                "missing": result["missing"]
            })

            for doc_type, missing_docs in result["missing"].items():
                missing_by_type[doc_type].extend(missing_docs)

    # Count frequency of missing documents
    for doc_type, missing_list in missing_by_type.items():
        counter = Counter(missing_list)
        analysis["missing_documents_by_type"][doc_type] = {
            "total_missing": len(missing_list),
            "unique_missing": len(counter)
        }
        analysis["most_common_missing"][doc_type] = counter.most_common(10)

    return analysis


def print_analysis(analysis: Dict[str, Any]):
    """Print analysis in readable format."""

    print("\n" + "="*80)
    print("📊 TRAJECTORY QA ANALYSIS")
    print("="*80)

    # Summary
    summary = analysis["summary"]
    print(f"\n📋 Summary:")
    print(f"  Total resolutions:   {summary['total_resolutions']}")
    print(f"  Complete:            {summary['complete']} ({summary['completion_rate']})")
    print(f"  Incomplete:          {summary['incomplete']}")
    print(f"  Errors:              {summary['errors']}")

    # Missing documents by type
    print(f"\n📄 Missing Documents by Type:")
    for doc_type, stats in analysis["missing_documents_by_type"].items():
        if stats["total_missing"] > 0:
            print(f"  {doc_type:20s}: {stats['total_missing']} missing ({stats['unique_missing']} unique)")

    # Most common missing documents
    print(f"\n🔍 Most Frequently Missing Documents:")
    for doc_type, common_docs in analysis["most_common_missing"].items():
        if common_docs:
            print(f"\n  {doc_type.upper()}:")
            for doc, count in common_docs:
                print(f"    {count:3d}x  {doc}")

    # Incomplete resolutions detail
    if analysis["incomplete_resolutions"]:
        print(f"\n⚠️  Incomplete Resolutions ({len(analysis['incomplete_resolutions'])}):")
        for res_info in analysis["incomplete_resolutions"][:10]:  # Show first 10
            print(f"  {res_info['resolution']:20s} - missing {res_info['missing_count']} document(s)")
            for doc_type, docs in res_info["missing"].items():
                if docs:
                    for doc in docs:
                        print(f"      • {doc_type}: {doc}")

        if len(analysis["incomplete_resolutions"]) > 10:
            print(f"\n  ... and {len(analysis['incomplete_resolutions']) - 10} more")

    print("\n" + "="*80)


def generate_missing_docs_list(analysis: Dict[str, Any], output_file: Path):
    """Generate a list of all unique missing documents."""

    missing_docs = set()

    for doc_type, common_docs in analysis["most_common_missing"].items():
        for doc, count in common_docs:
            missing_docs.add(doc)

    output = {
        "total_unique_missing": len(missing_docs),
        "missing_documents": sorted(list(missing_docs))
    }

    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"💾 Missing documents list saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze trajectory QA results"
    )
    parser.add_argument(
        "results_file",
        type=Path,
        help="Path to QA results JSON file"
    )
    parser.add_argument(
        "--export-missing",
        type=Path,
        help="Export list of missing documents to JSON file"
    )

    args = parser.parse_args()

    if not args.results_file.exists():
        print(f"❌ Error: {args.results_file} not found")
        return

    # Analyze results
    analysis = analyze_qa_results(args.results_file)

    # Print analysis
    print_analysis(analysis)

    # Export missing documents if requested
    if args.export_missing:
        generate_missing_docs_list(analysis, args.export_missing)


if __name__ == "__main__":
    main()
