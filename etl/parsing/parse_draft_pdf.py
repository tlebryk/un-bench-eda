#!/usr/bin/env python3
"""
Parse UN General Assembly draft resolution documents.

Extracts:
- Document metadata (symbol, session, date, agenda item, etc.)
- Draft resolution text
"""

import re
import json
import argparse
from pathlib import Path
from typing import Dict, Optional
import pdfplumber


def extract_metadata(text: str) -> Dict:
    """Extract document-level metadata from draft text"""
    metadata = {}

    # Use first ~1000 chars for metadata extraction
    header = text[:1000]

    # Extract symbol (e.g., A/78/L.3)
    # Handle both "A\nUnited Nations /78/L.3" format and regular "A/78/L.3" format
    # First try: look for complete symbol
    symbol_match = re.search(r'(A/(?:C\.\d+/)?[\d]+/L\.[\d]+(?:/Rev\.[\d]+)?(?:/Add\.[\d]+)?)', text[:2000])
    if not symbol_match:
        # Second try: look for split format "A\nUnited Nations /session/L.number"
        split_match = re.search(r'^A\s*\n\s*United Nations\s+(/([\d]+)/L\.([\d]+)(?:/Rev\.([\d]+))?(?:/Add\.([\d]+))?)', text[:500], re.MULTILINE)
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
    # Pattern: "Agenda item 125" followed by title on next line
    agenda_match = re.search(r'Agenda item (\d+)\s*\n\s*(.+?)(?=\n)', text[:1000])
    if agenda_match:
        metadata['agenda_item'] = {
            'number': int(agenda_match.group(1)),
            'title': agenda_match.group(2).strip()
        }

    # Extract submission/document type (e.g., "Draft resolution submitted by...")
    submission_match = re.search(r'(Draft (?:resolution|decision)[^\n]+)', text[:1500])
    if submission_match:
        metadata['submission_type'] = submission_match.group(1).strip()

    # Extract title, which is usually between the sponsor line and "The General Assembly,"
    title = None
    sponsor_match = re.search(r'.*draft (?:resolution|decision)[^\n]*', text[:2000], re.IGNORECASE)
    if sponsor_match:
        text_after_sponsor = text[sponsor_match.end():]
        # The body can start with "The General Assembly" or "The Security Council", etc.
        # And may be followed by a comma or newline.
        body_match = re.search(r'The (General Assembly|Security Council)', text_after_sponsor, re.IGNORECASE)
        if body_match:
            title_candidate = text_after_sponsor[:body_match.start()].strip()
            # Clean up whitespace and join lines
            title = ' '.join(title_candidate.split())
            if title:
                metadata['title'] = title
    
    if not metadata.get('title') and 'agenda_item' in metadata and 'title' in metadata['agenda_item']:
        # Fallback to agenda item title if no clear draft title is found
        metadata['title'] = metadata['agenda_item']['title']

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
            if i > 10 and line.strip() and not re.match(r'^(A|United Nations|General Assembly|Distr\.|Original:|Agenda|Draft)', line):
                start_pos = text.find(line)
                break

    if start_pos is not None:
        draft_text = text[start_pos:].strip()
    else:
        # Fallback: return everything after line 15
        lines = text.split('\n')
        draft_text = '\n'.join(lines[15:]).strip()

    return draft_text


def parse_draft_file(file_path: str) -> Dict:
    """Parse a draft resolution PDF file and return structured data"""

    print(f"Parsing draft: {file_path}")

    file_path_obj = Path(file_path)

    # Extract text from PDF
    if file_path_obj.suffix.lower() == '.pdf':
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
    else:
        # Fallback to reading as text file
        text = file_path_obj.read_text(encoding='utf-8')

    # Extract metadata
    metadata = extract_metadata(text)
    # If symbol missing, fall back to filename (stem)
    if not metadata.get("symbol"):
        metadata["symbol"] = file_path_obj.stem
    print(f"  Session: {metadata.get('session_name', 'Unknown')}")
    print(f"  Symbol: {metadata.get('symbol', 'Unknown')}")
    print(f"  Title: {metadata.get('title', 'Unknown')[:60]}...")

    # Extract draft text
    draft_text = extract_draft_text(text)

    # Calculate stats
    word_count = len(draft_text.split())
    line_count = len(draft_text.split('\n'))

    return {
        'metadata': metadata,
        'draft_text': draft_text,
        'stats': {
            'word_count': word_count,
            'line_count': line_count,
            'has_annex': 'Annex' in text or 'annex' in text.lower()
        }
    }


def parse_draft_files(input_dir: Path, output_dir: Path, max_files: Optional[int] = None):
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
    
    print(f"Found {len(pdf_files)} PDF files to parse in {input_dir}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    parsed = 0
    failed = 0
    
    for pdf_file in pdf_files:
        print(f"\nParsing: {pdf_file.name}")
        
        try:
            data = parse_draft_file(str(pdf_file))
            
            output_filename = pdf_file.stem + '.json'
            output_path = output_dir / output_filename
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"  ✓ Saved: {output_filename}")
            metadata = data.get('metadata', {})
            stats = data.get('stats', {})
            print(f"    Symbol: {metadata.get('symbol', 'N/A')}")
            print(f"    Word count: {stats.get('word_count', 'N/A')}")

            parsed += 1
            
        except Exception as e:
            print(f"  ✗ Error parsing {pdf_file.name}: {e}")
            failed += 1
    
    print(f"\n" + "="*60)
    print(f"SUMMARY")
    print(f"="*60)
    print(f"Total files: {len(pdf_files)}")
    print(f"Parsed: {parsed}")
    print(f"Failed: {failed}")
    print(f"Output directory: {output_dir.absolute()}")


def main():
    parser = argparse.ArgumentParser(
        description='Parse UN General Assembly draft resolution documents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Extracts:
- Document metadata (symbol, session, date, agenda item, etc.)
- Draft resolution text

Examples:
  # Parse all PDF files in a directory
  python3 parse_draft_pdf.py data/documents/pdfs/drafts

  # Parse a single file
  python3 parse_draft_pdf.py data/documents/pdfs/drafts/A_78_L.3.pdf

  # Parse first 5 files in a directory
  python3 parse_draft_pdf.py data/documents/pdfs/drafts --max-files 5
  
  # Custom output directory
  python3 parse_draft_pdf.py data/documents/pdfs/drafts -o data/parsed/pdfs/drafts
        """
    )
    parser.add_argument('input_path', type=Path, help='Path to draft PDF file or directory')
    parser.add_argument('-o', '--output', type=Path, default=None,
                        help='Output directory for JSON files (default: auto-detect from input path)')
    parser.add_argument('--max-files', type=int, default=None,
                        help='Maximum number of files to process (default: all)')

    args = parser.parse_args()

    input_path = args.input_path

    if not input_path.exists():
        parser.error(f"Path not found: {input_path}")

    if input_path.is_file():
        # Single file mode
        if args.output:
            if args.output.suffix:
                output_file = args.output
            else:
                output_file = args.output / f"{input_path.stem}.json"
        else:
            output_file = input_path.parent / f"{input_path.stem}.json"
        
        result = parse_draft_file(str(input_path))
        
        output_path_obj = Path(output_file)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path_obj, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Saved to: {output_path_obj}")
        print(f"\nStats:")
        print(f"  Word count: {result['stats']['word_count']}")
        print(f"  Line count: {result['stats']['line_count']}")
        print(f"  Has annex: {result['stats']['has_annex']}")

    else:
        # Directory mode
        input_dir = input_path
        
        if args.output:
            output_dir = args.output
        else:
            try:
                parts = list(input_dir.parts)
                documents_index = parts.index('documents')
                parts[documents_index] = 'parsed'
                output_dir = Path(*parts)
            except ValueError:
                output_dir = input_dir.parent / (input_dir.name + "_parsed")

        if args.max_files:
            print(f"Limit: First {args.max_files} files")
        print(f"Input: {input_dir}")
        print(f"Output: {output_dir}")
        
        parse_draft_files(input_dir, output_dir, args.max_files)


if __name__ == "__main__":
    main()
