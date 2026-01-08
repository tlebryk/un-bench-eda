#!/usr/bin/env python3
"""
Fill missing documents identified by QA script.

This script:
1. Reads QA results to identify missing documents
2. Extracts URLs for missing documents from resolution metadata
3. Creates metadata JSON for downloading
4. Downloads and parses the missing documents
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Any, Set
from collections import defaultdict

from .trace_genealogy import UNDocumentIndex


class MissingDocumentFiller:
    """Fill missing documents in trajectory data."""

    def __init__(self, index: UNDocumentIndex):
        self.index = index

    def extract_missing_urls(self, qa_results_file: Path) -> Dict[str, List[Dict[str, Any]]]:
        """Extract URLs for missing documents from QA results."""

        with open(qa_results_file) as f:
            qa_data = json.load(f)

        # Track missing documents and their metadata
        missing_docs = defaultdict(list)

        for result in qa_data.get("results", []):
            if result["status"] != "incomplete":
                continue

            resolution_symbol = result["resolution"]
            resolution_data = self.index.load(resolution_symbol)

            if not resolution_data:
                print(f"⚠️  Warning: Could not load {resolution_symbol}")
                continue

            # Extract URLs for missing documents
            for doc_type, missing_symbols in result["missing"].items():
                for symbol in missing_symbols:
                    url = self._find_document_url(resolution_data, symbol, doc_type)

                    if url:
                        # Extract record_id from URL if possible
                        record_id = self._extract_record_id_from_url(url)

                        doc_metadata = {
                            "symbol": symbol,
                            "url": url,
                            "record_id": record_id,
                            "doc_type": doc_type,
                            "referenced_by": resolution_symbol
                        }

                        # Avoid duplicates
                        if not any(d["symbol"] == symbol for d in missing_docs[doc_type]):
                            missing_docs[doc_type].append(doc_metadata)

        return missing_docs

    def _find_document_url(self, resolution_data: Dict[str, Any], symbol: str, doc_type: str) -> str:
        """Find URL for a document from resolution metadata."""

        related = resolution_data.get("related_documents", {})

        # Map doc_type to related_documents key
        type_mapping = {
            "drafts": "drafts",
            "committee_reports": "committee_reports",
            "meeting_records": "meeting_records"
        }

        related_key = type_mapping.get(doc_type)
        if not related_key:
            return None

        # Search for matching symbol
        for doc_ref in related.get(related_key, []):
            if doc_ref.get("text") == symbol:
                return doc_ref.get("url")

        # Also check agenda items
        if doc_type == "agenda_items":
            for agenda_item in resolution_data.get("agenda", []):
                if agenda_item.get("agenda_symbol") == symbol:
                    return agenda_item.get("url")

        return None

    def _extract_record_id_from_url(self, url: str) -> str:
        """Extract record ID from UN Digital Library URL."""
        # URL format: https://digitallibrary.un.org/record/4028559?ln=en
        if "digitallibrary.un.org/record/" in url:
            parts = url.split("/record/")
            if len(parts) == 2:
                record_id = parts[1].split("?")[0]
                return record_id
        return None

    def create_metadata_json(self, missing_docs: Dict[str, List[Dict[str, Any]]], output_file: Path):
        """Create metadata JSON file for downloader."""

        # Combine all document types
        all_docs = []
        for doc_type, docs in missing_docs.items():
            all_docs.extend(docs)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_docs, f, indent=2)

        print(f"📝 Created metadata file: {output_file}")
        print(f"   Total documents: {len(all_docs)}")
        for doc_type, docs in missing_docs.items():
            print(f"   - {doc_type}: {len(docs)}")

    def print_summary(self, missing_docs: Dict[str, List[Dict[str, Any]]]):
        """Print summary of missing documents."""

        print("\n" + "="*80)
        print("📋 MISSING DOCUMENTS SUMMARY")
        print("="*80)

        total = sum(len(docs) for docs in missing_docs.values())
        print(f"Total missing documents: {total}\n")

        for doc_type, docs in missing_docs.items():
            print(f"{doc_type.upper()} ({len(docs)} documents):")
            for doc in docs[:5]:  # Show first 5
                print(f"  • {doc['symbol']}")
                print(f"    URL: {doc['url']}")
                print(f"    Record ID: {doc.get('record_id', 'N/A')}")

            if len(docs) > 5:
                print(f"  ... and {len(docs) - 5} more")
            print()


def main():
    parser = argparse.ArgumentParser(
        description="Fill missing documents identified by trajectory QA"
    )
    parser.add_argument(
        "qa_results",
        type=Path,
        help="Path to QA results JSON file"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("test_data/missing_documents_metadata.json"),
        help="Output metadata JSON file (default: test_data/missing_documents_metadata.json)"
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/parsed/html"),
        help="Root directory for parsed HTML data (default: data/parsed/html)"
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Automatically download missing documents after creating metadata"
    )
    parser.add_argument(
        "--parse",
        action="store_true",
        help="Automatically parse downloaded documents (requires --download)"
    )

    args = parser.parse_args()

    if not args.qa_results.exists():
        print(f"❌ Error: {args.qa_results} not found")
        return

    # Build index
    print(f"Building document index from {args.data_root}...")
    index = UNDocumentIndex(args.data_root)
    print(f"Indexed {len(index.documents)} documents\n")

    # Extract missing documents
    filler = MissingDocumentFiller(index)
    print(f"Extracting missing document URLs from {args.qa_results}...")
    missing_docs = filler.extract_missing_urls(args.qa_results)

    # Print summary
    filler.print_summary(missing_docs)

    # Create metadata JSON
    filler.create_metadata_json(missing_docs, args.output)

    print(f"\n✅ Next steps:")
    print(f"   1. Download HTML: uv run python -m etl.fetch_download.download_metadata_html {args.output}")
    print(f"   2. Parse HTML: uv run python -m etl.parsing.parse_metadata_html data/documents/html/committee-reports/")
    print(f"   3. Re-run QA: uv run python -m etl.trajectories.qa_trajectories -n 20 --seed 42")

    if args.download:
        print(f"\n📥 Downloading missing documents...")
        import subprocess
        result = subprocess.run([
            "uv", "run", "python", "-m", "etl.fetch_download.download_metadata_html",
            str(args.output)
        ])

        if result.returncode == 0:
            print(f"✅ Download complete!")

            if args.parse:
                print(f"\n🔍 Parsing downloaded documents...")
                # Parse committee reports
                result = subprocess.run([
                    "uv", "run", "python", "-m", "etl.parsing.parse_metadata_html",
                    "data/documents/html/committee-reports/"
                ])

                if result.returncode == 0:
                    print(f"✅ Parsing complete!")
        else:
            print(f"❌ Download failed")


if __name__ == "__main__":
    main()
