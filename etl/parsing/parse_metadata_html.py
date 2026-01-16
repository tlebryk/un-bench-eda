#!/usr/bin/env python3
"""
Parse UN Digital Library HTML metadata pages

Extracts rich metadata from digitallibrary.un.org HTML pages for all document types including:
- Basic metadata (symbol, title, date, action note)
- Voting information
- Related documents (drafts, committee reports, meeting records)
- Agenda information
- Subjects/topics
- Available file formats and languages

Supports all document types: resolutions, drafts, committee-reports, agenda, meetings, voting

Reads from: data/documents/html/{type}/*.html
Saves to: data/parsed/html/{type}/*.json
"""

import json
import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from bs4 import BeautifulSoup


def extract_metadata_row_value(soup: BeautifulSoup, title_text: str) -> Optional[str]:
    """
    Extract value from a metadata row by title.
    
    Args:
        soup: BeautifulSoup object
        title_text: The title text to search for (e.g., "Symbol", "Vote summary")
    
    Returns:
        The value text, or None if not found
    """
    # Find all metadata rows
    metadata_rows = soup.find_all('div', class_='metadata-row')
    
    for row in metadata_rows:
        title_div = row.find('div', class_='title')
        if title_div and title_div.get_text(strip=True) == title_text:
            value_div = row.find('div', class_='value')
            if value_div:
                # Get text, but preserve links
                return value_div.get_text(separator=' ', strip=True)
    
    return None


def extract_metadata_row_links(soup: BeautifulSoup, title_text: str) -> List[Dict[str, str]]:
    """
    Extract links from a metadata row by title.
    
    Args:
        soup: BeautifulSoup object
        title_text: The title text to search for (e.g., "Draft", "Meeting record")
    
    Returns:
        List of dicts with 'text' and 'url' keys
    """
    metadata_rows = soup.find_all('div', class_='metadata-row')
    
    for row in metadata_rows:
        title_div = row.find('div', class_='title')
        if title_div and title_div.get_text(strip=True) == title_text:
            value_div = row.find('div', class_='value')
            if value_div:
                links = []
                for link in value_div.find_all('a', href=True):
                    text = link.get_text(strip=True)
                    url = link.get('href', '')
                    # Make absolute URL if relative
                    if url.startswith('/'):
                        url = f"https://digitallibrary.un.org{url}"
                    elif not url.startswith('http'):
                        url = f"https://digitallibrary.un.org/{url}"
                    links.append({'text': text, 'url': url})
                return links
    
    return []


def extract_citation_pdf_urls(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    Extract PDF URLs from citation_pdf_url meta tags.
    
    These meta tags contain direct PDF URLs that are more reliable than
    the Access metadata row links.
    
    Args:
        soup: BeautifulSoup object
    
    Returns:
        List of dicts with language, filename, and url
    """
    files = []
    lang_code_map = {
        'EN': 'English',
        'FR': 'French', 
        'ES': 'Spanish',
        'AR': 'Arabic',
        'RU': 'Russian',
        'ZH': 'Chinese'
    }
    
    for meta in soup.find_all('meta', attrs={'name': 'citation_pdf_url'}):
        url = meta.get('content', '').strip()
        if url and url.endswith('.pdf'):
            # Extract language from filename: A_78_PV.109-EN.pdf -> EN
            lang_match = re.search(r'-([A-Z]{2})\.pdf$', url)
            lang_code = lang_match.group(1) if lang_match else 'EN'
            language = lang_code_map.get(lang_code, lang_code)
            
            # Extract filename from URL
            filename = url.split('/')[-1]
            
            files.append({
                'language': language,
                'filename': filename,
                'url': url
            })
    
    return files


def extract_access_files(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    Extract file access information from the Access metadata row.
    
    Args:
        soup: BeautifulSoup object
    
    Returns:
        List of dicts with language, filename, and url
    """
    access_value = extract_metadata_row_value(soup, 'Access')
    if not access_value:
        return []
    
    # Find the Access row to get links
    metadata_rows = soup.find_all('div', class_='metadata-row')
    files = []
    
    for row in metadata_rows:
        title_div = row.find('div', class_='title')
        if title_div and title_div.get_text(strip=True) == 'Access':
            value_div = row.find('div', class_='value')
            if value_div:
                # Parse format: <strong>Language:</strong> <em>filename</em> - <a href="...">PDF</a>
                current_lang = None
                for element in value_div.children:
                    if element.name == 'strong':
                        current_lang = element.get_text(strip=True).rstrip(':')
                    elif element.name == 'em':
                        filename = element.get_text(strip=True)
                    elif element.name == 'a' and current_lang:
                        url = element.get('href', '')
                        if url.startswith('/'):
                            url = f"https://digitallibrary.un.org{url}"
                        files.append({
                            'language': current_lang,
                            'filename': filename,
                            'url': url
                        })
                        current_lang = None
    
    return files


def extract_subjects(soup: BeautifulSoup) -> List[str]:
    """
    Extract subject headings from the Browse Subjects section.
    
    Args:
        soup: BeautifulSoup object
    
    Returns:
        List of subject strings
    """
    subjects = []
    
    # Find the Browse Subjects section
    subjects_section = soup.find('div', class_='related-subjects')
    if subjects_section:
        # Find all subject links
        for link in subjects_section.find_all('a', class_='rs-link'):
            subject = link.get_text(strip=True)
            if subject:
                subjects.append(subject)
    
    return subjects


def parse_vote_summary(vote_text: str) -> Dict[str, any]:
    """
    Parse vote summary text into structured data.
    
    Examples:
        "Adopted without vote, 88th plenary meeting"
        "Adopted 151-6-27, 42nd plenary meeting"
    
    Args:
        vote_text: Raw vote summary text
    
    Returns:
        Dict with vote_type, yes, no, abstain, meeting info
    """
    result = {
        'vote_type': None,
        'yes': None,
        'no': None,
        'abstain': None,
        'meeting': None,
        'raw_text': vote_text
    }
    
    if not vote_text:
        return result
    
    # Check for "without vote"
    if 'without vote' in vote_text.lower():
        result['vote_type'] = 'without_vote'
    else:
        # Try to parse vote counts: "Adopted 151-6-27"
        vote_match = re.search(r'(\d+)-(\d+)-(\d+)', vote_text)
        if vote_match:
            result['vote_type'] = 'recorded_vote'
            result['yes'] = int(vote_match.group(1))
            result['no'] = int(vote_match.group(2))
            result['abstain'] = int(vote_match.group(3))
        else:
            result['vote_type'] = 'unknown'
    
    # Extract meeting info
    meeting_match = re.search(r'(\d+)(?:st|nd|rd|th)\s+plenary\s+meeting', vote_text, re.IGNORECASE)
    if meeting_match:
        result['meeting'] = f"{meeting_match.group(1)}th plenary meeting"
    
    return result


def parse_agenda_item(agenda_text: str) -> Optional[Dict[str, any]]:
    """
    Parse a single agenda item text.
    
    Handles various formats:
    - "A/78/251 35 Question of Palestine. PALESTINE QUESTION"
    - "A/78/251 [905] UN. GENERAL ASSEMBLY--PRESIDENT-ELECT--OATH OF OFFICE"
    - "A/78/251 8[1] UN. GENERAL ASSEMBLY (78TH SESS. : 2023-2024)--GENERAL DEBATE--RIGHT OF REPLY"
    - "A/78/251 18i Combating sand and dust storms. STORMS"
    - "A/78/251 114b Election of members..."
    
    Args:
        agenda_text: Raw agenda item text
    
    Returns:
        Dict with agenda_symbol, item_number, sub_item, title, subjects, or None
    """
    if not agenda_text:
        return None
    
    # Pattern 1: Standard format: A/78/251 35 Title. SUBJECTS
    # Pattern 2: With brackets: A/78/251 [905] Title
    # Pattern 3: With sub-item: A/78/251 18i Title or A/78/251 8[1] Title
    # Pattern 4: Complex: A/78/251 114b Title
    
    # Extract agenda symbol first
    symbol_match = re.match(r'([A-Z]/\d+/\d+(?:\s+Rev\.\d+)?)\s+', agenda_text)
    if not symbol_match:
        return None
    
    agenda_symbol = symbol_match.group(1)
    remainder = agenda_text[len(symbol_match.group(0)):]
    
    # Try pattern 1: Standard number format "35 Title. SUBJECTS"
    match = re.match(r'(\d+)\s+(.+?)(?:\.\s*(.+))?$', remainder)
    if match:
        item_number = int(match.group(1))
        item_id = f"{agenda_symbol}_item_{item_number}"
        return {
            'id': item_id,
            'agenda_symbol': agenda_symbol,
            'item_number': item_number,
            'sub_item': None,
            'title': match.group(2).strip(),
            'subjects': match.group(3).strip() if match.group(3) else None
        }
    
    # Try pattern 2: Bracketed number "[905] Title"
    match = re.match(r'\[(\d+)\]\s+(.+)$', remainder)
    if match:
        item_number = int(match.group(1))
        item_id = f"{agenda_symbol}_item_{item_number}"
        return {
            'id': item_id,
            'agenda_symbol': agenda_symbol,
            'item_number': item_number,
            'sub_item': None,
            'title': match.group(2).strip(),
            'subjects': None
        }
    
    # Try pattern 3: With sub-item letter "18i Title" or "8[1] Title"
    match = re.match(r'(\d+)([a-z]|\[\d+\])\s+(.+)$', remainder)
    if match:
        item_number = int(match.group(1))
        sub_item = match.group(2)
        # Remove brackets if present
        if sub_item.startswith('[') and sub_item.endswith(']'):
            sub_item = sub_item[1:-1]
        
        item_id = f"{agenda_symbol}_item_{item_number}{sub_item}"
        return {
            'id': item_id,
            'agenda_symbol': agenda_symbol,
            'item_number': item_number,
            'sub_item': sub_item,
            'title': match.group(3).strip(),
            'subjects': None
        }
    
    # Fallback: just return what we can extract
    return {
        'id': f"{agenda_symbol}_item_unknown",
        'agenda_symbol': agenda_symbol,
        'item_number': None,
        'sub_item': None,
        'title': remainder.strip(),
        'subjects': None
    }


def extract_agenda_items(soup: BeautifulSoup) -> List[Dict[str, any]]:
    """
    Extract all agenda items from the Agenda information metadata row.
    
    Agenda items are typically presented as multiple links separated by <br> tags.
    
    Args:
        soup: BeautifulSoup object
    
    Returns:
        List of parsed agenda item dictionaries
    """
    agenda_items = []
    
    # Find the Agenda information row
    metadata_rows = soup.find_all('div', class_='metadata-row')
    
    for row in metadata_rows:
        title_div = row.find('div', class_='title')
        if title_div and title_div.get_text(strip=True) == 'Agenda information':
            value_div = row.find('div', class_='value')
            if value_div:
                # Find all links (each link is an agenda item)
                links = value_div.find_all('a', href=True)
                for link in links:
                    link_text = link.get_text(strip=True)
                    parsed_item = parse_agenda_item(link_text)
                    if parsed_item:
                        # Add URL if available
                        url = link.get('href', '')
                        if url.startswith('/'):
                            url = f"https://digitallibrary.un.org{url}"
                        elif not url.startswith('http'):
                            url = f"https://digitallibrary.un.org/{url}"
                        parsed_item['url'] = url
                        agenda_items.append(parsed_item)
    
    return agenda_items


def detect_document_type(input_dir: Path) -> str:
    """
    Detect document type from input directory path.
    
    Args:
        input_dir: Path to directory containing HTML files
    
    Returns:
        Document type string (resolutions, drafts, committee-reports, agenda, meetings, voting, other)
    """
    parts = input_dir.parts
    
    # Check for known document type folders
    if 'resolutions' in parts:
        return 'resolutions'
    elif 'drafts' in parts:
        return 'drafts'
    elif 'committee-reports' in parts or 'committee_reports' in parts:
        return 'committee-reports'
    elif 'agenda' in parts:
        return 'agenda'
    elif 'meetings' in parts:
        return 'meetings'
    elif 'voting' in parts:
        return 'voting'
    elif 'committee-summary-records' in parts or 'committee_summary_records' in parts:
        return 'committee-summary-records'
    else:
        return 'other'


def parse_metadata_html(html_file: Path) -> Dict:
    """
    Parse a UN Digital Library HTML metadata file.
    
    Works for all document types: resolutions, drafts, committee-reports, agenda, meetings, voting.
    
    Args:
        html_file: Path to HTML file
    
    Returns:
        Structured data dictionary
    """
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract basic metadata
    symbol = extract_metadata_row_value(soup, 'Symbol')
    title = extract_metadata_row_value(soup, 'Title')
    date = extract_metadata_row_value(soup, 'Date')
    action_note = extract_metadata_row_value(soup, 'Action note')
    description = extract_metadata_row_value(soup, 'Description')
    notes = extract_metadata_row_value(soup, 'Notes')
    
    # Extract authors
    authors_text = extract_metadata_row_value(soup, 'Authors')
    authors = [authors_text] if authors_text else []
    
    # Extract vote summary (may not exist for all document types)
    vote_text = extract_metadata_row_value(soup, 'Vote summary')
    vote_summary = parse_vote_summary(vote_text) if vote_text else None
    
    # Extract related documents (may not exist for all document types)
    draft_links = extract_metadata_row_links(soup, 'Draft')
    committee_report_links = extract_metadata_row_links(soup, 'Committee report')
    meeting_record_links = extract_metadata_row_links(soup, 'Meeting record')
    
    # Extract agenda information (may not exist for all document types)
    # Returns a list of agenda items since meetings can have multiple agenda items
    agenda_items = extract_agenda_items(soup)
    
    # Extract file access information
    # Prefer citation_pdf_url meta tags (more reliable direct PDF URLs)
    citation_files = extract_citation_pdf_urls(soup)
    access_files = extract_access_files(soup)
    
    # Merge files, preferring citation URLs (they come first)
    # Deduplicate by URL to avoid duplicates
    seen_urls = set()
    files = []
    for file_entry in citation_files + access_files:
        url = file_entry.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            files.append(file_entry)
    
    # Extract subjects
    subjects = extract_subjects(soup)
    
    # Extract record ID from filename or URL
    record_id = None
    if 'record_' in html_file.stem:
        match = re.search(r'record_(\d+)', html_file.stem)
        if match:
            record_id = match.group(1)

    doc_id = record_id or symbol
    
    # Build result structure aligned with schema
    result = {
        'id': doc_id,
        'metadata': {
            'id': doc_id,
            'symbol': symbol,
            'record_id': record_id,
            'title': title,
            'date': date,
            'action_note': action_note,
            'description': description,
            'notes': notes,
            'authors': authors,
            'source_file': html_file.name
        },
        'voting': vote_summary,
        'related_documents': {
            'drafts': draft_links,
            'committee_reports': committee_report_links,
            'meeting_records': meeting_record_links
        },
        'agenda': agenda_items if agenda_items else None,
        'files': files,
        'subjects': subjects
    }
    
    return result


def parse_metadata_html_files(input_dir: Path, output_dir: Path, max_files: Optional[int] = None):
    """
    Parse all HTML files in a directory.
    
    Args:
        input_dir: Directory containing HTML files
        output_dir: Directory to save JSON files
        max_files: Maximum number of files to process (None = all)
    """
    html_files = list(input_dir.glob('*.html'))
    
    if max_files:
        html_files = html_files[:max_files]
    
    print(f"Found {len(html_files)} HTML files to parse")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    parsed = 0
    failed = 0
    
    for html_file in html_files:
        print(f"\nParsing: {html_file.name}")
        
        try:
            data = parse_metadata_html(html_file)
            
            # Create output filename
            output_filename = html_file.stem + '.json'
            output_path = output_dir / output_filename
            
            # Save JSON
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"  ✓ Saved: {output_filename}")
            print(f"    Symbol: {data['metadata'].get('symbol', 'N/A')}")
            if data['voting']:
                print(f"    Vote: {data['voting'].get('raw_text', 'N/A')}")
            print(f"    Drafts: {len(data['related_documents']['drafts'])}")
            print(f"    Committee Reports: {len(data['related_documents']['committee_reports'])}")
            print(f"    Meeting Records: {len(data['related_documents']['meeting_records'])}")
            if data['agenda']:
                print(f"    Agenda Items: {len(data['agenda'])}")
            print(f"    Subjects: {len(data['subjects'])}")
            
            parsed += 1
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed += 1
    
    print(f"\n" + "="*60)
    print(f"SUMMARY")
    print(f"="*60)
    print(f"Total files: {len(html_files)}")
    print(f"Parsed: {parsed}")
    print(f"Failed: {failed}")
    print(f"Output directory: {output_dir.absolute()}")


def main():
    parser = argparse.ArgumentParser(
        description='Parse UN Digital Library HTML metadata pages',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Parses UN Digital Library HTML metadata pages to extract rich metadata including:
- Basic metadata (symbol, title, date, action note)
- Voting information
- Related documents (drafts, committee reports, meeting records)
- Agenda information
- Subjects/topics
- Available file formats and languages

Supports all document types: resolutions, drafts, committee-reports, agenda, meetings, voting

Examples:
  # Parse all HTML files in directory (auto-detects type)
  python parse_metadata_html.py data/documents/html/resolutions
  
  # Parse committee reports
  python parse_metadata_html.py data/documents/html/committee-reports
  
  # Parse first 5 files
  python parse_metadata_html.py data/documents/html/resolutions --max-files 5
  
  # Custom output directory
  python parse_metadata_html.py data/documents/html/resolutions -o data/parsed/html/resolutions
        """
    )
    parser.add_argument('input_dir', type=Path, help='Directory containing HTML files')
    parser.add_argument('-o', '--output', type=Path, default=None,
                        help='Output directory for JSON files (default: auto-detect from input path)')
    parser.add_argument('--max-files', type=int, default=None,
                        help='Maximum number of files to process (default: all)')

    args = parser.parse_args()
    
    input_dir = args.input_dir
    
    if not input_dir.exists():
        parser.error(f"Directory not found: {input_dir}")
    
    # Auto-detect output directory and document type
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
            # Look for documents/html in path
            parts = input_dir.parts
            if 'documents' in parts:
                base_dir = Path(*parts[:parts.index('documents')])
            else:
                base_dir = Path('data')
        
        output_dir = base_dir / 'parsed' / 'html' / doc_type
    
    if args.max_files:
        print(f"Limit: First {args.max_files} files")
    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")
    
    parse_metadata_html_files(input_dir, output_dir, args.max_files)


if __name__ == "__main__":
    main()

