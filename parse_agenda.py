#!/usr/bin/env python3
"""
Parse UN General Assembly agenda documents.

Extracts:
- Document metadata (symbol, session, date)
- All agenda items with hierarchy
- Associated resolutions and decisions for each item
"""

import re
import json
import sys
from pathlib import Path
from typing import Dict, List
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

    # Extract title
    title_match = re.search(r'Agenda of the .+ session[^\n]*', text, re.IGNORECASE)
    if title_match:
        metadata['title'] = title_match.group(0).strip()

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

    # Main item pattern: "123. Title text here..."
    main_item_pattern = re.compile(r'^(\d+)\.\s+(.+)$')

    # Sub-item pattern: "(a) Title text here..."
    sub_item_pattern = re.compile(r'^\(([a-z]{1,2})\)\s+(.+)$')

    # Section header pattern: "A. Title text here"
    section_pattern = re.compile(r'^([A-Z])\.\s+(.+)$')

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        # Check for section header
        section_match = section_pattern.match(line)
        if section_match and len(section_match.group(1)) == 1:
            # Save previous item if exists
            if current_item:
                current_item['text'] = ' '.join(item_text_buffer).strip()
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
                    items.append({
                        **current_item,
                        'text': sub_text
                    })
                else:
                    # Was main item without sub-items
                    current_item['text'] = ' '.join(item_text_buffer).strip()
                    items.append(current_item)

                item_text_buffer = []

            # Start new sub-item
            sub_letter = sub_match.group(1)
            sub_text = sub_match.group(2)

            current_item = {
                'type': 'sub',
                'item_number': current_item['item_number'],
                'sub_item': sub_letter,
                'section_letter': current_item.get('section_letter')
            }
            item_text_buffer = [sub_text]
            continue

        # Otherwise, add to current item's text buffer
        if current_item:
            item_text_buffer.append(line)

    # Save final item
    if current_item and item_text_buffer:
        current_item['text'] = ' '.join(item_text_buffer).strip()
        items.append(current_item)

    # Extract resolutions/decisions for each item
    for item in items:
        if item['type'] == 'section':
            continue  # Sections don't have resolutions

        text = item.get('text', '')
        refs = extract_resolutions_decisions(text)
        item['resolutions'] = refs['resolutions']
        item['decisions'] = refs['decisions']

        # Create ID
        if item['item_number']:
            if item.get('sub_item'):
                item['id'] = f"{item['item_number']}{item['sub_item']}"
            else:
                item['id'] = str(item['item_number'])
        else:
            item['id'] = None

    return items


def parse_agenda_file(file_path: str) -> Dict:
    """Parse an agenda PDF file and return structured data"""

    print(f"Parsing agenda: {file_path}")

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
    print(f"  Session: {metadata.get('session_name', 'Unknown')}")
    print(f"  Symbol: {metadata.get('symbol', 'Unknown')}")

    # Parse items
    items = parse_agenda_items(text)
    print(f"  Found {len(items)} items (including sections)")

    # Count items with resolutions/decisions
    items_with_refs = sum(1 for item in items
                          if item.get('resolutions') or item.get('decisions'))
    print(f"  Items with resolutions/decisions: {items_with_refs}")

    return {
        'metadata': metadata,
        'items': items,
        'stats': {
            'total_items': len(items),
            'items_with_references': items_with_refs,
            'total_resolutions': sum(len(item.get('resolutions', [])) for item in items),
            'total_decisions': sum(len(item.get('decisions', [])) for item in items)
        }
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 parse_agenda.py <agenda.pdf> [output.json]")
        sys.exit(1)

    input_file = sys.argv[1]

    # Generate output filename
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    else:
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_parsed.json"

    # Parse
    result = parse_agenda_file(input_file)

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


if __name__ == "__main__":
    main()
