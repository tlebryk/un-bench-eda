#!/usr/bin/env python3
"""
Download HTML metadata pages from digitallibrary.un.org

This script downloads the HTML metadata pages for UN documents from the UN Digital Library.
These pages contain rich metadata including voting records, related documents, draft references,
committee reports, meeting records, agenda information, and subjects.

Reads from: data/parsed/metadata/*.json
Saves to: data/documents/html/{type}/ where type is one of:
  - resolutions
  - drafts
  - committee-reports
  - agenda
  - meetings
  - voting
"""

import json
import requests
import time
from pathlib import Path
import argparse


def record_id_to_digital_library_url(record_id: str) -> str:
    """
    Convert UN Digital Library record ID to metadata page URL.

    The Digital Library pages contain rich metadata including:
    - Vote summary
    - Draft references
    - Committee reports
    - Meeting records
    - Agenda information
    - Subjects/topics
    - Files in multiple languages

    Examples:
        4029926 → https://digitallibrary.un.org/record/4029926?v=pdf
        4060788 → https://digitallibrary.un.org/record/4060788?v=pdf

    Args:
        record_id: UN Digital Library record ID (e.g., "4029926")

    Returns:
        URL to metadata page at digitallibrary.un.org
    """
    return f"https://digitallibrary.un.org/record/{record_id}?v=pdf"


def symbol_to_metadata_page_url(symbol: str, language: str = "en") -> str:
    """
    Convert UN document symbol to docs.un.org metadata page URL (fallback method).

    This is used as a fallback when record_id is not available in the metadata.

    Examples:
        A/RES/78/276 → https://docs.un.org/en/A/res/78/276
        A/C.1/78/L.2 → https://docs.un.org/en/A/C.1/78/L.2
        A/78/251 → https://docs.un.org/en/A/78/251

    Args:
        symbol: UN document symbol (e.g., A/RES/78/276)
        language: Language code (default: en)

    Returns:
        URL to metadata page at docs.un.org
    """
    # Convert RES to lowercase res, keep everything else as-is
    symbol_lower = symbol.replace('/RES/', '/res/')

    return f"https://docs.un.org/{language}/{symbol_lower}"


def download_html(url: str, output_path: Path, max_retries: int = 5) -> bool:
    """
    Download HTML content from URL to file with rate limit handling.

    Args:
        url: HTML page URL
        output_path: Where to save the HTML
        max_retries: Maximum retry attempts

    Returns:
        True if successful, False otherwise
    """
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, timeout=30)
            
            # Handle rate limiting (HTTP 429)
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    try:
                        wait_time = int(retry_after)
                        print(f"  ⚠ Rate limited (429). Retry-After: {wait_time}s. Waiting...")
                        time.sleep(wait_time)
                    except ValueError:
                        # If Retry-After is not a number, use exponential backoff
                        wait_time = min(2 ** attempt, 60)  # Cap at 60 seconds
                        print(f"  ⚠ Rate limited (429). Waiting {wait_time}s...")
                        time.sleep(wait_time)
                else:
                    # No Retry-After header, use exponential backoff
                    wait_time = min(2 ** attempt, 60)  # Cap at 60 seconds
                    print(f"  ⚠ Rate limited (429). Waiting {wait_time}s...")
                    time.sleep(wait_time)
                continue  # Retry the request
            
            response.raise_for_status()

            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(response.text)

            file_size = output_path.stat().st_size
            print(f"  ✓ Downloaded ({file_size:,} bytes): {output_path.name}")
            return True

        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 429:
                # Already handled above, but catch here for safety
                continue
            print(f"  ✗ Attempt {attempt} failed (HTTP {e.response.status_code if e.response else 'unknown'}): {e}")
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 60))
        except Exception as e:
            print(f"  ✗ Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 60))

    return False


def download_metadata_html(json_file: str,
                           output_dir: str = None,
                           language: str = "en",
                           max_docs: int = None,
                           base_dir: str = "data",
                           delay: float = 1.0):
    """
    Download HTML metadata pages for documents in metadata JSON.

    Uses record_id to construct Digital Library URLs (primary method).
    Falls back to symbol-based docs.un.org URLs if record_id is not available.

    Args:
        json_file: Path to metadata JSON file
        output_dir: Directory to save HTML (default: auto-detect from filename)
        language: Language code for fallback docs.un.org URLs (default: "en")
        max_docs: Maximum number of documents to download (None = all)
        base_dir: Base data directory
        delay: Delay between requests in seconds (default: 1.0)
    """
    print(f"Loading metadata from {json_file}...")
    with open(json_file, 'r', encoding='utf-8') as f:
        metadata_list = json.load(f)

    print(f"Found {len(metadata_list)} documents")

    if max_docs:
        metadata_list = metadata_list[:max_docs]
        print(f"Limiting to {max_docs} documents")

    # Auto-detect output directory based on filename
    if output_dir is None:
        json_filename = Path(json_file).name
        # Auto-detect base directory from input path
        json_parts = Path(json_file).parts
        if 'test_data' in json_parts:
            base_data_dir = Path('test_data')
        elif 'dev_data' in json_parts:
            base_data_dir = Path('dev_data')
        elif 'data' in json_parts:
            base_data_dir = Path('data')
        else:
            base_data_dir = Path(base_dir)

        if 'resolutions' in json_filename:
            output_path = base_data_dir / "documents" / "html" / "resolutions"
            print(f"Auto-detected: Saving resolutions HTML to {output_path}")
        elif 'draft' in json_filename:
            output_path = base_data_dir / "documents" / "html" / "drafts"
            print(f"Auto-detected: Saving drafts HTML to {output_path}")
        elif 'committee-report' in json_filename or 'committee_reports' in json_filename:
            output_path = base_data_dir / "documents" / "html" / "committee-reports"
            print(f"Auto-detected: Saving committee-reports HTML to {output_path}")
        elif 'summary_records' in json_filename or 'summary-records' in json_filename:
            output_path = base_data_dir / "documents" / "html" / "committee-summary-records"
            print(f"Auto-detected: Saving committee-summary-records HTML to {output_path}")
        elif 'agenda' in json_filename:
            output_path = base_data_dir / "documents" / "html" / "agenda"
            print(f"Auto-detected: Saving agenda HTML to {output_path}")
        elif 'meeting' in json_filename:
            output_path = base_data_dir / "documents" / "html" / "meetings"
            print(f"Auto-detected: Saving meetings HTML to {output_path}")
        elif 'voting' in json_filename:
            output_path = base_data_dir / "documents" / "html" / "voting"
            print(f"Auto-detected: Saving voting HTML to {output_path}")
        else:
            output_path = base_data_dir / "documents" / "html" / "other"
            print(f"Unknown type: Saving to {output_path}")
    else:
        output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    failed = 0
    using_digital_library = 0
    using_fallback = 0

    for i, doc in enumerate(metadata_list, 1):
        symbol = doc.get('symbol', 'UNKNOWN')
        record_id = doc.get('record_id')
        
        print(f"\n[{i}/{len(metadata_list)}] {symbol}")

        # Prefer Digital Library URL if record_id is available
        if record_id:
            url = record_id_to_digital_library_url(record_id)
            using_digital_library += 1
            print(f"  → Digital Library URL: {url}")
            # Create filename: include symbol if available, otherwise just record_id
            if symbol and symbol != 'UNKNOWN':
                safe_symbol = symbol.replace('/', '_').replace(' ', '_')
                filename = f"{safe_symbol}_record_{record_id}.html"
            else:
                filename = f"record_{record_id}.html"
        elif symbol and symbol != 'UNKNOWN':
            # Fallback to symbol-based URL
            url = symbol_to_metadata_page_url(symbol, language=language)
            using_fallback += 1
            print(f"  → Fallback URL (docs.un.org): {url}")
            # Create safe filename from symbol
            safe_symbol = symbol.replace('/', '_').replace(' ', '_')
            filename = f"{safe_symbol}.html"
        else:
            print(f"  ✗ No symbol or record_id found")
            failed += 1
            continue

        file_path = output_path / filename

        # Skip if already exists
        if file_path.exists():
            print(f"  ⊙ Already exists: {filename}")
            downloaded += 1
            continue

        # Download
        if download_html(url, file_path):
            downloaded += 1
            time.sleep(delay)  # Rate limiting
        else:
            failed += 1

    print(f"\n" + "="*60)
    print(f"SUMMARY")
    print(f"="*60)
    print(f"Total documents: {len(metadata_list)}")
    print(f"Downloaded: {downloaded}")
    print(f"Failed: {failed}")
    print(f"Success rate: {downloaded/len(metadata_list)*100:.1f}%")
    print(f"Using Digital Library: {using_digital_library}")
    print(f"Using fallback (docs.un.org): {using_fallback}")
    print(f"Output directory: {output_path.absolute()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Download HTML metadata pages from digitallibrary.un.org',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Downloads HTML metadata pages from digitallibrary.un.org.
Uses record_id from metadata to construct Digital Library URLs.
Falls back to docs.un.org if record_id is not available.

Examples:
  # Download first 5 resolution metadata pages
  python download_metadata_html.py data/parsed/metadata/session_78_resolutions.json --max-docs 5
  
  # Download all resolution metadata (auto-detects output dir)
  python download_metadata_html.py data/parsed/metadata/session_78_resolutions.json
  
  # Custom output directory
  python download_metadata_html.py data/parsed/metadata/session_78_resolutions.json -o custom_dir/
        """
    )
    parser.add_argument('json_file', type=Path, help='Path to metadata JSON file')
    parser.add_argument('-o', '--output', type=Path, default=None,
                        help='Output directory for HTML files (default: auto-detect from filename)')
    parser.add_argument('--max-docs', type=int, default=None,
                        help='Maximum number of documents to download (default: all)')
    parser.add_argument('--base-dir', type=str, default='data',
                        help='Base data directory (default: data)')
    parser.add_argument('--language', type=str, default='en',
                        help='Language code for fallback docs.un.org URLs (default: en)')
    parser.add_argument('--delay', type=float, default=1.0,
                        help='Delay between requests in seconds (default: 1.0)')

    args = parser.parse_args()

    json_file = str(args.json_file)
    output_dir = str(args.output) if args.output else None
    max_docs = args.max_docs

    if max_docs:
        print(f"Limit: First {max_docs} documents")
    if output_dir:
        print(f"Output: {output_dir}")
    else:
        print(f"Output: Auto-detect based on filename")

    # Auto-detect base directory from input path
    json_parts = Path(json_file).parts
    if 'test_data' in json_parts:
        base_dir = 'test_data'
    elif 'dev_data' in json_parts:
        base_dir = 'dev_data'
    elif 'data' in json_parts:
        base_dir = 'data'
    else:
        base_dir = args.base_dir

    download_metadata_html(json_file, output_dir, args.language, max_docs, base_dir, args.delay)
