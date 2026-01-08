#!/usr/bin/env python3
"""
DEPRECATED: Barely useful. 
Validate ETL pipeline completeness.

Checks that each step of the ETL pipeline completed successfully:
1. HTML files were downloaded for all metadata
2. All HTML files were parsed to JSON
3. All referenced documents in resolutions exist

Run this after the ETL pipeline to ensure data completeness.
"""

import argparse
from pathlib import Path
from typing import Dict, List
import json


class ETLValidator:
    """Validate ETL pipeline completeness."""

    def __init__(self, base_dir: Path = Path("data")):
        self.base_dir = base_dir
        self.errors = []
        self.warnings = []

    def validate_parsing_completeness(self, doc_type: str) -> bool:
        """Validate that all HTML files were parsed to JSON."""
        html_dir = self.base_dir / "documents" / "html" / doc_type
        json_dir = self.base_dir / "parsed" / "html" / doc_type

        if not html_dir.exists():
            self.warnings.append(f"HTML directory does not exist: {html_dir}")
            return True  # Not an error if directory doesn't exist

        if not json_dir.exists():
            self.errors.append(f"Parsed directory does not exist: {json_dir}")
            return False

        html_files = list(html_dir.glob("*.html"))
        json_files = list(json_dir.glob("*.json"))

        html_count = len(html_files)
        json_count = len(json_files)

        if html_count == 0:
            self.warnings.append(f"No HTML files found in {html_dir}")
            return True

        if json_count == 0:
            self.errors.append(f"No JSON files found in {json_dir} but {html_count} HTML files exist")
            return False

        if html_count != json_count:
            self.errors.append(
                f"Parsing incomplete for {doc_type}: "
                f"{html_count} HTML files but only {json_count} JSON files"
            )

            # Find which files are missing
            html_stems = {f.stem for f in html_files}
            json_stems = {f.stem for f in json_files}
            missing = html_stems - json_stems

            if missing and len(missing) <= 10:
                self.errors.append(f"  Missing parsed files: {', '.join(sorted(list(missing))[:10])}")
            elif missing:
                self.errors.append(f"  {len(missing)} files not parsed")

            return False

        print(f"✅ {doc_type}: {html_count} HTML files, {json_count} JSON files - COMPLETE")
        return True

    def validate_all_document_types(self) -> bool:
        """Validate parsing for all document types."""
        doc_types = [
            "resolutions",
            "committee-reports",
            "drafts",
            "meetings",
            "agenda"
        ]

        all_valid = True
        print("\n📊 VALIDATING PARSING COMPLETENESS")
        print("="*80)

        for doc_type in doc_types:
            if not self.validate_parsing_completeness(doc_type):
                all_valid = False

        return all_valid

    def validate_trajectory_completeness(self, sample_size: int = 20) -> bool:
        """Run trajectory QA to check if documents are properly linked."""
        from etl.trajectories.qa_trajectories import TrajectoryQA, get_sample_resolutions
        from etl.trajectories.trace_genealogy import UNDocumentIndex

        print("\n📊 VALIDATING TRAJECTORY COMPLETENESS")
        print("="*80)

        # Build index
        data_root = self.base_dir / "parsed" / "html"
        index = UNDocumentIndex(data_root)

        # Get sample resolutions
        resolutions = get_sample_resolutions(data_root, sample_size=sample_size)

        if not resolutions:
            self.warnings.append("No resolutions found for trajectory validation")
            return True

        # Run QA
        qa = TrajectoryQA(index)
        summary = qa.run_qa(resolutions)

        # Check if completion rate is acceptable (> 90%)
        complete_rate = summary['complete'] / summary['total_checked']

        if complete_rate < 0.9:
            self.errors.append(
                f"Trajectory completeness too low: {complete_rate*100:.1f}% "
                f"({summary['complete']}/{summary['total_checked']}) - "
                f"Expected > 90%"
            )
            return False

        print(f"\n✅ Trajectory completeness: {complete_rate*100:.1f}% - ACCEPTABLE")
        return True

    def print_summary(self):
        """Print validation summary."""
        print("\n" + "="*80)
        print("📋 VALIDATION SUMMARY")
        print("="*80)

        if not self.errors and not self.warnings:
            print("✅ All validations passed!")
            return True

        if self.warnings:
            print(f"\n⚠️  Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  • {warning}")

        if self.errors:
            print(f"\n❌ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"  • {error}")
            print("\n🔧 To fix parsing errors, run:")
            print("   uv run python -m etl.parsing.parse_metadata_html data/documents/html/<doc-type>/")
            return False

        return True


def main():
    parser = argparse.ArgumentParser(
        description="Validate ETL pipeline completeness"
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("data"),
        help="Base data directory (default: data)"
    )
    parser.add_argument(
        "--skip-trajectory-qa",
        action="store_true",
        help="Skip trajectory QA validation (faster)"
    )
    parser.add_argument(
        "--trajectory-sample-size",
        type=int,
        default=20,
        help="Number of resolutions to sample for trajectory QA (default: 20)"
    )

    args = parser.parse_args()

    validator = ETLValidator(args.base_dir)

    # Validate parsing completeness
    parsing_valid = validator.validate_all_document_types()

    # Validate trajectory completeness (optional)
    trajectory_valid = True
    if not args.skip_trajectory_qa:
        trajectory_valid = validator.validate_trajectory_completeness(
            sample_size=args.trajectory_sample_size
        )

    # Print summary
    all_valid = validator.print_summary()

    # Exit with appropriate code
    exit(0 if all_valid and parsing_valid and trajectory_valid else 1)


if __name__ == "__main__":
    main()
