"""
Step 3: Download PDFs from parsed metadata

This script takes the parsed JSON metadata and downloads the actual PDF files.
Reads from: data/parsed/metadata/
Saves to: data/documents/pdfs/resolutions/ or data/documents/pdfs/drafts/
"""

import json
import requests
import time
from pathlib import Path
import argparse

# Data directories
RESOLUTIONS_DIR = Path("data/documents/pdfs/resolutions")
DRAFTS_DIR = Path("data/documents/pdfs/drafts")
RESOLUTIONS_DIR.mkdir(parents=True, exist_ok=True)
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)


def symbol_to_docs_url(symbol: str, language: str = "en") -> str:
    """
    Convert UN document symbol to documents.un.org API URL for PDF access.

    Uses the Official Document System (ODS) API which reliably serves PDFs.
    docs.un.org redirects to this endpoint.

    Examples:
        A/RES/78/276 → https://documents.un.org/api/symbol/access?s=A/res/78/276&l=en&t=pdf
        A/C.1/78/L.2 → https://documents.un.org/api/symbol/access?s=A/C.1/78/L.2&l=en&t=pdf
        A/78/251 → https://documents.un.org/api/symbol/access?s=A/78/251&l=en&t=pdf

    Args:
        symbol: UN document symbol (e.g., A/RES/78/276)
        language: Language code (default: en)

    Returns:
        URL to PDF at documents.un.org API
    """
    # Convert RES to lowercase res, keep everything else as-is
    symbol_lower = symbol.replace('/RES/', '/res/')

    # Construct ODS API URL
    return f"https://documents.un.org/api/symbol/access?s={symbol_lower}&l={language}&t=pdf"


def download_pdf(url: str, output_path: Path, max_retries: int = 5) -> bool:
    """
    Download a PDF from URL to file with rate limit handling.

    Args:
        url: PDF URL
        output_path: Where to save the PDF
        max_retries: Maximum retry attempts

    Returns:
        True if successful, False otherwise
    """
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, timeout=30, stream=True)
            
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

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

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


def download_documents_from_metadata(json_file: str,
                                       output_dir: str = None,
                                       language: str = "en",
                                       max_docs: int = None,
                                       english_only: bool = True,
                                       base_dir: str = "data",
                                       delay: float = 1.0):
    """
    Download PDFs for documents in metadata JSON.

    Uses docs.un.org URLs constructed from symbols (more reliable than Digital Library URLs).

    Args:
        json_file: Path to metadata JSON file
        output_dir: Directory to save PDFs (default: auto-detect from filename)
        language: Language code for docs.un.org (default: "en", ignored if english_only=False)
        max_docs: Maximum number of documents to download (None = all)
        english_only: If True, download English PDFs (language='en')
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
        elif 'data' in json_parts:
            base_data_dir = Path('data')
        else:
            base_data_dir = Path(base_dir)
        
        if 'resolutions' in json_filename:
            output_path = base_data_dir / "documents" / "pdfs" / "resolutions"
            print(f"Auto-detected: Saving resolutions to {output_path}")
        elif 'draft' in json_filename:
            output_path = base_data_dir / "documents" / "pdfs" / "drafts"
            print(f"Auto-detected: Saving drafts to {output_path}")
        elif 'agenda' in json_filename:
            output_path = base_data_dir / "documents" / "pdfs" / "agenda"
            print(f"Auto-detected: Saving agenda to {output_path}")
        elif 'committee-report' in json_filename or 'committee_reports' in json_filename:
            output_path = base_data_dir / "documents" / "html" / "committee-reports"
            print(f"Auto-detected: Saving committee-reports HTML to {output_path}")
        elif 'meeting' in json_filename:
            output_path = base_data_dir / "documents" / "pdfs" / "meetings"
            print(f"Auto-detected: Saving meetings to {output_path}")
        elif 'voting' in json_filename:
            output_path = base_data_dir / "documents" / "pdfs" / "voting"
            print(f"Auto-detected: Saving voting records to {output_path}")
        else:
            output_path = base_data_dir / "documents" / "pdfs" / "other"
            output_path.mkdir(parents=True, exist_ok=True)
            print(f"Unknown type: Saving to {output_path}")
    else:
        output_path = Path(output_dir)
    downloaded = 0
    failed = 0

    for i, doc in enumerate(metadata_list, 1):
        symbol = doc.get('symbol', 'UNKNOWN')
        print(f"\n[{i}/{len(metadata_list)}] {symbol}")

        # Skip if no symbol
        if symbol == 'UNKNOWN' or not symbol:
            print(f"  ✗ No symbol found")
            failed += 1
            continue

        # Construct docs.un.org URL from symbol (more reliable than Digital Library URLs)
        lang_code = 'en' if english_only else language
        url = symbol_to_docs_url(symbol, language=lang_code)
        print(f"  → URL: {url}")

        # Create safe filename from symbol
        safe_symbol = symbol.replace('/', '_').replace(' ', '_')
        filename = f"{safe_symbol}.pdf"
        file_path = output_path / filename

        # Skip if already exists
        if file_path.exists():
            print(f"  ⊙ Already exists: {filename}")
            downloaded += 1
            continue

        # Download
        if download_pdf(url, file_path):
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
    print(f"Output directory: {output_path.absolute()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Download PDFs from parsed metadata JSON files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download first 5 English resolutions (auto-detects output dir)
  python download_pdfs.py data/parsed/metadata/session_78_resolutions.json --max-docs 5
  
  # Download all English resolutions (auto-detects: data/documents/pdfs/resolutions/)
  python download_pdfs.py data/parsed/metadata/session_78_resolutions.json
  
  # Download committee drafts (auto-detects: data/documents/pdfs/drafts/)
  python download_pdfs.py data/parsed/metadata/session_78_committee_1_drafts.json
  
  # Custom output directory
  python download_pdfs.py data/parsed/metadata/session_78_resolutions.json -o custom_dir/
  
  # Download all languages
  python download_pdfs.py data/parsed/metadata/session_78_resolutions.json --all-languages
        """
    )
    parser.add_argument('json_file', type=Path, help='Path to metadata JSON file')
    parser.add_argument('-o', '--output', type=Path, default=None,
                        help='Output directory for PDFs (default: auto-detect from filename)')
    parser.add_argument('--max-docs', type=int, default=None,
                        help='Maximum number of documents to download (default: all)')
    parser.add_argument('--all-languages', action='store_true',
                        help='Download all languages (default: English only)')
    parser.add_argument('--base-dir', type=str, default='data',
                        help='Base data directory (default: data)')
    parser.add_argument('--delay', type=float, default=1.0,
                        help='Delay between requests in seconds (default: 1.0)')

    args = parser.parse_args()

    json_file = str(args.json_file)
    output_dir = str(args.output) if args.output else None
    max_docs = args.max_docs
    english_only = not args.all_languages

    print(f"Mode: {'English only' if english_only else 'All languages'}")
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
    elif 'data' in json_parts:
        base_dir = 'data'
    else:
        base_dir = args.base_dir
    
    download_documents_from_metadata(json_file, output_dir, "en", max_docs, english_only, base_dir, args.delay)
