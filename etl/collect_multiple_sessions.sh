#!/bin/bash
#
# Comprehensive UN Document Collection Script
#
# Collects committee drafts from multiple GA sessions
# Skips resolutions due to data quality issues (only 1% success rate)
#

set -e  # Exit on error

# Configuration
SESSIONS="${SESSIONS:-75 76 77 78 79}"  # Default sessions, override with env var
DRY_RUN="${DRY_RUN:-false}"  # Set to 'true' for dry run

echo "=================================="
echo "UN Document Multi-Session Collection"
echo "=================================="
echo "Sessions: $SESSIONS"
echo "Focus: Committee drafts (100% success rate)"
echo "Skipping: Resolutions (data quality issues)"
echo "=================================="
echo

if [ "$DRY_RUN" = "true" ]; then
    echo "DRY RUN MODE - No downloads will occur"
    echo
fi

# Phase 1: Fetch metadata
echo "=== Phase 1: Fetching Metadata ==="
for session in $SESSIONS; do
    echo "Fetching session $session..."
    uv run -m etl.fetch_download.fetch_metadata $session
    echo
done

# Phase 2: Parse XML to JSON
echo "=== Phase 2: Parsing XML to JSON ==="
xml_count=$(ls -1 data/raw/xml/*.xml 2>/dev/null | wc -l | tr -d ' ')
echo "Found $xml_count XML files to parse"
for xml in data/raw/xml/*.xml; do
    filename=$(basename "$xml")
    echo "Parsing $filename..."
    uv run -m etl.parsing.parse_metadata "$xml"
done
echo

# Phase 3: Download PDFs (drafts only)
echo "=== Phase 3: Downloading English PDFs ==="
json_count=0
skipped_count=0
for json in data/parsed/metadata/*.json; do
    filename=$(basename "$json")

    # Skip resolutions
    if [[ "$filename" == *"resolutions"* ]]; then
        echo "Skipping $filename (resolutions have low success rate)"
        ((skipped_count++))
        continue
    fi

    echo "Processing $filename..."
    ((json_count++))

    if [ "$DRY_RUN" = "true" ]; then
        echo "  [DRY RUN] Would download from $filename"
    else
        uv run -m etl.fetch_download.download_pdfs "$json"
    fi
    echo
done

# Summary
echo "=================================="
echo "Collection Complete!"
echo "=================================="
echo "Sessions processed: $(echo $SESSIONS | wc -w | tr -d ' ')"
echo "XML files fetched: $xml_count"
echo "JSON files parsed: $((json_count + skipped_count))"
echo "  - Drafts processed: $json_count"
echo "  - Resolutions skipped: $skipped_count"
echo

if [ "$DRY_RUN" != "true" ]; then
    pdf_count=$(find data/documents/pdfs/drafts/ -name "*.pdf" 2>/dev/null | wc -l | tr -d ' ')
    echo "PDFs downloaded: $pdf_count"
    echo "Storage used: $(du -sh data/ 2>/dev/null | cut -f1)"
    echo
    echo "Output directories:"
    echo "  XML:  data/raw/xml/"
    echo "  JSON: data/parsed/metadata/"
    echo "  PDFs: data/documents/pdfs/drafts/"
else
    echo "DRY RUN complete - no PDFs downloaded"
fi

echo
echo "Next steps:"
echo "  1. Verify downloaded PDFs in data/documents/pdfs/drafts/"
echo "  2. Build version chains (future task)"
echo "  3. Extract text from PDFs for analysis"
