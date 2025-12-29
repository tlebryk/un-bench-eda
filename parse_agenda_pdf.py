#!/usr/bin/env python3
"""
Parse UN General Assembly agenda documents.

Handles both:
- A/{session}/251: Agenda of the session
- A/{session}/252: Allocation of agenda items for the session

Extracts:
- Document metadata (symbol, session, date)
- All agenda items with hierarchy
- Associated resolutions and decisions for each item
"""

import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional
import pdfplumber


def extract_metadata(text: str) -> Dict:
    """Extract document-level metadata from agenda text"""
    metadata = {}

    # Extract symbol (e.g., A/78/251/Rev.1) - look further in text
    symbol_match = re.search(r'(A/\d+/\d+(?:/Rev\.\d+)?)', text[:2000])
    if symbol_match:
        metadata['symbol'] = symbol_match.group(1)

    # Extract session (e.g., "Seventy-eighth session")
    session_match = re.search(r'([\w-]+) session', text[:1000], re.IGNORECASE)
    if session_match:
        metadata['session_name'] = session_match.group(0)
        # Try to extract number
        num_match = re.search(r'(\d+)', session_match.group(0))
        if num_match:
            metadata['session_number'] = int(num_match.group(1))

    # Extract date
    date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', text[:1000])
    if date_match:
        metadata['date'] = date_match.group(1)

    # Extract title (handles both 251 "Agenda of the..." and 252 "Allocation of agenda items...")
    title_match = re.search(r'(?:Agenda of the|Allocation of agenda items for the) .+ session[^\n]*', text, re.IGNORECASE)
    if title_match:
        metadata['title'] = title_match.group(0).strip()
    else:
        # Fallback: look for "Allocation" pattern separately
        allocation_match = re.search(r'Allocation of .+ agenda items[^\n]*', text, re.IGNORECASE)
        if allocation_match:
            metadata['title'] = allocation_match.group(0).strip()

    return metadata


def extract_resolutions_decisions(text: str) -> Dict[str, List[str]]:
    """Extract resolutions and decisions from parenthetical text"""
    result = {'resolutions': [], 'decisions': []}

    # Find all resolution references: (resolution 78/124) or (resolutions 78/1, 78/2, ...)
    res_pattern = r'\(resolutions?\s+([\d/,\s]+(?:and\s+[\d/,\s]+)?)\)'
    for match in re.finditer(res_pattern, text):
        # Split on commas and 'and'
        items = re.split(r'[,\s]+and\s+|,\s*', match.group(1))
        for item in items:
            item = item.strip()
            if item and re.match(r'\d+/', item):
                result['resolutions'].append(item)

    # Find all decision references
    # More permissive pattern to catch complex decision lists
    dec_pattern = r'\(decisions?\s+([^)]+)\)'
    for match in re.finditer(dec_pattern, text):
        items_text = match.group(1)

        # Handle ranges like "78/528 A to D"
        for range_match in re.finditer(r'(\d+/\d+)\s+([A-Z])\s+to\s+([A-Z])', items_text):
            base = range_match.group(1)
            start = ord(range_match.group(2))
            end = ord(range_match.group(3))
            for i in range(start, end + 1):
                result['decisions'].append(f"{base} {chr(i)}")
            # Remove this range from the text so we don't process it again
            items_text = items_text.replace(range_match.group(0), '')

        # Handle patterns like "78/504 A and B"
        for ab_match in re.finditer(r'(\d+/\d+)\s+([A-Z])\s+and\s+([A-Z])', items_text):
            base = ab_match.group(1)
            result['decisions'].append(f"{base} {ab_match.group(2)}")
            result['decisions'].append(f"{base} {ab_match.group(3)}")
            # Remove from text
            items_text = items_text.replace(ab_match.group(0), '')

        # Regular comma/and-separated decisions
        items = re.split(r',\s*|\s+and\s+', items_text)
        for item in items:
            item = item.strip()
            # Match decision number with optional letter suffix
            dec_match = re.match(r'(\d+/\d+)(?:\s+([A-Z]))?', item)
            if dec_match:
                if dec_match.group(2):
                    result['decisions'].append(f"{dec_match.group(1)} {dec_match.group(2)}")
                else:
                    result['decisions'].append(dec_match.group(1))

    return result


def parse_agenda_items(text: str) -> List[Dict]:
    """Parse all agenda items from text"""
    items = []
    errors = []

    # Split into lines
    lines = text.split('\n')

    # Track current item
    current_item = None
    current_subitem = None
    item_text_buffer = []
    
    # Track current committee (for 252 documents)
    current_committee = None

    # Main item pattern: "123. Title text here..."
    main_item_pattern = re.compile(r'^(\d+)\.\s+(.+)$')

    # Sub-item pattern: "(a) Title text here..."
    sub_item_pattern = re.compile(r'^\(([a-z]{1,2})\)\s+(.+)$')

    # Section header pattern: "A. Title text here"
    section_pattern = re.compile(r'^([A-Z])\.\s+(.+)$')
    
    # Committee header pattern (for 252 documents)
    # Matches: "Plenary meetings", "First Committee", "Second Committee", etc.
    # Also handles "Special Political and Decolonization Committee (Fourth Committee)"
    committee_pattern = re.compile(
        r'^(Plenary meetings|First Committee|Second Committee|Third Committee|'
        r'Fourth Committee|Fifth Committee|Sixth Committee|'
        r'Special Political and Decolonization Committee(?:\s*\(Fourth Committee\))?)',
        re.IGNORECASE
    )

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        # Check for committee header (for 252 documents - allocation of work)
        committee_match = committee_pattern.match(line)
        if committee_match:
            # Save previous item if exists
            if current_item:
                current_item['text'] = ' '.join(item_text_buffer).strip()
                if current_committee:
                    current_item['committee'] = current_committee
                items.append(current_item)
                item_text_buffer = []
            
            # Extract committee name and normalize
            committee_name = committee_match.group(1)
            # Normalize committee names
            if 'Plenary' in committee_name:
                current_committee = 'Plenary'
            elif 'First Committee' in committee_name:
                current_committee = 'First Committee'
            elif 'Second Committee' in committee_name:
                current_committee = 'Second Committee'
            elif 'Third Committee' in committee_name:
                current_committee = 'Third Committee'
            elif 'Fourth Committee' in committee_name or 'Special Political' in committee_name:
                current_committee = 'Fourth Committee'
            elif 'Fifth Committee' in committee_name:
                current_committee = 'Fifth Committee'
            elif 'Sixth Committee' in committee_name:
                current_committee = 'Sixth Committee'
            else:
                current_committee = committee_name
            
            # Create committee header item
            items.append({
                'type': 'committee_header',
                'committee': current_committee,
                'title': committee_name,
                'item_number': None,
                'sub_item': None,
                'section_letter': None
            })
            continue

        # Check for section header
        section_match = section_pattern.match(line)
        if section_match and len(section_match.group(1)) == 1:
            # Save previous item if exists
            if current_item:
                current_item['text'] = ' '.join(item_text_buffer).strip()
                # Ensure committee is assigned if we're in one
                if current_committee and 'committee' not in current_item:
                    current_item['committee'] = current_committee
                items.append(current_item)
                item_text_buffer = []

            # Start new section (not an item, just metadata)
            current_item = {
                'type': 'section',
                'section_letter': section_match.group(1),
                'title': section_match.group(2),
                'item_number': None,
                'sub_item': None
            }
            continue

        # Check for main item
        main_match = main_item_pattern.match(line)
        if main_match:
            # Save previous item
            if current_item:
                current_item['text'] = ' '.join(item_text_buffer).strip()
                # Ensure committee is assigned if we're in one
                if current_committee and 'committee' not in current_item:
                    current_item['committee'] = current_committee
                items.append(current_item)
                item_text_buffer = []

            # Start new main item
            item_num = int(main_match.group(1))
            item_text = main_match.group(2)

            current_item = {
                'type': 'main',
                'item_number': item_num,
                'sub_item': None,
                'section_letter': None
            }
            
            # Assign to current committee if we're in one (for 252 documents)
            if current_committee:
                current_item['committee'] = current_committee

            # Carry forward section if we're in one
            if items and items[-1].get('type') == 'section':
                current_item['section_letter'] = items[-1]['section_letter']

            item_text_buffer = [item_text]
            continue

        # Check for sub-item
        sub_match = sub_item_pattern.match(line)
        if sub_match and current_item and current_item['type'] in ['main', 'section']:
            # Save previous sub-item or main item
            if item_text_buffer:
                if current_item.get('sub_item'):
                    # Was a sub-item, save it
                    sub_text = ' '.join(item_text_buffer).strip()
                    sub_item_to_save = {
                        **current_item,
                        'text': sub_text
                    }
                    # Ensure committee is assigned
                    if current_committee and 'committee' not in sub_item_to_save:
                        sub_item_to_save['committee'] = current_committee
                    items.append(sub_item_to_save)
                else:
                    # Was main item without sub-items
                    current_item['text'] = ' '.join(item_text_buffer).strip()
                    # Ensure committee is assigned
                    if current_committee and 'committee' not in current_item:
                        current_item['committee'] = current_committee
                    items.append(current_item)

                item_text_buffer = []

            # Start new sub-item
            sub_letter = sub_match.group(1)
            sub_text = sub_match.group(2)
            
            # Get parent item number and section from the item we just saved (or current_item)
            parent_item_number = current_item.get('item_number') if current_item else None
            parent_section = current_item.get('section_letter') if current_item else None

            current_item = {
                'type': 'sub',
                'item_number': parent_item_number,
                'sub_item': sub_letter,
                'section_letter': parent_section
            }
            
            # Assign to current committee if we're in one
            if current_committee:
                current_item['committee'] = current_committee
                
            item_text_buffer = [sub_text]
            continue

        # Otherwise, add to current item's text buffer
        if current_item:
            item_text_buffer.append(line)

    # Save final item
    if current_item and item_text_buffer:
        current_item['text'] = ' '.join(item_text_buffer).strip()
        if current_committee and 'committee' not in current_item:
            current_item['committee'] = current_committee
        items.append(current_item)

    # Extract resolutions/decisions for each item
    for item in items:
        if item['type'] in ['section', 'committee_header']:
            continue  # Sections and committee headers don't have resolutions

        text = item.get('text', '')
        refs = extract_resolutions_decisions(text)
        item['resolutions'] = refs['resolutions']
        item['decisions'] = refs['decisions']

    return items


def parse_agenda_file(file_path: Path) -> Dict:
    """Parse an agenda PDF file and return structured data"""

    print(f"Parsing agenda: {file_path.name}")

    # Extract text from PDF
    if file_path.suffix.lower() == '.pdf':
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
    else:
        # Fallback to reading as text file
        text = file_path.read_text(encoding='utf-8')

    # Extract metadata
    metadata = extract_metadata(text)
    print(f"  Session: {metadata.get('session_name', 'Unknown')}")
    print(f"  Symbol: {metadata.get('symbol', 'Unknown')}")

    # Parse items
    items = parse_agenda_items(text)
    print(f"  Found {len(items)} items (including sections)")

    # Add unique IDs
    doc_symbol = metadata.get('symbol')
    if doc_symbol:
        metadata['id'] = doc_symbol
        for item in items:
            item_type = item.get('type')
            item_id = None
            if item_type in ['main', 'sub']:
                item_num = item.get('item_number')
                if item_num:
                    sub_item = item.get('sub_item', '')
                    item_id = f"{doc_symbol}_item_{item_num}{sub_item}"
            elif item_type == 'section':
                section_letter = item.get('section_letter')
                if section_letter:
                    item_id = f"{doc_symbol}_section_{section_letter}"
            elif item_type == 'committee_header':
                committee = item.get('committee', '').replace(' ', '_')
                if committee:
                    item_id = f"{doc_symbol}_committee_{committee}"
            item['id'] = item_id


    # Count items with resolutions/decisions
    items_with_refs = sum(1 for item in items
                          if item.get('resolutions') or item.get('decisions'))
    print(f"  Items with resolutions/decisions: {items_with_refs}")

    return {
        'id': doc_symbol,
        'metadata': metadata,
        'items': items,
        'stats': {
            'total_items': len(items),
            'items_with_references': items_with_refs,
            'total_resolutions': sum(len(item.get('resolutions', [])) for item in items),
            'total_decisions': sum(len(item.get('decisions', [])) for item in items)
        }
    }


def detect_document_type(input_path: Path) -> str:
    """
    Detect document type from input path.
    
    Args:
        input_path: Path to file or directory
    
    Returns:
        Document type string (agenda, drafts, or other)
    """
    parts = input_path.parts
    
    # Check for known document type folders
    if 'agenda' in parts:
        return 'agenda'
    elif 'drafts' in parts:
        return 'drafts'
    else:
        return 'other'


def parse_agenda_files(input_dir: Path, output_dir: Path, max_files: Optional[int] = None):
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
        print(f"\nParsing: {pdf_file.name}")
        
        try:
            data = parse_agenda_file(pdf_file)
            
            # Create output filename
            output_filename = pdf_file.stem + '.json'
            output_path = output_dir / output_filename
            
            # Save JSON
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"  ✓ Saved: {output_filename}")
            print(f"    Symbol: {data['metadata'].get('symbol', 'N/A')}")
            print(f"    Total items: {data['stats']['total_items']}")
            print(f"    Total resolutions: {data['stats']['total_resolutions']}")
            print(f"    Total decisions: {data['stats']['total_decisions']}")
            
            parsed += 1
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
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
        description='Parse UN General Assembly agenda documents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Extracts:
- Document metadata (symbol, session, date)
- All agenda items with hierarchy
- Associated resolutions and decisions for each item

Examples:
  # Parse all PDF files in directory (auto-detects output)
  python parse_agenda_pdf.py data/documents/pdfs/agenda
  
  # Parse single file
  python parse_agenda_pdf.py data/documents/pdfs/agenda/A_78_251.pdf
  
  # Parse first 5 files
  python parse_agenda_pdf.py data/documents/pdfs/agenda --max-files 5
  
  # Custom output directory
  python parse_agenda_pdf.py data/documents/pdfs/agenda -o data/parsed/pdfs/agenda
        """
    )
    parser.add_argument('input_path', type=Path, help='Path to agenda PDF file or directory')
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
        # Single file mode (backward compatibility)
        if args.output:
            # If output is specified and is a file, use it; otherwise treat as directory
            if args.output.suffix:
                output_file = args.output
            else:
                output_file = args.output / f"{input_path.stem}.json"
        else:
            output_file = input_path.parent / f"{input_path.stem}.json"
        
        # Parse single file
        result = parse_agenda_file(input_path)
        
        # Save
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Saved to: {output_path}")
        print(f"\nStats:")
        print(f"  Total items: {result['stats']['total_items']}")
        print(f"  Total resolutions: {result['stats']['total_resolutions']}")
        print(f"  Total decisions: {result['stats']['total_decisions']}")
    
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
        
        parse_agenda_files(input_dir, output_dir, args.max_files)


if __name__ == "__main__":
    main()
