#!/usr/bin/env python3
"""
Parse UN General Assembly draft resolution and resolution documents.

This parser handles both draft resolutions (pre-adoption) and adopted resolutions.
It extracts comprehensive metadata, cleans text, and segments document structure.

Extracts:
- Enhanced metadata (symbol, session, date, sponsors, committee, document type, etc.)
- Cleaned resolution text (headers/footers removed)
- Segmented text (preamble vs operative paragraphs)
"""

import re
import json
import argparse
from pathlib import Path
from typing import Dict, Optional
import pdfplumber

# Import our utility modules
from .pdf_utils import collapse, remove_footers_headers
from .resolution_metadata import (
    extract_sponsors,
    extract_document_type,
    extract_committee,
    extract_title_enhanced,
    get_html_metadata_path
)
from .resolution_segmentation import segment_resolution_text


def extract_metadata(text: str, pdf_path: Path) -> Dict:
    """Extract document-level metadata from draft/resolution text"""
    metadata = {}

    # Use first ~1000 chars for metadata extraction
    header = text[:1000]

    # Extract symbol (e.g., A/78/L.3, A/C.3/78/L.41, A/RES/78/175)
    # Handle both "A\nUnited Nations /78/L.3" format and regular "A/78/L.3" format
    # First try: look for complete symbol
    symbol_match = re.search(
        r'(A/(?:C\.\d+/)?(?:RES/)?\d+/[A-Z0-9.]+(?:/Rev\.\d+)?(?:/Add\.\d+)?)',
        text[:2000]
    )
    if not symbol_match:
        # Second try: look for split format "A\nUnited Nations /session/L.number"
        split_match = re.search(
            r'^A\s*\n\s*United Nations\s+(/(?:C\.\d+/)?(\d+)/[A-Z0-9.]+(?:/Rev\.\d+)?(?:/Add\.\d+)?)',
            text[:500],
            re.MULTILINE
        )
        if split_match:
            metadata['symbol'] = 'A' + split_match.group(1)
    else:
        metadata['symbol'] = symbol_match.group(1)

    # Extract distribution type (e.g., "Limited")
    distr_match = re.search(r'Distr\.:\s*(\w+)', header)
    if distr_match:
        metadata['distribution'] = distr_match.group(1)

    # Extract date
    date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', header)
    if date_match:
        metadata['date'] = date_match.group(1)

    # Extract original language
    lang_match = re.search(r'Original:\s*(\w+)', header)
    if lang_match:
        metadata['original_language'] = lang_match.group(1)

    # Extract session (e.g., "Seventy-eighth session")
    session_match = re.search(r'([\w-]+)\s+session', header, re.IGNORECASE)
    if session_match:
        metadata['session_name'] = session_match.group(0)
        # Try to extract number
        num_match = re.search(r'(\d+)', session_match.group(0))
        if num_match:
            metadata['session_number'] = int(num_match.group(1))

    # Extract agenda item number and title
    # Pattern: "Agenda item 125" followed by possible sub-item and title
    agenda_match = re.search(
        r'Agenda item (\d+)\s*(?:\(([a-z])\))?\s*\n\s*(.+?)(?=\n)',
        text[:1500]
    )
    if agenda_match:
        agenda_item = {
            'number': int(agenda_match.group(1)),
            'title': agenda_match.group(3).strip()
        }
        if agenda_match.group(2):  # sub-item like (c)
            agenda_item['sub_item'] = agenda_match.group(2)
        metadata['agenda_item'] = agenda_item

    # Extract document type
    doc_type = extract_document_type(text)
    if doc_type:
        metadata['document_type'] = doc_type

    # Extract committee
    committee = extract_committee(text, metadata.get('symbol'))
    if committee:
        metadata['committee'] = committee

    # Extract sponsors (from both HTML and PDF sources)
    html_path = get_html_metadata_path(pdf_path)
    sponsors = extract_sponsors(pdf_path, text, html_path)
    # Only include if we found sponsors from at least one source
    if sponsors['html'] or sponsors['pdf']:
        metadata['sponsors'] = sponsors

    # Extract title (with HTML metadata if available)
    html_metadata = None
    if html_path and html_path.exists():
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                html_metadata = json.load(f)
        except:
            pass

    title = extract_title_enhanced(text, html_metadata)
    if title:
        metadata['title'] = title

    return metadata


def extract_draft_text(text: str) -> str:
    """Extract the main draft text (after metadata header)"""

    # Find where the actual draft text starts
    # Usually starts with "The General Assembly" or similar
    start_patterns = [
        r'\n\s*(The General Assembly)',
        r'\n\s*(Adopts the)',
        r'\n\s*(Recalling)',
        r'\n\s*(Noting)',
        r'\n\s*(Recognizing)',
        r'\n\s*(Guided)',
        r'\n\s*(Welcoming)',
    ]

    start_pos = None
    for pattern in start_patterns:
        match = re.search(pattern, text)
        if match:
            start_pos = match.start(1)
            break

    if start_pos is None:
        # Fallback: assume text starts after first ~500 chars if no pattern found
        # Skip to first paragraph after metadata
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if i > 10 and line.strip() and not re.match(
                r'^(A|United Nations|General Assembly|Distr\.|Original:|Agenda|Draft)',
                line
            ):
                start_pos = text.find(line)
                break

    if start_pos is not None:
        draft_text = text[start_pos:].strip()
    else:
        # Fallback: return everything after line 15
        lines = text.split('\n')
        draft_text = '\n'.join(lines[15:]).strip()

    return draft_text


def parse_resolution_file(file_path: Path) -> Dict:
    """Parse a draft resolution or resolution PDF file and return structured data"""

    print(f"Parsing: {file_path.name}")

    # Extract text from PDF with header/footer removal
    if file_path.suffix.lower() == '.pdf':
        with pdfplumber.open(file_path) as pdf:
            pages_text = []
            for page_num, page in enumerate(pdf.pages, 1):
                raw_text = page.extract_text() or ""
                # Remove headers/footers from each page
                cleaned_text = remove_footers_headers(raw_text, page_num)
                pages_text.append(cleaned_text)
            text = '\n'.join(pages_text)
    else:
        # Fallback to reading as text file
        text = file_path.read_text(encoding='utf-8')

    # Extract metadata
    metadata = extract_metadata(text, file_path)
    print(f"  Session: {metadata.get('session_name', 'Unknown')}")
    print(f"  Symbol: {metadata.get('symbol', 'Unknown')}")
    print(f"  Type: {metadata.get('document_type', 'Unknown')}")
    if metadata.get('committee'):
        print(f"  Committee: {metadata['committee']}")
    if metadata.get('title'):
        print(f"  Title: {metadata['title'][:60]}...")
    if metadata.get('sponsors'):
        sponsors = metadata['sponsors']
        sources = []
        if sponsors.get('html'):
            html_count = len(sponsors['html']['primary'])
            sources.append(f"HTML:{html_count}")
        if sponsors.get('pdf'):
            pdf_count = len(sponsors['pdf']['primary'])
            sources.append(f"PDF:{pdf_count}")
        print(f"  Sponsors: {', '.join(sources)}")

    # Extract main draft/resolution text
    draft_text = extract_draft_text(text)

    # Segment text into preamble and operative paragraphs
    segments = segment_resolution_text(draft_text)

    # Calculate stats
    word_count = len(draft_text.split())
    line_count = len(draft_text.split('\n'))

    # Add IDs
    doc_symbol = metadata.get('symbol')
    if doc_symbol:
        metadata['id'] = doc_symbol

    return {
        'id': doc_symbol,
        'metadata': metadata,
        'text_segments': segments,
        'raw_text': {
            'full_text': draft_text,
            'cleaned_text': draft_text  # Already cleaned (footers removed)
        },
        'stats': {
            'word_count': word_count,
            'line_count': line_count,
            'has_annex': 'Annex' in text or 'annex' in text.lower(),
            'preamble_paragraph_count': len(segments['preamble_paragraphs']),
            'operative_paragraph_count': len(segments['operative_paragraphs'])
        }
    }


def detect_document_type(input_path: Path) -> str:
    """
    Detect document type from input path.

    Args:
        input_path: Path to file or directory

    Returns:
        Document type string (drafts, resolutions, or other)
    """
    parts = input_path.parts

    # Check for known document type folders
    if 'drafts' in parts:
        return 'drafts'
    elif 'resolutions' in parts:
        return 'resolutions'
    else:
        return 'resolutions'  # default


def parse_resolution_files(input_dir: Path, output_dir: Path, max_files: Optional[int] = None):
    """
    Parse all PDF files in a directory.

    Args:
        input_dir: Directory containing PDF files
        output_dir: Directory to save JSON files
        max_files: Maximum number of files to process (None = all)
    """
    pdf_files = list(input_dir.glob('*.pdf'))

    if max_files:
        pdf_files = pdf_files[:max_files]

    print(f"Found {len(pdf_files)} PDF files to parse")

    output_dir.mkdir(parents=True, exist_ok=True)

    parsed = 0
    failed = 0

    for pdf_file in pdf_files:
        print(f"\n{'='*70}")
        print(f"Processing: {pdf_file.name}")
        print('='*70)

        try:
            data = parse_resolution_file(pdf_file)

            # Create output filename
            output_filename = pdf_file.stem + '.json'
            output_path = output_dir / output_filename

            # Save JSON
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"\n✓ Saved: {output_filename}")
            print(f"  Word count: {data['stats']['word_count']}")
            print(f"  Preamble paragraphs: {data['stats']['preamble_paragraph_count']}")
            print(f"  Operative paragraphs: {data['stats']['operative_paragraph_count']}")

            parsed += 1

        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n" + "="*70)
    print(f"SUMMARY")
    print(f"="*70)
    print(f"Total files: {len(pdf_files)}")
    print(f"Parsed: {parsed}")
    print(f"Failed: {failed}")
    print(f"Output directory: {output_dir.absolute()}")


def main():
    parser = argparse.ArgumentParser(
        description='Parse UN General Assembly draft resolution and resolution documents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Extracts:
- Enhanced metadata (symbol, session, date, sponsors, committee, document type, etc.)
- Cleaned resolution text (headers/footers removed)
- Segmented text (preamble vs operative paragraphs)

Examples:
  # Parse all PDF files in directory (auto-detects output)
  python parse_resolution_pdf.py data/documents/pdfs/drafts

  # Parse single file
  python parse_resolution_pdf.py data/documents/pdfs/drafts/A_78_L.3.pdf

  # Parse first 5 files
  python parse_resolution_pdf.py data/documents/pdfs/drafts --max-files 5

  # Custom output directory
  python parse_resolution_pdf.py data/documents/pdfs/drafts -o data/parsed/pdfs/drafts
        """
    )
    parser.add_argument('input_path', type=Path, help='Path to PDF file or directory')
    parser.add_argument('-o', '--output', type=Path, default=None,
                        help='Output directory for JSON files (default: auto-detect from input path)')
    parser.add_argument('--max-files', type=int, default=None,
                        help='Maximum number of files to process (default: all)')

    args = parser.parse_args()

    input_path = args.input_path

    if not input_path.exists():
        parser.error(f"Path not found: {input_path}")

    # Determine if input is a file or directory
    if input_path.is_file():
        # Single file mode
        if args.output:
            # If output is specified and is a file, use it; otherwise treat as directory
            if args.output.suffix:
                output_file = args.output
            else:
                output_file = args.output / f"{input_path.stem}.json"
        else:
            output_file = input_path.parent / f"{input_path.stem}.json"

        # Parse single file
        result = parse_resolution_file(input_path)

        # Save
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n✓ Saved to: {output_path}")
        print(f"\nStats:")
        print(f"  Word count: {result['stats']['word_count']}")
        print(f"  Preamble paragraphs: {result['stats']['preamble_paragraph_count']}")
        print(f"  Operative paragraphs: {result['stats']['operative_paragraph_count']}")

    else:
        # Directory mode
        input_dir = input_path

        # Auto-detect output directory
        if args.output:
            output_dir = args.output
        else:
            # Detect document type from input path
            doc_type = detect_document_type(input_dir)

            # Determine base directory
            if 'test_data' in input_dir.parts:
                base_dir = Path('test_data')
            elif 'data' in input_dir.parts:
                base_dir = Path('data')
            else:
                # Try to infer from input path structure
                # Look for documents/pdfs in path
                parts = input_dir.parts
                if 'documents' in parts:
                    base_dir = Path(*parts[:parts.index('documents')])
                else:
                    base_dir = Path('data')

            output_dir = base_dir / 'parsed' / 'pdfs' / doc_type

        if args.max_files:
            print(f"Limit: First {args.max_files} files")
        print(f"Input: {input_dir}")
        print(f"Output: {output_dir}")

        parse_resolution_files(input_dir, output_dir, args.max_files)


if __name__ == "__main__":
    main()
