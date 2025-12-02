#!/usr/bin/env python3
"""
Parse UN General Assembly plenary meeting (PV) records.

The parser extracts:
- Document-level metadata (symbol, session, meeting number, date/time, presiding officer)
- Each agenda item section with referenced documents
- Ordered utterances (speaker metadata + text + referenced documents)
"""

from __future__ import annotations

import json
import re
import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber


DOC_PATTERN = re.compile(r'\b[A-Z]/[\dA-Z]+(?:/[A-Z0-9.\-]+)+\b')
AGENDA_PATTERN = re.compile(
    r'^\s*Agenda item\s+(?P<number>\d+[A-Za-z]*)\s*(?P<rest>\([^)]+\))?(?P<title>.*)$',
    re.IGNORECASE,
)
SPEAKER_PATTERN = re.compile(
    r'(?P<header>(?:The\s+(?:Acting\s+)?President|The\s+Vice-President|The\s+Secretary-General|'
    r'Mr\.|Ms\.|Mrs\.|Dr\.|Sir|Madam|Ambassador|H\.E\.)[^\n:]{0,120})\s*:\s*(?P<body>.*)',
    re.IGNORECASE,
)


def collapse(text: str) -> str:
    """Collapse internal whitespace."""
    return re.sub(r'\s+', ' ', text.strip())


def detect_column_boundary(page: pdfplumber.page.Page) -> Optional[float]:
    """Detect the x-position boundary between left and right columns.
    
    Returns the x-coordinate that separates left and right columns, or None if
    single column or detection fails.
    """
    words = page.extract_words()
    if not words or len(words) < 10:
        return None
    
    x_positions = [w['x0'] for w in words]
    midpoint = page.width / 2
    
    # Find the largest gap near the middle of the page
    sorted_x = sorted(set(x_positions))
    gaps = []
    for i in range(len(sorted_x) - 1):
        gap = sorted_x[i+1] - sorted_x[i]
        gap_center = (sorted_x[i] + sorted_x[i+1]) / 2
        # Look for gaps near the middle (within 100 points of center)
        if abs(gap_center - midpoint) < 100 and gap > 5:
            gaps.append((gap, sorted_x[i], sorted_x[i+1]))
    
    if gaps:
        # Use the largest gap near the middle
        largest_gap = max(gaps, key=lambda x: x[0])
        # Return the midpoint of the gap as the boundary
        return (largest_gap[1] + largest_gap[2]) / 2
    
    # Fallback: if words are roughly evenly distributed on both sides, use page midpoint
    left_count = sum(1 for x in x_positions if x < midpoint)
    right_count = sum(1 for x in x_positions if x >= midpoint)
    if left_count > 10 and right_count > 10:
        return midpoint
    
    return None


def extract_text_with_column_info(file_path: Path) -> List[Tuple[str, Optional[int], int]]:
    """Extract text from PDF with column and page information.
    
    Returns a list of (text, column, page_num) tuples where column is:
    - 0 for left column
    - 1 for right column  
    - None for single column or unknown
    
    Each tuple represents text from one column on one page.
    """
    if file_path.suffix.lower() != '.pdf':
        # For non-PDF files, return as single column
        text = file_path.read_text(encoding='utf-8')
        return [(text, None, 0)]
    
    result = []
    with pdfplumber.open(str(file_path)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            words = page.extract_words()
            if not words:
                continue
            
            column_boundary = detect_column_boundary(page)
            
            if column_boundary is None:
                # Single column - extract normally
                text = page.extract_text() or ''
                if text.strip():
                    result.append((text, None, page_num))
            else:
                # Two columns - extract separately
                left_words = [w for w in words if w['x0'] < column_boundary]
                right_words = [w for w in words if w['x0'] >= column_boundary]
                
                # Sort words by y-position (top to bottom), then x-position
                left_words.sort(key=lambda w: (w['top'], w['x0']))
                right_words.sort(key=lambda w: (w['top'], w['x0']))
                
                # Reconstruct text for each column, preserving line structure
                if left_words:
                    left_text = _reconstruct_text_from_words(left_words)
                    result.append((left_text, 0, page_num))
                
                if right_words:
                    right_text = _reconstruct_text_from_words(right_words)
                    result.append((right_text, 1, page_num))
    
    return result


def _reconstruct_text_from_words(words: List[Dict[str, Any]]) -> str:
    """Reconstruct text from words, preserving line breaks based on y-position.
    
    Groups words that are on the same line (similar y-position) and sorts
    them by x-position within each line.
    """
    if not words:
        return ''
    
    # Group words by approximate line (similar y-position)
    # Use a tolerance of 3 points to group words on the same line
    lines_dict: Dict[int, List[Tuple[float, str]]] = {}
    for word in words:
        word_text = word.get('text', '')
        word_y = word.get('top', 0)
        word_x = word.get('x0', 0)
        
        # Round y to nearest 3 to group words on same line
        line_key = int(round(word_y / 3)) * 3
        
        if line_key not in lines_dict:
            lines_dict[line_key] = []
        lines_dict[line_key].append((word_x, word_text))
    
    # Sort lines by y-position, and within each line sort by x-position
    sorted_lines = sorted(lines_dict.items())
    lines = []
    for line_y, word_list in sorted_lines:
        # Sort words in this line by x-position
        word_list.sort(key=lambda x: x[0])
        # Join words with spaces
        line_text = ' '.join([text for _, text in word_list])
        lines.append(line_text)
    
    return '\n'.join(lines)


def load_text(file_path: Path) -> str:
    """Extract text from PDF or fallback text file.
    
    For PDFs, extracts text column by column and processes to only include
    text from the column where each agenda item appears.
    """
    if file_path.suffix.lower() != '.pdf':
        return file_path.read_text(encoding='utf-8')
    
    # Extract text with column information
    column_texts = extract_text_with_column_info(file_path)
    
    # Process to filter text by column for each agenda item
    return _process_column_text(column_texts)


def _process_column_text(column_texts: List[Tuple[str, Optional[int], int]]) -> str:
    """Process column-aware text to only include relevant column for each agenda item.
    
    When an agenda item is found, determines which column it's in and only
    includes subsequent text from that column until the next agenda item.
    Pages are processed in order, with columns processed left-to-right.
    """
    if not column_texts:
        return ''
    
    # If all text is single column (None), just join it
    if all(col is None for _, col, _ in column_texts):
        return '\n'.join([text for text, _, _ in column_texts])
    
    # Build a map of agenda items to their columns
    agenda_column_map: Dict[str, Optional[int]] = {}
    
    # First pass: find which column each agenda item is in
    for text, column, _ in column_texts:
        if column is None:
            continue
        for match in AGENDA_PATTERN.finditer(text):
            agenda_num = match.group('number')
            # Use the column where this agenda item was found
            agenda_column_map[agenda_num] = column
    
    # Second pass: reconstruct text, filtering by column
    result_lines = []
    current_agenda_column: Optional[int] = None
    
    # Group by page, then process columns left-to-right (0 then 1) within each page
    page_texts: Dict[int, List[Tuple[str, Optional[int]]]] = defaultdict(list)
    for text, column, page_num in column_texts:
        page_texts[page_num].append((text, column))
    
    # Process pages in order
    for page_num in sorted(page_texts.keys()):
        # Process columns in order: None first (single column), then 0 (left), then 1 (right)
        page_cols = page_texts[page_num]
        page_cols.sort(key=lambda x: (x[1] if x[1] is not None else -1,))
        
        for text, column in page_cols:
            lines = text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check if this line starts a new agenda item
                agenda_match = AGENDA_PATTERN.match(line)
                if agenda_match:
                    agenda_num = agenda_match.group('number')
                    # Update current column to match this agenda item's column
                    current_agenda_column = agenda_column_map.get(agenda_num)
                    result_lines.append(line)
                    continue
                
                # If we're in an agenda item section, only include text from its column
                if current_agenda_column is not None:
                    if column == current_agenda_column:
                        result_lines.append(line)
                else:
                    # No current agenda item, include all text (for preface)
                    result_lines.append(line)
    
    return '\n'.join(result_lines)


def normalize_for_regex(text: str) -> str:
    """Normalize text for regex matching (remove newlines, collapse spaces)."""
    return collapse(text.replace('\n', ' '))


def extract_symbol(text: str) -> Optional[str]:
    """Extract the meeting symbol (e.g., A/78/PV.51)."""
    normalized = normalize_for_regex(text[:3000])
    match = re.search(r'A\s*/\s*(\d+)\s*/\s*(PV\.\d+)', normalized, re.IGNORECASE)
    if match:
        return f"A/{match.group(1)}/{match.group(2).upper()}"
    return None


def extract_session(text: str) -> Optional[str]:
    """Extract session name (e.g., Seventy-eighth session)."""
    normalized = normalize_for_regex(text[:2000])
    match = re.search(r'([A-Za-z-]+\s+session)', normalized, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip('.')
    return None


def extract_meeting_number(text: str) -> Optional[int]:
    normalized = normalize_for_regex(text[:2000])
    match = re.search(r'(\d+)\s*(?:st|nd|rd|th)\s+plenary meeting', normalized, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def extract_datetime(text: str) -> Optional[str]:
    normalized = normalize_for_regex(text[:2000])
    match = re.search(
        r'([A-Za-z]+,\s+\d{1,2}\s+[A-Za-z]+\s+\d{4},\s+[0-9\.apm\s]+)',
        normalized,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).replace(' .', '.').strip()
    return None


def extract_location(text: str) -> Optional[str]:
    normalized = normalize_for_regex(text[:2000])
    match = re.search(r'(New York|Geneva|Vienna)', normalized, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def extract_president_line(text: str) -> Optional[str]:
    header = text[:2000]
    for line in header.splitlines():
        if line.strip().startswith('President:'):
            return collapse(line.split('President:', 1)[1])
    return None


def extract_chair_line(text: str) -> Optional[str]:
    header = text[:2000]
    for line in header.splitlines():
        if 'took the Chair' in line:
            return collapse(line)
    return None


def extract_meeting_start(text: str) -> Optional[str]:
    match = re.search(r'The meeting was called to order at ([^.\n]+)', text)
    if match:
        return collapse(match.group(1))
    return None


def extract_metadata(text: str) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    metadata['symbol'] = extract_symbol(text)
    metadata['session'] = extract_session(text)
    metadata['meeting_number'] = extract_meeting_number(text)
    metadata['datetime'] = extract_datetime(text)
    metadata['location'] = extract_location(text)
    metadata['president'] = extract_president_line(text)
    metadata['chair'] = extract_chair_line(text)
    metadata['called_to_order_at'] = extract_meeting_start(text)
    metadata['agenda_items'] = extract_all_agenda_items(text)
    return {k: v for k, v in metadata.items() if v}


def extract_all_agenda_items(text: str) -> List[str]:
    items = []
    for match in re.finditer(r'Agenda item\s+\d+[^\n]*', text, re.IGNORECASE):
        items.append(collapse(match.group(0)))
    return items


def parse_speaker_header(header: str) -> Dict[str, Any]:
    """Extract speaker metadata from header text."""
    cleaned = collapse(re.sub(r'\.{3,}', ' ', header))
    result: Dict[str, Any] = {'raw': cleaned}

    affiliation = None
    aff_match = re.search(r'(.+?)\s*\(([^)]+)\)\s*$', cleaned)
    if aff_match:
        cleaned = aff_match.group(1).strip()
        affiliation = aff_match.group(2).strip()
        result['affiliation'] = affiliation

    if cleaned.lower().startswith('the '):
        result['role'] = cleaned
        result['name'] = cleaned
    else:
        honorific_match = re.match(r'^(Mr\.|Ms\.|Mrs\.|Dr\.|Sir|Madam|Ambassador)\s+(.*)$', cleaned)
        if honorific_match:
            result['honorific'] = honorific_match.group(1)
            result['name'] = honorific_match.group(2).strip()
        else:
            result['name'] = cleaned

    return result


def detect_documents(line: str) -> List[Dict[str, str]]:
    docs = []
    for symbol in DOC_PATTERN.findall(line):
        docs.append({'symbol': symbol, 'context': collapse(line)})
    return docs


def merge_documents(existing: List[Dict[str, str]], new_docs: List[Dict[str, str]]) -> None:
    seen = {(doc['symbol'], doc['context']) for doc in existing}
    for doc in new_docs:
        key = (doc['symbol'], doc['context'])
        if key not in seen:
            existing.append(doc)
            seen.add(key)


def _parse_state_list(text: str) -> List[str]:
    """Parse a comma-separated list of state names.
    
    Handles states with parentheses (e.g., "Micronesia (Federated States of)")
    and cleans up the names.
    """
    if not text or not text.strip():
        return []
    
    states = []
    current_state = []
    paren_depth = 0
    
    # Split by commas, but be careful with parentheses
    i = 0
    while i < len(text):
        char = text[i]
        
        if char == '(':
            paren_depth += 1
            current_state.append(char)
        elif char == ')':
            paren_depth -= 1
            current_state.append(char)
        elif char == ',' and paren_depth == 0:
            # This comma separates states
            state_name = ''.join(current_state).strip()
            if state_name:
                states.append(state_name)
            current_state = []
        else:
            current_state.append(char)
        
        i += 1
    
    # Add the last state
    if current_state:
        state_name = ''.join(current_state).strip()
        if state_name:
            states.append(state_name)
    
    # Clean up state names
    cleaned_states = []
    for state in states:
        # Remove extra whitespace
        state = ' '.join(state.split())
        # Remove page numbers and document references (e.g., "5/34 A/78/PV.50")
        # This can appear anywhere in the state name
        state = re.sub(r'\s*\d+/\d+\s+A/\d+/[A-Z0-9.]+', '', state)
        # Remove "Draft resolution" or similar text that got included
        state = re.sub(r'\s+Draft\s+resolution.*$', '', state, flags=re.IGNORECASE)
        # Remove trailing periods (unless part of abbreviation)
        if state.endswith('.') and not re.search(r'\b[A-Z]\.$', state):
            state = state[:-1].strip()
        # Clean up any double spaces created
        state = ' '.join(state.split())
        state = state.strip()
        if state:
            cleaned_states.append(state)
    
    return cleaned_states


def _parse_state_list(text: str) -> List[str]:
    """Parse a comma-separated list of state names.
    
    Handles states with parentheses (e.g., "Micronesia (Federated States of)")
    and cleans up the names.
    """
    if not text or not text.strip():
        return []
    
    states = []
    current_state = []
    paren_depth = 0
    
    # Split by commas, but be careful with parentheses
    i = 0
    while i < len(text):
        char = text[i]
        
        if char == '(':
            paren_depth += 1
            current_state.append(char)
        elif char == ')':
            paren_depth -= 1
            current_state.append(char)
        elif char == ',' and paren_depth == 0:
            # This comma separates states
            state_name = ''.join(current_state).strip()
            if state_name:
                states.append(state_name)
            current_state = []
        else:
            current_state.append(char)
        
        i += 1
    
    # Add the last state
    if current_state:
        state_name = ''.join(current_state).strip()
        if state_name:
            states.append(state_name)
    
    # Clean up state names
    cleaned_states = []
    for state in states:
        # Remove extra whitespace
        state = ' '.join(state.split())
        # Remove page numbers and document references (e.g., "5/34 A/78/PV.50")
        # This can appear anywhere in the state name
        state = re.sub(r'\s*\d+/\d+\s+A/\d+/[A-Z0-9.]+', '', state)
        # Remove "Draft resolution" or similar text that got included
        state = re.sub(r'\s+Draft\s+resolution.*$', '', state, flags=re.IGNORECASE)
        # Remove trailing periods (unless part of abbreviation)
        if state.endswith('.') and not re.search(r'\b[A-Z]\.$', state):
            state = state[:-1].strip()
        # Clean up any double spaces created
        state = ' '.join(state.split())
        state = state.strip()
        if state:
            cleaned_states.append(state)
    
    return cleaned_states


def _extract_vote_lists(text: str) -> Dict[str, Any]:
    """Extract lists of states from vote records.
    
    Looks for "In favour:", "Against:", and "Abstaining:" sections
    and extracts the comma-separated list of states.
    
    Returns:
        Dict with 'in_favour', 'against', 'abstaining' lists of state names
    """
    result: Dict[str, Any] = {}
    
    # Find positions of vote section markers
    in_favour_pos = text.find('In favour:')
    against_pos = text.find('Against:')
    abstaining_pos = text.find('Abstaining:')
    
    # Also check for alternative spellings
    if in_favour_pos == -1:
        in_favour_pos = text.find('In favor:')
    if abstaining_pos == -1:
        abstaining_pos = text.find('Abstentions:')
    
    # Extract "In favour" list
    if in_favour_pos != -1:
        # Find where this section ends (next marker or "Draft resolution" or "was adopted")
        end_markers = ['Against:', 'Abstaining:', 'Abstentions:', 'Draft resolution', 'was adopted']
        end_pos = len(text)
        for marker in end_markers:
            marker_pos = text.find(marker, in_favour_pos + 1)
            if marker_pos != -1 and marker_pos < end_pos:
                end_pos = marker_pos
        
        in_favour_text = text[in_favour_pos + len('In favour:'):end_pos].strip()
        # Remove any trailing page numbers or dates
        in_favour_text = re.sub(r'\d+/\d+\s+\d{2}/\d{2}/\d{4}.*$', '', in_favour_text)
        states = _parse_state_list(in_favour_text)
        if states:
            result['in_favour'] = states
    
    # Extract "Against" list
    if against_pos != -1:
        end_markers = ['Abstaining:', 'Abstentions:', 'Draft resolution', 'was adopted']
        end_pos = len(text)
        for marker in end_markers:
            marker_pos = text.find(marker, against_pos + 1)
            if marker_pos != -1 and marker_pos < end_pos:
                end_pos = marker_pos
        
        against_text = text[against_pos + len('Against:'):end_pos].strip()
        against_text = re.sub(r'\d+/\d+\s+\d{2}/\d{2}/\d{4}.*$', '', against_text)
        states = _parse_state_list(against_text)
        if states:
            result['against'] = states
    
    # Extract "Abstaining" list
    if abstaining_pos != -1:
        end_pos = len(text)
        
        # Check for literal markers
        for marker in ['Draft resolution', 'was adopted']:
            marker_pos = text.find(marker, abstaining_pos + 1)
            if marker_pos != -1 and marker_pos < end_pos:
                end_pos = marker_pos
        
        # Check for regex patterns
        pattern_match = re.search(r'(?:by\s+\d+\s+votes|resolution\s+\d+/\d+)', text[abstaining_pos + 1:], re.IGNORECASE)
        if pattern_match:
            pattern_pos = abstaining_pos + 1 + pattern_match.start()
            if pattern_pos < end_pos:
                end_pos = pattern_pos
        
        abstaining_text = text[abstaining_pos + len('Abstaining:'):end_pos].strip()
        # Also handle "Abstentions:"
        if abstaining_pos == text.find('Abstentions:'):
            abstaining_text = text[abstaining_pos + len('Abstentions:'):end_pos].strip()
        abstaining_text = re.sub(r'\d+/\d+\s+\d{2}/\d{2}/\d{4}.*$', '', abstaining_text)
        states = _parse_state_list(abstaining_text)
        if states:
            result['abstaining'] = states
    
    return result


def extract_resolution_metadata(text: str) -> Dict[str, Any]:
    """Extract resolution-related metadata from utterance text.
    
    Extracts:
    - Draft resolution identifier (I, II, III, etc.)
    - Resolution title (from "entitled" quotes)
    - Resolution number (e.g., "78/225")
    - Adoption status (adopted, rejected, etc.)
    - Vote information (without a vote, vote counts, etc.)
    - Vote details (lists of states in favour, against, abstaining)
    """
    metadata: Dict[str, Any] = {}
    
    # Pattern for draft resolution identifier: "Draft resolution I/II/III/IV/V" or "draft resolution 1/2/3"
    draft_res_pattern = re.compile(
        r'(?:Draft|draft)\s+resolution\s+(?:I{1,3}|IV|V|VI{0,3}|[1-9]\d*)',
        re.IGNORECASE
    )
    draft_match = draft_res_pattern.search(text)
    if draft_match:
        draft_text = draft_match.group(0)
        # Extract the identifier (Roman numeral or number)
        identifier_match = re.search(r'(?:Draft|draft)\s+resolution\s+(I{1,3}|IV|V|VI{0,3}|[1-9]\d*)', draft_text, re.IGNORECASE)
        if identifier_match:
            metadata['draft_resolution_identifier'] = identifier_match.group(1).upper()
    
    # Pattern for title: text in quotes after "entitled"
    # Handle both straight quotes (") and curly quotes (" " U+201C U+201D)
    # Also handle quotes followed by period
    # Be more careful: look for the pattern and limit title length to prevent over-matching
    title_pattern = re.compile(
        r'entitled\s+["""\u201C\u201D](.+?)["""\u201C\u201D]\.?',
        re.IGNORECASE | re.DOTALL
    )
    title_match = title_pattern.search(text)
    if title_match:
        title = title_match.group(1).strip()
        # If title is suspiciously long (likely over-matched), try to find a sentence boundary
        # Titles are typically short phrases, not multiple paragraphs
        if len(title) > 200:
            # Try to find a period followed by space or newline within first 200 chars
            # This handles cases where closing quote is missing
            sentence_end = re.search(r'\.(?:\s|\n|$)', title[:200])
            if sentence_end:
                title = title[:sentence_end.start()].strip()
        # Clean up any extra whitespace
        title = ' '.join(title.split())
        # Final sanity check: if still too long, truncate at first sentence
        if len(title) > 300:
            # Find first sentence boundary
            first_sentence = re.search(r'^([^.]{1,300})(?:\.|$)', title)
            if first_sentence:
                title = first_sentence.group(1).strip()
        metadata['resolution_title'] = title
    
    # Pattern for resolution number: "resolution 78/225" or "(resolution 78/225)"
    resolution_pattern = re.compile(
        r'\(?resolution\s+(\d+/\d+)\)?',
        re.IGNORECASE
    )
    resolution_match = resolution_pattern.search(text)
    if resolution_match:
        metadata['resolution_number'] = resolution_match.group(1)
        # Also create full symbol
        session_match = re.search(r'(\d+)/\d+', resolution_match.group(1))
        if session_match:
            session = session_match.group(1)
            res_num = resolution_match.group(1).split('/')[1]
            metadata['resolution_symbol'] = f"A/RES/{session}/{res_num}"
    
    # Pattern for adoption status
    adoption_patterns = [
        (r'was\s+adopted', 'adopted'),
        (r'was\s+rejected', 'rejected'),
        (r'was\s+not\s+adopted', 'not_adopted'),
        (r'is\s+adopted', 'adopted'),
        (r'adopted\s+without\s+a\s+vote', 'adopted'),
    ]
    for pattern, status in adoption_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            metadata['adoption_status'] = status
            break
    
    # Extract vote lists (In favour, Against, Abstaining)
    vote_lists = _extract_vote_lists(text)
    if vote_lists:
        metadata['vote_details'] = vote_lists
        # Set vote type based on presence of lists
        if vote_lists.get('in_favour') or vote_lists.get('against') or vote_lists.get('abstaining'):
            metadata['vote_type'] = 'recorded_vote'
    
    # Pattern for vote information
    # "without a vote"
    if re.search(r'without\s+a\s+vote', text, re.IGNORECASE):
        if 'vote_type' not in metadata:
            metadata['vote_type'] = 'without_vote'
        metadata['vote_info'] = 'without a vote'
    # "by a vote of X to Y" or "by X votes to Y"
    elif re.search(r'by\s+(?:a\s+)?vote\s+of\s+(\d+)\s+to\s+(\d+)', text, re.IGNORECASE):
        vote_match = re.search(r'by\s+(?:a\s+)?vote\s+of\s+(\d+)\s+to\s+(\d+)', text, re.IGNORECASE)
        if vote_match:
            if 'vote_type' not in metadata:
                metadata['vote_type'] = 'recorded_vote'
            metadata['vote_in_favor'] = int(vote_match.group(1))
            metadata['vote_against'] = int(vote_match.group(2))
            # Check for abstentions
            abstention_match = re.search(r'(\d+)\s+abstention', text, re.IGNORECASE)
            if abstention_match:
                metadata['vote_abstentions'] = int(abstention_match.group(1))
            metadata['vote_info'] = f"{vote_match.group(1)} to {vote_match.group(2)}"
    # "by a recorded vote of X to Y, with Z abstentions"
    elif re.search(r'by\s+a\s+recorded\s+vote', text, re.IGNORECASE):
        recorded_match = re.search(
            r'by\s+a\s+recorded\s+vote\s+of\s+(\d+)\s+to\s+(\d+)(?:,\s+with\s+(\d+)\s+abstention)?',
            text,
            re.IGNORECASE
        )
        if recorded_match:
            if 'vote_type' not in metadata:
                metadata['vote_type'] = 'recorded_vote'
            metadata['vote_in_favor'] = int(recorded_match.group(1))
            metadata['vote_against'] = int(recorded_match.group(2))
            if recorded_match.group(3):
                metadata['vote_abstentions'] = int(recorded_match.group(3))
            vote_str = f"{recorded_match.group(1)} to {recorded_match.group(2)}"
            if recorded_match.group(3):
                vote_str += f", with {recorded_match.group(3)} abstentions"
            metadata['vote_info'] = vote_str
    
    return metadata


def detect_draft_resolution_mentions(text: str) -> List[str]:
    """Detect all draft resolution identifiers mentioned in text.
    
    Returns a list of identifiers (e.g., ['I', 'III', 'IV']) found in the text.
    """
    identifiers = []
    # Pattern to find all draft resolution mentions
    pattern = re.compile(
        r'(?:Draft|draft)\s+resolution\s+(I{1,3}|IV|V|VI{0,3}|[1-9]\d*)',
        re.IGNORECASE
    )
    for match in pattern.finditer(text):
        identifier = match.group(1).upper()
        if identifier not in identifiers:
            identifiers.append(identifier)
    return identifiers


def finalize_utterance(utterance: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not utterance:
        return None
    text = collapse(' '.join(utterance.get('text_lines', [])))
    utterance['text'] = text
    utterance.pop('text_lines', None)
    utterance['word_count'] = len(text.split()) if text else 0
    utterance['documents'] = [doc['symbol'] for doc in detect_documents(text)]
    
    # Extract resolution metadata
    resolution_metadata = extract_resolution_metadata(text)
    if resolution_metadata:
        utterance['resolution_metadata'] = resolution_metadata
    
    # Also detect all draft resolution mentions for context
    # This helps associate utterances with resolutions even if they don't have full metadata
    draft_mentions = detect_draft_resolution_mentions(text)
    if draft_mentions:
        utterance['draft_resolution_mentions'] = draft_mentions
    
    return utterance


def identify_section_title(preamble: List[str]) -> Optional[str]:
    for line in preamble:
        lowered = line.lower()
        if lowered.startswith('the meeting was called to order'):
            continue
        if lowered.startswith('statement by'):
            continue
        if lowered.startswith('letter dated'):
            continue
        if lowered.startswith('in the absence of'):
            continue
        return line
    return preamble[0] if preamble else None


def parse_sections(text: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    lines = [collapse(line) for line in text.splitlines()]
    sections: List[Dict[str, Any]] = []
    preface_lines: List[str] = []
    current_section: Optional[Dict[str, Any]] = None
    current_utterance: Optional[Dict[str, Any]] = None

    def close_current_section() -> None:
        nonlocal current_section, current_utterance
        if current_section:
            finalized = finalize_utterance(current_utterance)
            if finalized:
                current_section['utterances'].append(finalized)
            current_utterance = None
            current_section['section_title'] = identify_section_title(current_section['preamble'])
            current_section['section_summary'] = ' '.join(current_section['preamble'])
            current_section.pop('preamble', None)
            sections.append(current_section)
        current_section = None
        current_utterance = None

    for line in lines:
        if not line:
            continue

        agenda_match = AGENDA_PATTERN.match(line)
        if agenda_match:
            close_current_section()
            current_section = {
                'agenda_item_number': agenda_match.group('number'),
                'agenda_item_note': (agenda_match.group('rest') or '').strip() or None,
                'raw_agenda_line': collapse(line),
                'preamble': [],
                'documents': [],
                'utterances': [],
            }
            continue

        if current_section is None:
            preface_lines.append(line)
            continue

        merge_documents(current_section['documents'], detect_documents(line))

        speaker_match = SPEAKER_PATTERN.search(line)
        if speaker_match:
            header = collapse(speaker_match.group('header'))
            body = collapse(speaker_match.group('body'))
            finalized = finalize_utterance(current_utterance)
            if finalized:
                current_section['utterances'].append(finalized)
            current_utterance = {
                'speaker': parse_speaker_header(header),
                'text_lines': [body] if body else [],
            }
            continue

        if current_utterance:
            current_utterance.setdefault('text_lines', []).append(line)
        else:
            current_section['preamble'].append(line)

    close_current_section()
    preface = ' '.join(preface_lines).strip() or None
    return sections, preface


def associate_utterances_with_resolutions(sections: List[Dict[str, Any]]) -> None:
    """Post-process sections to associate utterances with resolutions based on context.
    
    When the President announces multiple draft resolutions (e.g., "five draft resolutions"),
    subsequent cross-talk utterances should be associated with those resolutions based on
    mentions of draft resolution identifiers.
    """
    for section in sections:
        utterances = section.get('utterances', [])
        if not utterances:
            continue
        
        # Track when we're in a "multiple resolutions" context
        # Look for President's announcement like "five draft resolutions"
        multiple_resolutions_context = False
        announced_resolution_count = None
        
        for i, utterance in enumerate(utterances):
            text = utterance.get('text', '')
            speaker = utterance.get('speaker', {})
            speaker_raw = speaker.get('raw', '').lower()
            
            # Check if President announces multiple resolutions
            if 'president' in speaker_raw:
                # Look for patterns like "five draft resolutions" or "several draft resolutions"
                multi_res_pattern = re.search(
                    r'(\d+|several|multiple|a number of)\s+draft\s+resolutions?',
                    text,
                    re.IGNORECASE
                )
                if multi_res_pattern:
                    multiple_resolutions_context = True
                    # Extract the number if it's a digit
                    count_str = multi_res_pattern.group(1)
                    if count_str.isdigit():
                        announced_resolution_count = int(count_str)
                    # This context continues until voting starts
                    continue
            
            # Check if we're starting voting (President says "We will now take a decision")
            if 'president' in speaker_raw and re.search(
                r'we will now take a decision|we turn (first|now) to|draft resolution [IVX]+ is entitled',
                text,
                re.IGNORECASE
            ):
                multiple_resolutions_context = False
                announced_resolution_count = None
            
            # If we're in a multiple resolutions context, try to associate utterances
            # with resolutions based on mentions
            if multiple_resolutions_context:
                draft_mentions = utterance.get('draft_resolution_mentions', [])
                if draft_mentions:
                    # If utterance mentions specific draft resolutions, ensure they're in metadata
                    if 'resolution_metadata' not in utterance:
                        # Create basic metadata from mentions
                        # Use the first mention as primary, but note all mentions
                        utterance['resolution_metadata'] = {
                            'draft_resolution_identifier': draft_mentions[0],
                            'mentioned_resolutions': draft_mentions
                        }
                    elif 'draft_resolution_identifier' in utterance['resolution_metadata']:
                        # If we already have metadata, add all mentions
                        if 'mentioned_resolutions' not in utterance['resolution_metadata']:
                            utterance['resolution_metadata']['mentioned_resolutions'] = []
                        for mention in draft_mentions:
                            if mention not in utterance['resolution_metadata']['mentioned_resolutions']:
                                utterance['resolution_metadata']['mentioned_resolutions'].append(mention)


def compute_stats(sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    utterances = sum(len(section['utterances']) for section in sections)
    speakers = set()
    documents = set()
    for section in sections:
        for doc in section['documents']:
            documents.add(doc['symbol'])
        for utt in section['utterances']:
            raw = utt['speaker'].get('raw')
            if raw:
                speakers.add(raw)
    return {
        'section_count': len(sections),
        'utterance_count': utterances,
        'unique_speakers': len(speakers),
        'document_references': len(documents),
    }


def parse_meeting_file(file_path: str) -> Dict[str, Any]:
    """Parse a plenary meeting PDF/txt file into structured data."""
    path = Path(file_path)
    text = load_text(path)
    metadata = extract_metadata(text)
    sections, preface = parse_sections(text)
    
    # Post-process to associate utterances with resolutions
    associate_utterances_with_resolutions(sections)

    # Add unique IDs
    doc_symbol = metadata.get('symbol')
    if doc_symbol:
        metadata['id'] = doc_symbol
        for i, section in enumerate(sections):
            agenda_num = section.get('agenda_item_number', f"s{i+1}")
            section['id'] = f"{doc_symbol}_section_{agenda_num}"
            for j, utterance in enumerate(section.get('utterances', [])):
                utterance['id'] = f"{section['id']}_utterance_{j+1}"

    return {
        'id': doc_symbol,
        'source_file': str(path),
        'preface': preface,
        'metadata': metadata,
        'sections': sections,
        'stats': compute_stats(sections),
    }


def parse_meeting_files(input_dir: Path, output_dir: Path, max_files: Optional[int] = None):
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
            data = parse_meeting_file(str(pdf_file))
            
            output_filename = pdf_file.stem + '.json'
            output_path = output_dir / output_filename
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"  ✓ Saved: {output_filename}")
            metadata = data.get('metadata', {})
            stats = data.get('stats', {})
            print(f"    Symbol: {metadata.get('symbol', 'N/A')}")
            print(f"    Sections: {stats.get('section_count', 'N/A')}")
            print(f"    Utterances: {stats.get('utterance_count', 'N/A')}")

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Parse UN General Assembly plenary meeting (PV) records',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Extracts:
- Document-level metadata (symbol, session, meeting number, date/time, presiding officer)
- Each agenda item section with referenced documents
- Ordered utterances (speaker metadata + text + referenced documents)

Examples:
  # Parse all PDF files in a directory
  python3 parse_meeting_pdf.py data/documents/pdfs/meetings

  # Parse a single file
  python3 parse_meeting_pdf.py data/documents/pdfs/meetings/A_78_PV.51.pdf
        """
    )
    parser.add_argument('input_path', type=Path, help='Path to meeting PDF file or directory')
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

        result = parse_meeting_file(str(input_path))

        output_path_obj = Path(output_file)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path_obj, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"✓ Parsed meeting saved to {output_path_obj}")
        print(f"Sections: {result['stats']['section_count']}, "
              f"Utterances: {result['stats']['utterance_count']}, "
              f"Speakers: {result['stats']['unique_speakers']}")
    
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
        
        parse_meeting_files(input_dir, output_dir, args.max_files)


if __name__ == "__main__":
    main()

