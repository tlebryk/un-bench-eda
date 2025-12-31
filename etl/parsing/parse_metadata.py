"""
Step 2: Parse metadata XML files to extract document info

This script parses MARCXML files and extracts key metadata including PDF URLs.
Reads from: data/raw/xml/
Saves to: data/parsed/metadata/
"""

import xml.etree.ElementTree as ET
import json
import argparse
from pathlib import Path
from typing import List, Dict

# Data directories
INPUT_DIR = Path("data/raw/xml")
OUTPUT_DIR = Path("data/parsed/metadata")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MARC_NS = {'marc': 'http://www.loc.gov/MARC21/slim'}


def extract_record_metadata(record: ET.Element) -> Dict:
    """
    Extract metadata from a single MARC record.

    Key fields:
    - 001: Record ID
    - 191: Document symbol
    - 245: Title
    - 269: Publication date
    - 650: Subject keywords
    - 710: Author/Body
    - 856: File URLs (PDFs!)
    """
    metadata = {}

    # Record ID
    record_id = record.find('.//marc:controlfield[@tag="001"]', MARC_NS)
    if record_id is not None:
        metadata['record_id'] = record_id.text.strip()

    # Symbol (tag 191 for documents, tag 791 for meeting/speech records)
    symbol_field = record.find('.//marc:datafield[@tag="191"]', MARC_NS)
    if symbol_field is None:
        # Try tag 791 (used for meeting records)
        symbol_field = record.find('.//marc:datafield[@tag="791"]', MARC_NS)

    if symbol_field is not None:
        symbol = symbol_field.find('.//marc:subfield[@code="a"]', MARC_NS)
        if symbol is not None:
            metadata['symbol'] = symbol.text.strip()

    # Title (tag 245)
    title_field = record.find('.//marc:datafield[@tag="245"]', MARC_NS)
    if title_field is not None:
        title_parts = []
        for subfield in title_field.findall('.//marc:subfield', MARC_NS):
            if subfield.text:
                title_parts.append(subfield.text.strip())
        metadata['title'] = ' '.join(title_parts)

    # Publication date (tag 269)
    date_field = record.find('.//marc:datafield[@tag="269"]', MARC_NS)
    if date_field is not None:
        date = date_field.find('.//marc:subfield[@code="a"]', MARC_NS)
        if date is not None:
            metadata['date'] = date.text.strip()

    # Subjects (tag 650)
    subjects = []
    for subject_field in record.findall('.//marc:datafield[@tag="650"]', MARC_NS):
        subject = subject_field.find('.//marc:subfield[@code="a"]', MARC_NS)
        if subject is not None:
            subjects.append(subject.text.strip())
    if subjects:
        metadata['subjects'] = subjects

    # Authors/Bodies (tag 710)
    authors = []
    for author_field in record.findall('.//marc:datafield[@tag="710"]', MARC_NS):
        author = author_field.find('.//marc:subfield[@code="a"]', MARC_NS)
        if author is not None:
            authors.append(author.text.strip())
    if authors:
        metadata['authors'] = authors

    # PDF URLs (tag 856) - THE CRITICAL PART!
    files = []
    for file_field in record.findall('.//marc:datafield[@tag="856"]', MARC_NS):
        file_info = {}

        # Language
        lang = file_field.find('.//marc:subfield[@code="y"]', MARC_NS)
        if lang is not None:
            file_info['language'] = lang.text.strip()

        # File size
        size = file_field.find('.//marc:subfield[@code="s"]', MARC_NS)
        if size is not None:
            file_info['size'] = int(size.text.strip())

        # URL
        url = file_field.find('.//marc:subfield[@code="u"]', MARC_NS)
        if url is not None:
            file_info['url'] = url.text.strip()

        if file_info:
            files.append(file_info)

    if files:
        metadata['files'] = files

    return metadata


def parse_xml_file(xml_file: str) -> List[Dict]:
    """
    Parse a MARCXML file and extract all records.

    Args:
        xml_file: Path to XML file

    Returns:
        List of metadata dictionaries
    """
    print(f"Parsing {xml_file}...")

    # Parse with UTF-8 encoding
    with open(xml_file, 'r', encoding='utf-8') as f:
        tree = ET.parse(f)
    root = tree.getroot()

    records = root.findall('.//marc:record', MARC_NS)
    print(f"Found {len(records)} records")

    metadata_list = []
    for record in records:
        metadata = extract_record_metadata(record)
        if metadata:
            metadata_list.append(metadata)

    return metadata_list


def save_as_json(metadata_list: List[Dict], output_file: str):
    """Save metadata list to JSON file."""
    Path(output_file).write_text(
        json.dumps(metadata_list, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    print(f"Saved {len(metadata_list)} records to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Parse MARCXML files and extract document metadata',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python parse_metadata.py data/raw/xml/session_78_resolutions.xml
  # Outputs to: data/parsed/metadata/session_78_resolutions.json
  
  python parse_metadata.py data/raw/xml/session_78_resolutions.xml -o custom_output.json
        """
    )
    parser.add_argument('xml_file', type=Path, help='Path to XML file to parse')
    parser.add_argument('-o', '--output', type=Path, default=None,
                        help='Output JSON file path (default: auto-detect from input path)')

    args = parser.parse_args()

    xml_file = args.xml_file

    # Auto-generate output path in parsed/metadata/
    if args.output:
        output_file = args.output
    else:
        # Auto-detect base directory from input path
        # If input is test_data/raw/xml/..., output should be test_data/parsed/metadata/...
        # If input is data/raw/xml/..., output should be data/parsed/metadata/...
        xml_parts = xml_file.parts
        if 'test_data' in xml_parts:
            base_dir = Path('test_data')
        elif 'data' in xml_parts:
            base_dir = Path('data')
        else:
            base_dir = Path('data')  # default fallback
        
        output_dir = base_dir / "parsed" / "metadata"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / xml_file.name.replace('.xml', '.json')

    # Parse
    metadata_list = parse_xml_file(xml_file)

    # Show sample
    if metadata_list:
        print("\n=== Sample Record ===")
        sample = metadata_list[0]
        print(f"Symbol: {sample.get('symbol')}")
        print(f"Title: {sample.get('title', '')[:80]}...")
        print(f"Date: {sample.get('date')}")
        if 'files' in sample:
            print(f"Files: {len(sample['files'])} available")
            for f in sample['files'][:2]:
                print(f"  - {f.get('language')}: {f.get('url')}")

    # Save
    save_as_json(metadata_list, output_file)

    print(f"\nDone! Parsed {len(metadata_list)} documents")
