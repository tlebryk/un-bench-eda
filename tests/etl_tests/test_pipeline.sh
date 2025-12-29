#!/bin/bash
#
# Test the complete working pipeline on a small scale
#

set -e  # Exit on error

echo "================================"
echo "UN Document Scraper - Pipeline Test"
echo "================================"
echo

# Clean up any existing test data
echo "Cleaning up previous test data..."
rm -rf test_data
mkdir -p test_data/raw/xml test_data/parsed/metadata test_data/documents/pdfs

echo
echo "=== STEP 1: Fetch metadata (Session 78 resolutions) ==="
uv run fetch_metadata.py 78 --base-dir test_data --types resolutions

echo
echo "=== STEP 2: Parse XML to JSON ==="
uv run parse_metadata.py test_data/raw/xml/session_78_resolutions.xml

echo
echo "=== STEP 3: Download first 3 English PDFs ==="
uv run download_pdfs.py test_data/parsed/metadata/session_78_resolutions.json --max-docs 3
echo
echo "================================"
echo "Pipeline Test Complete!"
echo "================================"
echo
echo "Results:"
echo "  XML files:  $(ls -1 test_data/raw/xml/*.xml 2>/dev/null | wc -l | tr -d ' ')"
echo "  JSON files: $(ls -1 test_data/parsed/metadata/*.json 2>/dev/null | wc -l | tr -d ' ')"
echo "  PDF files:  $(ls -1 test_data/documents/pdfs/resolutions/*.pdf 2>/dev/null | wc -l | tr -d ' ')"
echo
echo "Check test_data/ directory for all downloaded files"
