#!/usr/bin/env python3
"""
Shared utilities for parsing UN PDF documents.

Provides:
- Text cleaning (collapse whitespace, normalize)
- Header/footer removal
- Common pattern matching
"""

import re
from typing import List


def collapse(text: str) -> str:
    """Collapse internal whitespace to single spaces.

    Args:
        text: Text with potentially multiple spaces, tabs, etc.

    Returns:
        Text with all whitespace collapsed to single spaces

    Example:
        >>> collapse("Hello    world\\n\\tthere")
        'Hello world there'
    """
    return re.sub(r'\s+', ' ', text.strip())


def normalize_for_regex(text: str) -> str:
    """Normalize text for regex matching (remove newlines, collapse spaces).

    Args:
        text: Raw text with newlines and varying whitespace

    Returns:
        Normalized text suitable for regex pattern matching

    Example:
        >>> normalize_for_regex("Hello\\nworld  there")
        'Hello world there'
    """
    return collapse(text.replace('\n', ' '))


def remove_footers_headers(text: str, page_num: int = 1) -> str:
    """Remove UN document headers and footers from extracted text.

    UN documents have standard header/footer patterns:
    - Page 1: Job number with date (e.g., "23-21227 (E) 131123")
    - Page 1: Barcode format (e.g., "*2321227*")
    - Page 2+: Document symbol at top (e.g., "A/C.3/78/L.41")
    - All pages: Page/total with job number (e.g., "2/9 23-21227")
    - Footnote separators: "__________________"

    Args:
        text: Raw text from PDF page
        page_num: Page number (1-indexed)

    Returns:
        Cleaned text with headers/footers removed

    Example:
        >>> text = "Some content\\n23-21227 (E) 131123\\n*2321227*\\nMore content"
        >>> remove_footers_headers(text, 1)
        'Some content\\nMore content'
    """
    lines = text.split('\n')
    cleaned_lines = []

    for line in lines:
        # Skip if line matches footer patterns
        if _is_footer_line(line, page_num):
            continue

        # Skip if line matches header patterns (page 2+)
        if page_num > 1 and _is_header_line(line):
            continue

        cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)


def _is_footer_line(line: str, page_num: int) -> bool:
    """Check if line matches UN document footer patterns.

    Detects:
    - Job numbers: "23-21227 (E) 131123"
    - Barcode format: "*2321227*"
    - Page numbers: "2/9 23-21227" or "23-18952 3/4"
    - Footnote separators: "__________________"

    Args:
        line: Single line of text
        page_num: Page number (1-indexed)

    Returns:
        True if line is a footer artifact
    """
    line = line.strip()

    # Empty lines are not footers
    if not line:
        return False

    # Pattern 1: Job number with language code and date (e.g., "23-21227 (E) 131123")
    if re.match(r'^\d{2}-\d{5}\s*\([A-Z]\)\s*\d{6}$', line):
        return True

    # Pattern 2: Barcode format (e.g., "*2321227*")
    if re.match(r'^\*\d{7}\*$', line):
        return True

    # Pattern 3: Page number with job number (e.g., "2/9 23-21227")
    if re.match(r'^\d+/\d+\s+\d{2}-\d{5}$', line):
        return True

    # Pattern 4: Job number with page number (e.g., "23-18952 3/4")
    if re.match(r'^\d{2}-\d{5}\s+\d+/\d+$', line):
        return True

    # Pattern 5: Footnote separator (underscores only)
    if re.match(r'^_{10,}$', line):
        return True

    # Pattern 6: "Please recycle" with symbols (often on first page)
    if 'please recycle' in line.lower():
        return True

    return False


def _is_header_line(line: str) -> bool:
    """Check if line matches UN document header patterns (page 2+).

    Headers on pages 2+ typically contain the document symbol.

    Args:
        line: Single line of text

    Returns:
        True if line is a header artifact
    """
    line = line.strip()

    # Empty lines are not headers
    if not line:
        return False

    # Document symbol at top of page (e.g., "A/C.3/78/L.41" or "A/RES/78/175")
    # Pattern matches: A/[optional committee]/session/document_id
    if re.match(r'^A/(?:C\.\d+/)?(?:RES/)?\d+/[A-Z0-9.]+$', line):
        return True

    return False
