#!/usr/bin/env python3
"""
Trace UN document genealogy backwards from final resolutions.

This script provides tools to navigate the document tree from a resolution
back through committee reports, drafts, meeting records, and agenda items.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from collections import defaultdict


# Default data locations
DEFAULT_DATA_ROOT = Path(__file__).parent / "data"
DEFAULT_PARSED_HTML = DEFAULT_DATA_ROOT / "parsed" / "html"
DEFAULT_PARSED_PDFS = DEFAULT_DATA_ROOT / "parsed" / "pdfs"


@dataclass
class DocumentReference:
    """A reference to a related UN document."""
    symbol: str
    url: Optional[str] = None
    doc_type: Optional[str] = None  # resolution, draft, committee_report, meeting, agenda


class UNDocumentIndex:
    """Index of all UN documents for fast lookup by symbol."""

    def __init__(self, data_root: Path = DEFAULT_PARSED_HTML):
        self.data_root = Path(data_root)
        self.documents: Dict[str, Path] = {}
        self._build_index()

    def _build_index(self):
        """Build index of all documents by symbol."""
        # Index HTML parsed documents
        for doc_type_dir in self.data_root.iterdir():
            if not doc_type_dir.is_dir():
                continue

            for json_file in doc_type_dir.glob("*.json"):
                try:
                    with open(json_file) as f:
                        data = json.load(f)
                        symbol = data.get("metadata", {}).get("symbol")
                        if symbol:
                            # Normalize symbol (remove spaces, etc.)
                            normalized = self._normalize_symbol(symbol)
                            self.documents[normalized] = json_file
                except Exception as e:
                    print(f"Warning: Failed to index {json_file}: {e}")

        # Also index PDF parsed documents
        pdf_root = DEFAULT_PARSED_PDFS
        if pdf_root.exists():
            for doc_type_dir in pdf_root.iterdir():
                if not doc_type_dir.is_dir():
                    continue

                for json_file in doc_type_dir.glob("*.json"):
                    try:
                        with open(json_file) as f:
                            data = json.load(f)
                            # For PDF parsed docs, extract symbol from filename
                            # e.g., A_C.3_78_L.41.json -> A/C.3/78/L.41
                            symbol = json_file.stem.replace("_", "/").replace(".json", "")
                            normalized = self._normalize_symbol(symbol)
                            if normalized not in self.documents:
                                self.documents[normalized] = json_file
                    except Exception as e:
                        print(f"Warning: Failed to index {json_file}: {e}")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """Normalize document symbol for lookup."""
        # Remove spaces, convert to uppercase
        normalized = symbol.strip().upper()
        # Normalize separators
        normalized = normalized.replace("_", "/")
        return normalized

    def find(self, symbol: str) -> Optional[Path]:
        """Find document by symbol."""
        normalized = self._normalize_symbol(symbol)
        return self.documents.get(normalized)

    def load(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Load document data by symbol."""
        path = self.find(symbol)
        if path:
            with open(path) as f:
                return json.load(f)
        return None


class DocumentGenealogy:
    """Trace document genealogy backwards from resolution."""

    def __init__(self, index: UNDocumentIndex):
        self.index = index

    def trace_backwards(self, resolution_symbol: str) -> Dict[str, Any]:
        """Trace genealogy backwards from resolution to origins."""
        resolution = self.index.load(resolution_symbol)
        if not resolution:
            return {"error": f"Resolution {resolution_symbol} not found"}

        tree = {
            "resolution": {"symbol": resolution_symbol, "data": resolution},
            "drafts": [],
            "committee_reports": [],
            "meeting_records": [],
            "agenda_items": []
        }

        related = resolution.get("related_documents", {})

        for draft_ref in related.get("drafts", []):
            draft_symbol = draft_ref.get("text")
            tree["drafts"].append({
                "symbol": draft_symbol,
                "data": self.index.load(draft_symbol),
                "found": self.index.find(draft_symbol) is not None
            })

        for report_ref in related.get("committee_reports", []):
            report_symbol = report_ref.get("text")
            tree["committee_reports"].append({
                "symbol": report_symbol,
                "data": self.index.load(report_symbol),
                "found": self.index.find(report_symbol) is not None
            })

        for meeting_ref in related.get("meeting_records", []):
            meeting_symbol = meeting_ref.get("text")
            tree["meeting_records"].append({
                "symbol": meeting_symbol,
                "data": self.index.load(meeting_symbol),
                "found": self.index.find(meeting_symbol) is not None
            })

        for agenda_item in resolution.get("agenda", []):
            agenda_symbol = agenda_item.get("agenda_symbol")
            tree["agenda_items"].append({
                "symbol": agenda_symbol,
                "item_number": agenda_item.get("item_number"),
                "sub_item": agenda_item.get("sub_item"),
                "title": agenda_item.get("title"),
                "data": self.index.load(agenda_symbol),
                "found": self.index.find(agenda_symbol) is not None
            })

        return tree

    def trace_forwards(self, agenda_symbol: str, item_number: str = None) -> Dict[str, Any]:
        """Trace forwards from agenda item to all resulting documents."""
        agenda = self.index.load(agenda_symbol)
        if not agenda:
            return {"error": f"Agenda {agenda_symbol} not found"}

        tree = {
            "agenda": {"symbol": agenda_symbol, "data": agenda},
            "drafts": [],
            "committee_reports": [],
            "resolutions": [],
            "meetings": []
        }

        # Search all documents for ones that reference this agenda item
        for doc_symbol, doc_path in self.index.documents.items():
            doc_data = self.index.load(doc_symbol)
            if not doc_data:
                continue

            # Check if this doc references our agenda item
            for agenda_ref in doc_data.get("agenda", []):
                if agenda_ref.get("agenda_symbol") == agenda_symbol:
                    # Match item number if specified
                    if item_number:
                        ref_item = str(agenda_ref.get("item_number", ""))
                        if agenda_ref.get("sub_item"):
                            ref_item += agenda_ref.get("sub_item")
                        if ref_item != item_number:
                            continue

                    # Categorize by document type (from path)
                    doc_entry = {"symbol": doc_symbol, "data": doc_data, "found": True}

                    if "/resolutions/" in str(doc_path):
                        tree["resolutions"].append(doc_entry)
                    elif "/drafts/" in str(doc_path):
                        tree["drafts"].append(doc_entry)
                    elif "/committee-reports/" in str(doc_path):
                        tree["committee_reports"].append(doc_entry)
                    elif "/meetings/" in str(doc_path):
                        tree["meetings"].append(doc_entry)
                    break

        return tree

    def trace_from_draft(self, draft_symbol: str) -> Dict[str, Any]:
        """Trace both directions from a draft resolution."""
        draft = self.index.load(draft_symbol)
        if not draft:
            return {"error": f"Draft {draft_symbol} not found"}

        tree = {
            "draft": {"symbol": draft_symbol, "data": draft},
            "resolutions": [],
            "committee_reports": [],
            "agenda_items": []
        }

        # Get agenda items (backwards)
        for agenda_item in draft.get("agenda", []):
            agenda_symbol = agenda_item.get("agenda_symbol")
            tree["agenda_items"].append({
                "symbol": agenda_symbol,
                "item_number": agenda_item.get("item_number"),
                "sub_item": agenda_item.get("sub_item"),
                "data": self.index.load(agenda_symbol),
                "found": self.index.find(agenda_symbol) is not None
            })

        # Find documents that reference this draft (forwards)
        for doc_symbol, doc_path in self.index.documents.items():
            doc_data = self.index.load(doc_symbol)
            if not doc_data:
                continue

            # Check if this doc references our draft
            for draft_ref in doc_data.get("related_documents", {}).get("drafts", []):
                if draft_ref.get("text") == draft_symbol:
                    doc_entry = {"symbol": doc_symbol, "data": doc_data, "found": True}

                    if "/resolutions/" in str(doc_path):
                        tree["resolutions"].append(doc_entry)
                    elif "/committee-reports/" in str(doc_path):
                        tree["committee_reports"].append(doc_entry)
                    break

        return tree

    def print_tree(self, tree: Dict[str, Any], verbose: bool = False):
        """Print the document tree in a readable format."""
        if "error" in tree:
            print(f"❌ {tree['error']}")
            return

        # Detect mode and print accordingly
        if "resolution" in tree:
            self._print_backwards(tree, verbose)
        elif "agenda" in tree:
            self._print_forwards(tree, verbose)
        elif "draft" in tree:
            self._print_from_draft(tree, verbose)

    def _print_backwards(self, tree: Dict[str, Any], verbose: bool):
        """Print backwards trace from resolution."""
        res = tree["resolution"]
        data = res["data"]
        print(f"\n📄 RESOLUTION: {res['symbol']}")
        print(f"   Title: {data['metadata']['title']}")
        if data.get("voting"):
            print(f"   Voting: {data['voting'].get('raw_text', 'N/A')}")

        print(f"\n📋 AGENDA ITEMS ({len(tree['agenda_items'])})")
        for item in tree["agenda_items"]:
            status = "✓" if item["found"] else "✗"
            print(f"   {status} {item['symbol']} (Item {item.get('item_number', '?')}{item.get('sub_item', '')})")

        print(f"\n📝 DRAFTS ({len(tree['drafts'])})")
        for draft in tree["drafts"]:
            status = "✓" if draft["found"] else "✗"
            print(f"   {status} {draft['symbol']}")

        print(f"\n📊 COMMITTEE REPORTS ({len(tree['committee_reports'])})")
        for report in tree["committee_reports"]:
            status = "✓" if report["found"] else "✗"
            print(f"   {status} {report['symbol']}")

        print(f"\n🏛️  MEETINGS ({len(tree['meeting_records'])})")
        for meeting in tree["meeting_records"]:
            status = "✓" if meeting["found"] else "✗"
            print(f"   {status} {meeting['symbol']}")

    def _print_forwards(self, tree: Dict[str, Any], verbose: bool):
        """Print forwards trace from agenda."""
        agenda = tree["agenda"]
        data = agenda["data"]
        print(f"\n📋 AGENDA: {agenda['symbol']}")
        print(f"   Title: {data['metadata']['title']}")

        print(f"\n📝 DRAFTS ({len(tree['drafts'])})")
        for draft in tree["drafts"]:
            print(f"   ✓ {draft['symbol']}")

        print(f"\n📊 COMMITTEE REPORTS ({len(tree['committee_reports'])})")
        for report in tree["committee_reports"]:
            print(f"   ✓ {report['symbol']}")

        print(f"\n📄 RESOLUTIONS ({len(tree['resolutions'])})")
        for res in tree["resolutions"]:
            print(f"   ✓ {res['symbol']}")

        print(f"\n🏛️  MEETINGS ({len(tree['meetings'])})")
        for meeting in tree["meetings"]:
            print(f"   ✓ {meeting['symbol']}")

    def _print_from_draft(self, tree: Dict[str, Any], verbose: bool):
        """Print trace from draft in both directions."""
        draft = tree["draft"]
        data = draft["data"]
        print(f"\n📝 DRAFT: {draft['symbol']}")
        print(f"   Title: {data['metadata'].get('title', 'N/A')}")
        print(f"   Date: {data['metadata'].get('date', 'N/A')}")

        print(f"\n⬅️  BACKWARDS:")
        print(f"   📋 Agenda items: {len(tree['agenda_items'])}")
        for item in tree["agenda_items"]:
            status = "✓" if item["found"] else "✗"
            print(f"      {status} {item['symbol']} (Item {item.get('item_number', '?')}{item.get('sub_item', '')})")

        print(f"\n➡️  FORWARDS:")
        print(f"   📊 Committee reports: {len(tree['committee_reports'])}")
        for report in tree["committee_reports"]:
            print(f"      ✓ {report['symbol']}")

        print(f"   📄 Resolutions: {len(tree['resolutions'])}")
        for res in tree["resolutions"]:
            print(f"      ✓ {res['symbol']}")


def main():
    parser = argparse.ArgumentParser(
        description="Trace UN document genealogy"
    )
    parser.add_argument(
        "symbol",
        help="Document symbol (e.g., A/RES/78/220, A/78/251, A/C.3/78/L.41)"
    )
    parser.add_argument(
        "--mode",
        choices=["backwards", "forwards", "draft"],
        help="Trace mode (default: auto-detect from symbol)"
    )
    parser.add_argument(
        "--item",
        help="Agenda item number for forwards mode (e.g., '71c')"
    )
    parser.add_argument(
        "--data-root",
        default=DEFAULT_PARSED_HTML,
        type=Path,
        help="Root directory for parsed HTML data"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show verbose output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    # Build index
    print(f"Building document index from {args.data_root}...")
    index = UNDocumentIndex(args.data_root)
    print(f"Indexed {len(index.documents)} documents")

    # Auto-detect mode if not specified
    mode = args.mode
    if not mode:
        if "/RES/" in args.symbol.upper():
            mode = "backwards"
        elif "/L." in args.symbol.upper():
            mode = "draft"
        else:
            mode = "forwards"

    # Trace genealogy
    genealogy = DocumentGenealogy(index)
    if mode == "backwards":
        tree = genealogy.trace_backwards(args.symbol)
    elif mode == "forwards":
        tree = genealogy.trace_forwards(args.symbol, args.item)
    elif mode == "draft":
        tree = genealogy.trace_from_draft(args.symbol)

    # Output
    if args.json:
        print(json.dumps(tree, indent=2, default=str))
    else:
        genealogy.print_tree(tree, verbose=args.verbose)


if __name__ == "__main__":
    main()
