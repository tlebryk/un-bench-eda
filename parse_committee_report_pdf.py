#!/usr/bin/env python3
"""
Parse UN General Assembly committee report PDFs.

Committee reports contain:
- Document-level metadata (symbol, session, agenda item, committee, rapporteur)
- Introduction section
- Items corresponding to draft resolutions or amendments
- For each item: submission info, sponsorship, adoption status, voting details
- Full text of draft resolutions (referenced by paragraph number)
"""

from __future__ import annotations

import json
import re
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber
from pdf_utils import remove_footers_headers, collapse


DOC_PATTERN = re.compile(r'\b[A-Z]/[\dA-Z]+(?:/[A-Z0-9.\-]+)+\b')
DRAFT_RESOLUTION_PATTERN = re.compile(
    r'A/C\.(\d+)/(\d+)/L\.(\d+)(?:/Rev\.(\d+))?',
    re.IGNORECASE
)
AGENDA_ITEM_PATTERN = re.compile(
    r'Agenda item\s+(\d+)(?:\s*\(([a-z])\))?',
    re.IGNORECASE
)
PARAGRAPH_PATTERN = re.compile(r'^(\d+)\.\s+')


def extract_symbol(text: str) -> Optional[str]:
    """Extract the report symbol (e.g., A/78/481/Add.3)."""
    # Look for pattern like "A/78/481/Add.3" in first 2000 chars
    normalized = collapse(text[:2000])
    match = re.search(r'A\s*/\s*(\d+)\s*/\s*(\d+)(?:/Add\.(\d+))?', normalized)
    if match:
        session = match.group(1)
        number = match.group(2)
        addendum = match.group(3)
        if addendum:
            return f"A/{session}/{number}/Add.{addendum}"
        return f"A/{session}/{number}"
    return None


def extract_session(text: str) -> Optional[str]:
    """Extract session name (e.g., Seventy-eighth session)."""
    normalized = collapse(text[:2000])
    match = re.search(r'([A-Za-z-]+\s+session)', normalized, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip('.')
    return None


def extract_agenda_item(text: str) -> Optional[Dict[str, Any]]:
    """Extract agenda item number and sub-item."""
    normalized = collapse(text[:3000])
    match = AGENDA_ITEM_PATTERN.search(normalized)
    if match:
        return {
            'number': match.group(1),
            'sub_item': match.group(2) if match.group(2) else None,
        }
    return None


def extract_committee(text: str) -> Optional[str]:
    """Extract committee name (e.g., Third Committee)."""
    normalized = collapse(text[:2000])
    # Look for "Report of the X Committee" or "Third Committee" etc.
    match = re.search(
        r'Report of the (First|Second|Third|Fourth|Fifth|Sixth) Committee',
        normalized,
        re.IGNORECASE
    )
    if match:
        return match.group(1) + ' Committee'
    
    # Also check for just "X Committee"
    match = re.search(
        r'(First|Second|Third|Fourth|Fifth|Sixth)\s+Committee',
        normalized,
        re.IGNORECASE
    )
    if match:
        return match.group(1) + ' Committee'
    
    return None


def extract_rapporteur(text: str) -> Optional[str]:
    """Extract rapporteur name."""
    # Look for "Rapporteur: Mr. Name (Country)" pattern
    # The name can span multiple lines, so we need to be careful
    match = re.search(
        r'Rapporteur:\s*(.+?)(?:\([^)]+\)|$)',
        text[:2000],
        re.IGNORECASE | re.DOTALL
    )
    if match:
        rapporteur = match.group(1).strip()
        # Remove trailing asterisk if present
        rapporteur = rapporteur.rstrip('*')
        # Clean up - remove extra whitespace and newlines
        rapporteur = ' '.join(rapporteur.split())
        return rapporteur
    return None


def extract_metadata(text: str) -> Dict[str, Any]:
    """Extract document-level metadata."""
    metadata: Dict[str, Any] = {}
    metadata['symbol'] = extract_symbol(text)
    metadata['session'] = extract_session(text)
    metadata['committee'] = extract_committee(text)
    metadata['rapporteur'] = extract_rapporteur(text)
    
    agenda_item = extract_agenda_item(text)
    if agenda_item:
        metadata['agenda_item'] = agenda_item
    
    return {k: v for k, v in metadata.items() if v}


def parse_draft_resolution_item(text: str, start_pos: int) -> Optional[Dict[str, Any]]:
    """Parse a draft resolution item section.
    
    Looks for patterns like:
    - "A. Draft resolution A/C.3/78/L.39"
    - "B. Draft resolution A/C.3/78/L.40/Rev.1"
    
    Returns the item data or None if not found.
    """
    # Look for section header pattern
    section_pattern = re.compile(
        r'^([A-Z])\.\s+Draft resolution\s+(A/C\.\d+/\d+/L\.\d+(?:/Rev\.\d+)?)',
        re.MULTILINE | re.IGNORECASE
    )
    
    match = section_pattern.search(text, start_pos)
    if not match:
        return None
    
    section_letter = match.group(1)
    draft_symbol = match.group(2)
    
    # Extract draft symbol components
    draft_match = DRAFT_RESOLUTION_PATTERN.match(draft_symbol)
    if draft_match:
        committee = int(draft_match.group(1))
        session = int(draft_match.group(2))
        draft_num = int(draft_match.group(3))
        rev_num = int(draft_match.group(4)) if draft_match.group(4) else None
    else:
        committee = session = draft_num = None
        rev_num = None
    
    # Find where this section ends (next section or end of text)
    next_section_pattern = re.compile(
        r'^([A-Z])\.\s+Draft resolution',
        re.MULTILINE | re.IGNORECASE
    )
    next_match = next_section_pattern.search(text, match.end())
    end_pos = next_match.start() if next_match else len(text)
    
    item_text = text[match.start():end_pos]
    
    # Extract title (usually in quotes after "entitled")
    # Handle both straight and curly quotes
    title_match = re.search(
        r'entitled\s+["""\u201C\u201D](.+?)["""\u201C\u201D]',
        item_text,
        re.IGNORECASE | re.DOTALL
    )
    if title_match:
        title = title_match.group(1).strip()
        # Clean up any extra whitespace
        title = ' '.join(title.split())
    else:
        title = None
    
    # Extract submission info
    submission_info = None
    submission_match = re.search(
        r'submitted by\s+(.+?)(?:\.|,|$)',
        item_text,
        re.IGNORECASE | re.DOTALL
    )
    if submission_match:
        submission_info = collapse(submission_match.group(1))
    
    # Extract sponsorship info
    sponsors = []
    sponsor_matches = re.finditer(
        r'joined in sponsoring the draft resolution',
        item_text,
        re.IGNORECASE
    )
    for sponsor_match in sponsor_matches:
        # Look backwards for the sponsor list
        before_text = item_text[max(0, sponsor_match.start()-200):sponsor_match.start()]
        # Find the last sentence before "joined in sponsoring"
        sponsor_sentence = re.search(r'([^.]{10,200})joined in sponsoring', before_text, re.IGNORECASE)
        if sponsor_sentence:
            sponsor_text = sponsor_sentence.group(1).strip()
            # Clean up and extract state names
            sponsor_text = re.sub(r'^(?:Also at the same meeting,|At the same meeting,)\s*', '', sponsor_text, flags=re.IGNORECASE)
            sponsors.append(sponsor_text)
    
    # Extract adoption info
    adoption_info = None
    adoption_status = None
    vote_info = None
    
    # Check for "adopted without a vote"
    if re.search(r'adopted\s+without\s+a\s+vote', item_text, re.IGNORECASE):
        adoption_status = 'adopted'
        vote_info = 'without a vote'
    # Check for "adopted by a recorded vote"
    elif re.search(r'adopted\s+by\s+a\s+recorded\s+vote', item_text, re.IGNORECASE):
        adoption_status = 'adopted'
        vote_match = re.search(
            r'adopted\s+by\s+a\s+recorded\s+vote\s+of\s+(\d+)\s+to\s+(\d+)(?:,\s+with\s+(\d+)\s+abstention)?',
            item_text,
            re.IGNORECASE
        )
        if vote_match:
            vote_info = {
                'type': 'recorded_vote',
                'in_favor': int(vote_match.group(1)),
                'against': int(vote_match.group(2)),
                'abstentions': int(vote_match.group(3)) if vote_match.group(3) else 0,
            }
    # Check for "adopted"
    elif re.search(r'adopted\s+draft resolution', item_text, re.IGNORECASE):
        adoption_status = 'adopted'
    
    # Extract reference to full text (e.g., "see para. 33, draft resolution I")
    text_reference = None
    ref_match = re.search(
        r'see\s+para\.\s+(\d+),\s+draft resolution\s+([IVX]+|\d+)',
        item_text,
        re.IGNORECASE
    )
    if ref_match:
        text_reference = {
            'paragraph': int(ref_match.group(1)),
            'draft_number': ref_match.group(2),
        }
    
    # Extract vote lists if present (using the same function from meeting parser)
    # But first, we need to handle committee report format which may have different end markers
    from parse_meeting_pdf import _extract_vote_lists, _parse_state_list
    
    # In committee reports, vote lists might end with paragraph numbers or "Before the vote"
    # Let's extract vote lists manually with committee report-specific end markers
    vote_details = {}
    
    in_favour_pos = item_text.find('In favour:')
    against_pos = item_text.find('Against:')
    abstaining_pos = item_text.find('Abstaining:')
    
    if in_favour_pos == -1:
        in_favour_pos = item_text.find('In favor:')
    if abstaining_pos == -1:
        abstaining_pos = item_text.find('Abstentions:')
    
    # Extract "In favour" list
    if in_favour_pos != -1:
        # End markers for committee reports
        end_markers = ['Against:', 'Abstaining:', 'Abstentions:', 'Before the vote', 'After the vote', r'\d+\.\s+Before', r'\d+\.\s+After']
        end_pos = len(item_text)
        for marker in end_markers:
            if marker.startswith('\\d'):
                # Regex pattern
                marker_match = re.search(marker, item_text[in_favour_pos + 1:], re.IGNORECASE)
                if marker_match:
                    marker_pos = in_favour_pos + 1 + marker_match.start()
                    if marker_pos < end_pos:
                        end_pos = marker_pos
            else:
                marker_pos = item_text.find(marker, in_favour_pos + 1)
                if marker_pos != -1 and marker_pos < end_pos:
                    end_pos = marker_pos
        
        in_favour_text = item_text[in_favour_pos + len('In favour:'):end_pos].strip()
        # Remove document references
        in_favour_text = re.sub(r'A/\d+/\d+(?:/Add\.\d+)?', '', in_favour_text)
        states = _parse_state_list(in_favour_text)
        if states:
            vote_details['in_favour'] = states
    
    # Extract "Against" list
    if against_pos != -1:
        end_markers = ['Abstaining:', 'Abstentions:', 'Before the vote', 'After the vote', r'\d+\.\s+Before', r'\d+\.\s+After']
        end_pos = len(item_text)
        for marker in end_markers:
            if marker.startswith('\\d'):
                marker_match = re.search(marker, item_text[against_pos + 1:], re.IGNORECASE)
                if marker_match:
                    marker_pos = against_pos + 1 + marker_match.start()
                    if marker_pos < end_pos:
                        end_pos = marker_pos
            else:
                marker_pos = item_text.find(marker, against_pos + 1)
                if marker_pos != -1 and marker_pos < end_pos:
                    end_pos = marker_pos
        
        against_text = item_text[against_pos + len('Against:'):end_pos].strip()
        against_text = re.sub(r'A/\d+/\d+(?:/Add\.\d+)?', '', against_text)
        states = _parse_state_list(against_text)
        if states:
            vote_details['against'] = states
    
    # Extract "Abstaining" list
    if abstaining_pos != -1:
        end_markers = ['Before the vote', 'After the vote', r'\d+\.\s+Before', r'\d+\.\s+After', r'III\.', 'Recommendations']
        end_pos = len(item_text)
        for marker in end_markers:
            if marker.startswith('\\d') or marker.startswith('III'):
                marker_match = re.search(marker, item_text[abstaining_pos + 1:], re.IGNORECASE)
                if marker_match:
                    marker_pos = abstaining_pos + 1 + marker_match.start()
                    if marker_pos < end_pos:
                        end_pos = marker_pos
            else:
                marker_pos = item_text.find(marker, abstaining_pos + 1)
                if marker_pos != -1 and marker_pos < end_pos:
                    end_pos = marker_pos
        
        abstaining_text = item_text[abstaining_pos + len('Abstaining:'):end_pos].strip()
        # Also handle "Abstentions:"
        if abstaining_pos == item_text.find('Abstentions:'):
            abstaining_text = item_text[abstaining_pos + len('Abstentions:'):end_pos].strip()
        abstaining_text = re.sub(r'A/\d+/\d+(?:/Add\.\d+)?', '', abstaining_text)
        states = _parse_state_list(abstaining_text)
        if states:
            vote_details['abstaining'] = states
    
    vote_details = vote_details if vote_details else None
    
    return {
        'section_letter': section_letter,
        'draft_symbol': draft_symbol,
        'draft_committee': committee,
        'draft_session': session,
        'draft_number': draft_num,
        'draft_revision': rev_num,
        'title': title,
        'submission_info': submission_info,
        'sponsors': sponsors,
        'adoption_status': adoption_status,
        'vote_info': vote_info,
        'vote_details': vote_details if vote_details else None,
        'text_reference': text_reference,
        'item_text': item_text,
    }


def parse_items(text: str) -> List[Dict[str, Any]]:
    """Parse all draft resolution items from the report."""
    items = []
    
    # Find "Consideration of proposals" section
    consideration_pos = text.find('Consideration of proposals')
    if consideration_pos == -1:
        consideration_pos = text.find('II.')
        if consideration_pos == -1:
            return items
    
    # Start parsing from consideration section
    current_pos = consideration_pos
    
    while current_pos < len(text):
        item = parse_draft_resolution_item(text, current_pos)
        if not item:
            break
        
        items.append(item)
        # Move past this item - find where the item text ends
        item_text = item.get('item_text', '')
        if item_text:
            # Find the end of this item's text in the main text
            item_start = text.find(item_text, current_pos)
            if item_start != -1:
                current_pos = item_start + len(item_text)
            else:
                # Fallback: move forward by a reasonable amount
                current_pos += 500
        else:
            break
    
    return items


def parse_committee_report_file(file_path: str) -> Dict[str, Any]:
    """Parse a committee report PDF file into structured data."""
    path = Path(file_path)
    
    # Extract text from PDF with header/footer removal
    if path.suffix.lower() == '.pdf':
        with pdfplumber.open(str(path)) as pdf:
            pages_text = []
            for page_num, page in enumerate(pdf.pages, 1):
                raw_text = page.extract_text() or ""
                cleaned_text = remove_footers_headers(raw_text, page_num)
                pages_text.append(cleaned_text)
            text = '\n'.join(pages_text)
    else:
        text = path.read_text(encoding='utf-8')
    
    # Extract metadata
    metadata = extract_metadata(text)
    
    # Parse items
    items = parse_items(text)
    
    # Extract introduction (text before "Consideration of proposals")
    introduction_pos = text.find('Consideration of proposals')
    if introduction_pos == -1:
        introduction_pos = text.find('II.')
    introduction = text[:introduction_pos].strip() if introduction_pos > 0 else None
    
    return {
        'source_file': str(path),
        'metadata': metadata,
        'introduction': introduction,
        'items': items,
        'stats': {
            'item_count': len(items),
            'items_with_votes': sum(1 for item in items if item.get('vote_details')),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Parse UN General Assembly committee report PDFs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Extracts:
- Document-level metadata (symbol, session, agenda item, committee, rapporteur)
- Introduction section
- Items corresponding to draft resolutions
- For each item: submission, sponsorship, adoption, voting details

Example:
  python3 parse_committee_report_pdf.py data/documents/pdfs/committee-reports/A_78_481_Add.3.pdf
        """
    )
    parser.add_argument('input_file', type=Path, help='Path to committee report PDF file')
    parser.add_argument('-o', '--output', type=Path, default=None,
                        help='Output JSON file path (default: <input_file>_parsed.json)')

    args = parser.parse_args()

    input_file = args.input_file
    if args.output:
        output_file = args.output
    else:
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_parsed.json"

    result = parse_committee_report_file(input_file)

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"✓ Parsed committee report saved to {output_path}")
    print(f"Items: {result['stats']['item_count']}, "
          f"Items with votes: {result['stats']['items_with_votes']}")


if __name__ == "__main__":
    main()

