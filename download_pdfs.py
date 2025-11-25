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
import sys

# Data directories
RESOLUTIONS_DIR = Path("data/documents/pdfs/resolutions")
DRAFTS_DIR = Path("data/documents/pdfs/drafts")
RESOLUTIONS_DIR.mkdir(parents=True, exist_ok=True)
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)


def download_pdf(url: str, output_path: Path, max_retries: int = 3) -> bool:
    """
    Download a PDF from URL to file.

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
            response.raise_for_status()

            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size = output_path.stat().st_size
            print(f"  ✓ Downloaded ({file_size:,} bytes): {output_path.name}")
            return True

        except Exception as e:
            print(f"  ✗ Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)

    return False


def download_documents_from_metadata(json_file: str,
                                       output_dir: str = None,
                                       language: str = "English",
                                       max_docs: int = None,
                                       english_only: bool = True):
    """
    Download PDFs for documents in metadata JSON.

    Args:
        json_file: Path to metadata JSON file
        output_dir: Directory to save PDFs (default: auto-detect from filename)
        language: Which language to download (default: English)
        max_docs: Maximum number of documents to download (None = all)
        english_only: If True, only download English PDFs (checks for 'English' or '-EN.pdf')
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
        if 'resolutions' in json_filename:
            output_path = RESOLUTIONS_DIR
            print(f"Auto-detected: Saving resolutions to {output_path}")
        elif 'draft' in json_filename:
            output_path = DRAFTS_DIR
            print(f"Auto-detected: Saving drafts to {output_path}")
        else:
            output_path = Path("data/documents/pdfs/other")
            output_path.mkdir(parents=True, exist_ok=True)
            print(f"Unknown type: Saving to {output_path}")
    else:
        output_path = Path(output_dir)
    downloaded = 0
    failed = 0

    for i, doc in enumerate(metadata_list, 1):
        symbol = doc.get('symbol', 'UNKNOWN')
        print(f"\n[{i}/{len(metadata_list)}] {symbol}")

        # Find file for requested language
        files = doc.get('files', [])
        target_file = None

        if english_only:
            # Look for English PDFs: either language="English" or URL ends with -EN.pdf
            for f in files:
                lang = f.get('language', '')
                url = f.get('url', '')
                if lang == 'English' or '-EN.pdf' in url or url.endswith('EN.pdf'):
                    target_file = f
                    break
        else:
            # Look for specific language
            for f in files:
                if f.get('language') == language:
                    target_file = f
                    break

        if not target_file:
            if english_only:
                print(f"  ⚠ No English file found")
            else:
                print(f"  ⚠ No {language} file found (available: {[f.get('language') for f in files]})")

            # Don't fallback if english_only is True
            if not english_only and files:
                target_file = files[0]
                print(f"  → Using {target_file.get('language')} instead")
            else:
                print(f"  ✗ Skipping (no suitable file)")
                failed += 1
                continue

        # Download
        url = target_file.get('url')
        if not url:
            print(f"  ✗ No URL found")
            failed += 1
            continue

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
            time.sleep(0.5)  # Rate limiting
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
    if len(sys.argv) < 2:
        print("Usage: python download_pdfs.py <metadata.json> [output_dir] [max_docs] [--all-languages]")
        print("\nBy default, downloads English PDFs only (checks for 'English' or '-EN.pdf')")
        print("Use --all-languages to download other languages")
        print("\nExamples:")
        print("  # Download first 5 English resolutions (auto-detects output dir)")
        print("  python download_pdfs.py data/parsed/metadata/session_78_resolutions.json 5")
        print("\n  # Download all English resolutions (auto-detects: data/documents/pdfs/resolutions/)")
        print("  python download_pdfs.py data/parsed/metadata/session_78_resolutions.json")
        print("\n  # Download committee drafts (auto-detects: data/documents/pdfs/drafts/)")
        print("  python download_pdfs.py data/parsed/metadata/session_78_committee_1_drafts.json")
        print("\n  # Custom output directory")
        print("  python download_pdfs.py data/parsed/metadata/session_78_resolutions.json custom_dir/")
        sys.exit(1)

    json_file = sys.argv[1]

    # Parse arguments
    output_dir = None
    max_docs = None

    # Check for --all-languages flag
    english_only = '--all-languages' not in sys.argv

    # Parse remaining positional arguments (skip argv[0] and argv[1])
    for arg in sys.argv[2:]:
        if arg == '--all-languages':
            continue
        try:
            # Try to parse as integer (max_docs)
            max_docs = int(arg)
        except ValueError:
            # Not an integer, must be output_dir
            output_dir = arg

    print(f"Mode: {'English only' if english_only else 'All languages'}")
    if max_docs:
        print(f"Limit: First {max_docs} documents")
    if output_dir:
        print(f"Output: {output_dir}")
    else:
        print(f"Output: Auto-detect based on filename")

    download_documents_from_metadata(json_file, output_dir, "English", max_docs, english_only)
