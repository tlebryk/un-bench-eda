#!/usr/bin/env python3
"""
Text segmentation utilities for UN draft/resolution documents.

Handles segmentation of:
- Preamble paragraphs (gerund clauses: Guided, Recalling, etc.)
- Operative paragraphs (numbered items: 1., 2., 3., etc.)
"""

import re
from typing import Dict, List


# Common preamble starters (gerunds and phrases)
PREAMBLE_STARTERS = [
    'The General Assembly',
    'Guided',
    'Recalling',
    'Welcoming',
    'Recognizing',
    'Noting',
    'Reaffirming',
    'Bearing in mind',
    'Mindful',
    'Acknowledging',
    'Emphasizing',
    'Convinced',
    'Concerned',
    'Aware',
    'Deeply concerned',
    'Gravely concerned',
    'Alarmed',
    'Appreciating',
    'Deploring',
    'Desirous',
    'Determined',
    'Expressing',
    'Having considered',
    'Having examined',
    'Observing',
    'Reiterating',
    'Stressing',
    'Taking into account',
    'Taking note',
    'Underlining',
    'Affirming',
    'Believing',
    'Considering',
    'Desiring',
]


def segment_resolution_text(text: str) -> Dict:
    """
    Segment resolution text into preamble and operative paragraphs.

    The preamble contains gerund clauses and introductory language.
    The operative section contains numbered paragraphs (1., 2., 3., ...).

    Args:
        text: Full resolution text (after metadata header removed)

    Returns:
        {
            'preamble': 'Full preamble text...',
            'operative': 'Full operative text...',
            'preamble_paragraphs': ['Guided by...', 'Recalling...'],
            'operative_paragraphs': ['1. Takes note...', '2. Welcomes...']
        }
    """
    # Find start of operative section (first numbered paragraph)
    # Pattern: Line starting with "1." followed by space and uppercase word
    operative_match = re.search(r'\n\s*1\.\s+[A-Z]', text)

    if not operative_match:
        # No operative section found - entire text is preamble
        return {
            'preamble': text.strip(),
            'operative': '',
            'preamble_paragraphs': _split_preamble_paragraphs(text),
            'operative_paragraphs': []
        }

    # Split at the operative boundary
    preamble = text[:operative_match.start()].strip()
    operative = text[operative_match.start():].strip()

    return {
        'preamble': preamble,
        'operative': operative,
        'preamble_paragraphs': _split_preamble_paragraphs(preamble),
        'operative_paragraphs': _split_operative_paragraphs(operative)
    }


def _split_preamble_paragraphs(text: str) -> List[str]:
    """
    Split preamble into individual paragraphs.

    Preamble paragraphs typically start with gerunds or specific phrases.

    Args:
        text: Preamble text

    Returns:
        List of preamble paragraph strings
    """
    if not text.strip():
        return []

    paragraphs = []
    current_para = []

    lines = text.split('\n')

    for line in lines:
        line_stripped = line.strip()

        if not line_stripped:
            continue

        # Check if line starts a new paragraph
        starts_new = False
        for starter in PREAMBLE_STARTERS:
            if line_stripped.startswith(starter):
                starts_new = True
                break

        if starts_new and current_para:
            # Save previous paragraph
            para_text = ' '.join(current_para)
            paragraphs.append(para_text)
            current_para = [line_stripped]
        else:
            current_para.append(line_stripped)

    # Add final paragraph
    if current_para:
        para_text = ' '.join(current_para)
        paragraphs.append(para_text)

    return paragraphs


def _split_operative_paragraphs(text: str) -> List[str]:
    """
    Split operative section into numbered paragraphs.

    Operative paragraphs are numbered: "1.", "2.", "3.", etc.

    Args:
        text: Operative section text

    Returns:
        List of operative paragraph strings (with numbers preserved)
    """
    if not text.strip():
        return []

    paragraphs = []

    # Handle case where text starts with a number (no leading newline before "1.")
    # Add a newline at the start if text begins with a digit
    if text.strip() and text.strip()[0].isdigit():
        text = '\n' + text

    # Split on numbered paragraph markers
    # Pattern: newline followed by number and period at start of line
    parts = re.split(r'\n\s*(\d+)\.\s+', text)

    # parts will be: ['<possible prefix>', '1', 'Takes note...', '2', 'Welcomes...', ...]
    # Skip the first part (before first number) and process pairs
    i = 1
    while i < len(parts):
        if i + 1 < len(parts):
            num = parts[i]
            content = parts[i + 1].strip()

            # Reconstruct paragraph with number
            paragraph = f"{num}. {content}"
            paragraphs.append(paragraph)

            i += 2
        else:
            i += 1

    return paragraphs


def extract_sub_paragraphs(operative_paragraph: str) -> List[str]:
    """
    Extract sub-paragraphs from an operative paragraph.

    Many operative paragraphs have lettered sub-items: (a), (b), (c), etc.

    Args:
        operative_paragraph: Single operative paragraph text

    Returns:
        List of sub-paragraph strings
    """
    # Pattern: "(a)", "(b)", "(c)", etc. at start of line or after newline
    parts = re.split(r'\n\s*\(([a-z])\)\s+', operative_paragraph)

    if len(parts) <= 1:
        # No sub-paragraphs found
        return []

    sub_paragraphs = []

    # First part is the main paragraph text (before first sub-item)
    i = 1
    while i < len(parts):
        if i + 1 < len(parts):
            letter = parts[i]
            content = parts[i + 1].strip()
            sub_paragraphs.append(f"({letter}) {content}")
            i += 2
        else:
            i += 1

    return sub_paragraphs
