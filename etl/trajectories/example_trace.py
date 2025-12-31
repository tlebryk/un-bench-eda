#!/usr/bin/env python3
"""Example usage of the trace_genealogy library."""

import argparse
from pathlib import Path
from .trace_genealogy import UNDocumentIndex, DocumentGenealogy


def main():
    parser = argparse.ArgumentParser(description="Example usage of trace_genealogy library")
    parser.add_argument(
        "--data-root",
        type=Path,
        help="Root directory for parsed HTML data (default: data/documents/html)"
    )
    args = parser.parse_args()

    # Initialize
    print("Loading document index...")
    index = UNDocumentIndex(args.data_root) if args.data_root else UNDocumentIndex()
    genealogy = DocumentGenealogy(index)
    print(f"Loaded {len(index.documents)} documents\n")

    # Example 1: Trace backwards from resolution
    print("=" * 60)
    print("EXAMPLE 1: Trace backwards from resolution A/RES/78/220")
    print("=" * 60)
    tree = genealogy.trace_backwards("A/RES/78/220")
    print(f"Found {len(tree['drafts'])} drafts")
    print(f"Found {len(tree['committee_reports'])} committee reports")
    print(f"Found {len(tree['agenda_items'])} agenda items")

    # Example 2: Trace forwards from agenda
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Trace forwards from agenda item 71c")
    print("=" * 60)
    tree = genealogy.trace_forwards("A/78/251", item_number="71c")
    print(f"Found {len(tree['drafts'])} drafts")
    print(f"Found {len(tree['resolutions'])} resolutions")

    # Example 3: Trace from draft (both directions)
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Trace from draft A/C.3/78/L.41")
    print("=" * 60)
    tree = genealogy.trace_from_draft("A/C.3/78/L.41")
    print(f"Backwards: {len(tree['agenda_items'])} agenda items")
    print(f"Forwards: {len(tree['resolutions'])} resolutions, "
          f"{len(tree['committee_reports'])} committee reports")

    # Example 4: Direct document access
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Direct document access")
    print("=" * 60)
    doc = index.load("A/RES/78/220")
    if doc:
        print(f"Symbol: {doc['metadata']['symbol']}")
        print(f"Title: {doc['metadata']['title'][:60]}...")
        print(f"Voting: {doc.get('voting', {}).get('raw_text', 'N/A')}")


if __name__ == "__main__":
    main()
