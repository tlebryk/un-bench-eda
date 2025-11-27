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


def load_text(file_path: Path) -> str:
    """Extract text from PDF or fallback text file."""
    if file_path.suffix.lower() == '.pdf':
        with pdfplumber.open(str(file_path)) as pdf:
            pages = [page.extract_text() or '' for page in pdf.pages]
        return '\n'.join(pages)
    return file_path.read_text(encoding='utf-8')


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


def finalize_utterance(utterance: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not utterance:
        return None
    text = collapse(' '.join(utterance.get('text_lines', [])))
    utterance['text'] = text
    utterance.pop('text_lines', None)
    utterance['word_count'] = len(text.split()) if text else 0
    utterance['documents'] = [doc['symbol'] for doc in detect_documents(text)]
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

    return {
        'source_file': str(path),
        'preface': preface,
        'metadata': metadata,
        'sections': sections,
        'stats': compute_stats(sections),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Parse UN General Assembly plenary meeting (PV) records',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Extracts:
- Document-level metadata (symbol, session, meeting number, date/time, presiding officer)
- Each agenda item section with referenced documents
- Ordered utterances (speaker metadata + text + referenced documents)

Example:
  python3 parse_meeting_pdf.py data/documents/pdfs/meetings/A_78_PV.51.pdf
        """
    )
    parser.add_argument('input_file', type=Path, help='Path to meeting PDF file')
    parser.add_argument('-o', '--output', type=Path, default=None,
                        help='Output JSON file path (default: <input_file>_parsed.json)')

    args = parser.parse_args()

    input_file = args.input_file
    if args.output:
        output_file = args.output
    else:
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_parsed.json"

    result = parse_meeting_file(input_file)

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"✓ Parsed meeting saved to {output_path}")
    print(f"Sections: {result['stats']['section_count']}, "
          f"Utterances: {result['stats']['utterance_count']}, "
          f"Speakers: {result['stats']['unique_speakers']}")


if __name__ == "__main__":
    main()

