#!/usr/bin/env python3
"""
Metadata extraction utilities for UN draft/resolution documents.

Handles extraction of:
- Sponsors/endorsers (from HTML metadata with PDF fallback)
- Document type (draft resolution, draft decision, amendment, etc.)
- Committee information
- Enhanced title extraction
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional


# Multi-word country patterns for parsing
MULTI_WORD_COUNTRIES = [
    'United Kingdom of Great Britain and Northern Ireland',
    'United States of America',
    'Micronesia (Federated States of)',
    'Netherlands (Kingdom of the)',
    'Bosnia and Herzegovina',
    'Saint Vincent and the Grenadines',
    'Sao Tome and Principe',
    'Trinidad and Tobago',
    'Republic of Moldova',
    'Dominican Republic',
    'Democratic Republic of the Congo',
    'Central African Republic',
    'Czech Republic',
    'Republic of Korea',
    'Democratic People\'s Republic of Korea',
    'Lao People\'s Democratic Republic',
    'United Republic of Tanzania',
    'United Arab Emirates',
    'New Zealand',
    'Papua New Guinea',
    'Sierra Leone',
    'Sri Lanka',
    'Costa Rica',
    'Puerto Rico',
    'Saudi Arabia',
    'South Africa',
    'El Salvador',
    'Equatorial Guinea',
    'Antigua and Barbuda',
    'Burkina Faso',
    'Cape Verde',
    'North Macedonia',
    'San Marino',
]

# Committee number to name mapping
COMMITTEE_NAMES = {
    1: 'First Committee',
    2: 'Second Committee',
    3: 'Third Committee',
    4: 'Fourth Committee',
    5: 'Fifth Committee',
    6: 'Sixth Committee',
}


def get_html_metadata_path(pdf_path: Path) -> Optional[Path]:
    """
    Determine corresponding HTML metadata JSON path for a PDF.

    Path mapping:
    PDF:  data/documents/pdfs/drafts/A_C.3_78_L.41.pdf
    HTML: data/parsed/html/drafts/A_C.3_78_L.41_record_*.json

    Args:
        pdf_path: Path to draft/resolution PDF file

    Returns:
        Path to parsed HTML JSON file, or None if not found
    """
    # Navigate to base data directory
    # PDF path: data/documents/pdfs/drafts/filename.pdf
    # HTML path: data/parsed/html/drafts/filename_record_*.json

    parts = pdf_path.parts
    if 'data' not in parts:
        return None

    data_idx = parts.index('data')
    base_dir = Path(*parts[:data_idx+1])

    # Determine document type (drafts, resolutions, etc.)
    if 'drafts' in parts:
        doc_type = 'drafts'
    elif 'resolutions' in parts:
        doc_type = 'resolutions'
    else:
        doc_type = 'drafts'  # default

    html_dir = base_dir / 'parsed' / 'html' / doc_type

    if not html_dir.exists():
        return None

    # Match by symbol prefix (handle multiple record IDs)
    symbol = pdf_path.stem  # e.g., "A_C.3_78_L.41"
    matches = list(html_dir.glob(f'{symbol}_record_*.json'))

    return matches[0] if matches else None


def extract_sponsors(pdf_path: Path, pdf_text: str, html_metadata_path: Optional[Path] = None) -> Dict:
    """
    Extract document sponsors/endorsers from both HTML and PDF sources.

    Returns both sources separately so consumers can choose which to use.

    Args:
        pdf_path: Path to PDF file
        pdf_text: Extracted text from PDF
        html_metadata_path: Optional path to HTML metadata JSON

    Returns:
        {
            'html': {
                'primary': ['Albania', 'Australia', ...],
                'additional': ['Andorra', 'New Zealand', ...]
            } or None,
            'pdf': {
                'primary': ['Egypt', 'Jordan', ...]
            } or None
        }
    """
    sponsors_data = {
        'html': None,
        'pdf': None
    }

    # Try HTML extraction (if path not provided, try to find it)
    if html_metadata_path is None:
        html_metadata_path = get_html_metadata_path(pdf_path)

    if html_metadata_path and html_metadata_path.exists():
        try:
            with open(html_metadata_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            # Extract from authors field (space-separated list)
            authors_list = json_data.get('metadata', {}).get('authors', [])
            if authors_list and authors_list[0]:
                html_sponsors = {
                    'primary': _parse_country_list_spaced(authors_list[0]),
                    'additional': []
                }

                # Check notes for additional sponsors
                notes = json_data.get('metadata', {}).get('notes', '')
                if notes and 'additional sponsor' in notes.lower():
                    html_sponsors['additional'] = _extract_additional_sponsors(notes)

                sponsors_data['html'] = html_sponsors
        except (json.JSONDecodeError, KeyError):
            pass

    # Always try PDF extraction as well
    pdf_sponsors = _extract_sponsors_from_pdf(pdf_text)
    if pdf_sponsors:
        sponsors_data['pdf'] = {
            'primary': pdf_sponsors,
            'additional': []  # PDF can't extract additional sponsors
        }

    return sponsors_data


def _parse_country_list_spaced(text: str) -> List[str]:
    """Parse space-separated country names (handles multi-word names).

    Example:
        "Albania Australia Austria ... United Kingdom United States"
        -> ["Albania", "Australia", "Austria", ..., "United Kingdom...", "United States..."]

    Args:
        text: Space-separated country list

    Returns:
        List of country names
    """
    countries = []
    remaining = text.strip()

    # First, greedily match known multi-word countries (longest first)
    for pattern in sorted(MULTI_WORD_COUNTRIES, key=len, reverse=True):
        # Use word boundaries to avoid partial matches
        pattern_regex = r'\b' + re.escape(pattern) + r'\b'
        if re.search(pattern_regex, remaining):
            countries.append(pattern)
            # Remove matched pattern
            remaining = re.sub(pattern_regex, ' ', remaining, count=1)

    # Then split remaining text on spaces for single-word countries
    words = remaining.split()
    for word in words:
        word = word.strip()
        if word and len(word) > 1 and word.isalpha():  # Skip empty, single letters, and non-alphabetic
            countries.append(word)

    # Return in original order (no sorting to preserve document order)
    return countries


def _parse_country_list_comma(text: str) -> List[str]:
    """Parse comma-separated country names.

    Example:
        "Albania, Australia, Austria, ..., United Kingdom and United States"

    Args:
        text: Comma-separated country list

    Returns:
        List of country names
    """
    # Replace "and" with comma for consistent parsing
    text = re.sub(r'\s+and\s+', ', ', text)

    # Split on commas
    countries = []
    for country in text.split(','):
        country = country.strip()
        if country:
            countries.append(country)

    return countries


def _extract_additional_sponsors(notes: str) -> List[str]:
    """Extract additional sponsors from notes field.

    Example:
        "Additional sponsors: Andorra, New Zealand, Palau, Republic of Moldova (A/78/481/Add.3)."

    Args:
        notes: Notes text containing additional sponsors

    Returns:
        List of additional sponsor countries
    """
    # Pattern: "Additional sponsors: <countries> (A/...)"
    pattern = r'[Aa]dditional sponsors?:\s*([^(]+?)(?:\(|$)'
    match = re.search(pattern, notes)

    if match:
        sponsors_text = match.group(1).strip()
        return _parse_country_list_comma(sponsors_text)

    return []


def _extract_sponsors_from_pdf(text: str) -> List[str]:
    """
    Extract sponsors from PDF text.

    Pattern: Country list appears on first page, formatted as:
    "Country1, Country2, ... and CountryN: draft resolution"

    Args:
        text: Full PDF text

    Returns:
        List of sponsor countries
    """
    # Look in first ~2500 characters for sponsor list
    header = text[:2500]

    # Find ": draft resolution" or ": draft decision"
    marker_match = re.search(r':\s*draft\s+(?:resolution|decision)', header, re.IGNORECASE)
    if not marker_match:
        return []

    # Extract text before the marker (up to 400 chars before)
    end_pos = marker_match.start()
    start_pos = max(0, end_pos - 400)
    candidate_text = header[start_pos:end_pos]

    # Find the last occurrence of "and [Country]" before the marker
    # This marks the end of the sponsor list
    and_pattern = r'and\s+([A-Z][a-zA-Z\s\-()]+?)$'
    and_match = re.search(and_pattern, candidate_text.strip())
    if not and_match:
        return []

    # Now find where the sponsor list starts
    # Look for the start after a newline followed by a capital letter
    # The sponsor list typically starts on its own line
    lines = candidate_text.split('\n')

    # Work backwards from the end to find the first line that starts with a country
    sponsor_lines = []
    for line in reversed(lines):
        line_stripped = line.strip()
        if not line_stripped:
            break  # Empty line marks end of backwards search
        # Check if line looks like it contains countries (has comma or starts with capital)
        if line_stripped and (line_stripped[0].isupper() or ',' in line_stripped):
            sponsor_lines.insert(0, line_stripped)
        else:
            break  # Hit a non-sponsor line

    if not sponsor_lines:
        return []

    sponsor_text = ' '.join(sponsor_lines)

    # Validate: should contain commas and "and"
    if ',' not in sponsor_text or 'and' not in sponsor_text.lower():
        return []

    # Extract the part before the final "and"
    parts = re.split(r'\s+and\s+', sponsor_text, flags=re.IGNORECASE)
    if len(parts) >= 2:
        # Combine all parts
        all_sponsors = ', '.join(parts)
        return _parse_country_list_comma(all_sponsors)

    return []


def extract_document_type(text: str) -> Optional[str]:
    """
    Extract document type from text.

    Types:
    - draft_resolution
    - draft_decision
    - amendment
    - revised_draft_resolution
    - resolution
    - decision

    Args:
        text: Full PDF text

    Returns:
        Document type string, or None if not detected
    """
    # Search first 2000 characters
    header = text[:2000]

    # Patterns in priority order (more specific first)
    patterns = [
        (r'Amendment to draft resolution', 'amendment'),
        (r'Revised draft resolution', 'revised_draft_resolution'),
        (r'Draft decision', 'draft_decision'),
        (r'Draft resolution', 'draft_resolution'),
        (r'Resolution adopted by the General Assembly', 'resolution'),
        (r'Decision adopted by the General Assembly', 'decision'),
    ]

    for pattern, doc_type in patterns:
        if re.search(pattern, header, re.IGNORECASE):
            return doc_type

    return None


def extract_committee(text: str, symbol: Optional[str] = None) -> Optional[str]:
    """
    Extract committee name from document.

    Strategies:
    1. Pattern match in text: "Third Committee"
    2. Parse from symbol: "A/C.3/78/L.41" -> Third Committee

    Args:
        text: Full PDF text
        symbol: Document symbol (e.g., "A/C.3/78/L.41")

    Returns:
        Committee name (e.g., "Third Committee"), or None
    """
    # Strategy 1: Direct pattern match in text
    header = text[:1500]

    committee_pattern = r'(First|Second|Third|Fourth|Fifth|Sixth|Special Political and Decolonization)\s+Committee'
    match = re.search(committee_pattern, header, re.IGNORECASE)
    if match:
        return match.group(0).title()

    # Strategy 2: Extract from symbol
    if symbol:
        # Pattern: "A/C.<number>/session/..."
        symbol_match = re.search(r'A/C\.(\d+)/', symbol)
        if symbol_match:
            committee_num = int(symbol_match.group(1))
            return COMMITTEE_NAMES.get(committee_num)

    return None


def extract_title_enhanced(text: str, html_metadata: Optional[Dict] = None) -> Optional[str]:
    """
    Extract document title with multiple fallback strategies.

    Priority:
    1. HTML metadata (most reliable)
    2. PDF pattern for adopted resolutions
    3. PDF pattern for draft resolutions
    4. PDF pattern as fallback

    Args:
        text: Full PDF text
        html_metadata: Optional parsed HTML metadata dictionary

    Returns:
        Document title, or None
    """
    # Strategy 1: HTML metadata
    if html_metadata:
        title = html_metadata.get('metadata', {}).get('title', '')
        if title:
            # Clean up: Remove sponsor list from title
            if ':' in title:
                title = title.split(':')[0].strip()
            return title if title else None

    # Strategy 2: For adopted resolutions (A/RES/...)
    doc_type = extract_document_type(text)
    if doc_type == 'resolution':
        # Pattern: Title is between "Agenda item..." and "Resolution adopted by..."
        pattern = r'Agenda item[\s\S]*?\n\s*([^\n]+(?:\n[^\n]+)*?)\s*\n\s*Resolution adopted by'
        match = re.search(pattern, text[:2500], re.IGNORECASE | re.DOTALL)
        if match:
            title = ' '.join(match.group(1).split())
            if title:
                return title

        # Fallback for resolutions: look for "<number>.<Title>" pattern
        # e.g., "78/8. Report of the International Atomic Energy Agency"
        res_num_pattern = r'\d+/\d+\.\s+([^\n]+)'
        match = re.search(res_num_pattern, text[:2500])
        if match:
            title = match.group(1).strip()
            if title:
                return title

    # Strategy 3: PDF extraction for drafts
    pattern = r'(?:draft resolution|draft decision)[\s\S]*?\n\s*([^\n]+(?:\n[^\n]+)*?)\s*\n\s*The General Assembly'
    match = re.search(pattern, text[:3000], re.IGNORECASE | re.DOTALL)
    if match:
        title = ' '.join(match.group(1).split())
        return title

    # Strategy 4: Look after agenda item (general fallback)
    pattern = r'Agenda item \d+.*?\n\s*([^\n]+)\s*\n\s*(?:Draft|The General Assembly)'
    match = re.search(pattern, text[:2000], re.IGNORECASE | re.DOTALL)
    if match:
        title = match.group(1).strip()
        # Filter out common non-title patterns
        if not re.match(r'^(Draft|The|Agenda)', title):
            return title

    return None
