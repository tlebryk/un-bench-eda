#!/bin/bash
#
# Quick end-to-end development pipeline test
# Uses dev_data/ directory to avoid overwriting production data
# Downloads minimal data for testing downstream scripts (trajectories, UI)
#

set -e  # Exit on error

echo "========================================"
echo "UN Document Scraper - Dev Pipeline Test"
echo "========================================"
echo

# Configuration
DEV_DIR="dev_data"
SESSION="78"
MAX_DOCS=2  # Keep it small for quick testing

# Clean up previous dev data
echo "Cleaning up previous dev data..."
rm -rf $DEV_DIR
mkdir -p $DEV_DIR/raw/xml $DEV_DIR/parsed/metadata $DEV_DIR/documents/pdfs

echo
echo "=== STEP 1: Fetch metadata (Session $SESSION - minimal set) ==="
uv run -m etl.fetch_download.fetch_metadata $SESSION --base-dir $DEV_DIR --types resolutions
uv run -m etl.fetch_download.fetch_metadata $SESSION --base-dir $DEV_DIR --types plenary-drafts
uv run -m etl.fetch_download.fetch_metadata $SESSION --base-dir $DEV_DIR --types committee-drafts
uv run -m etl.fetch_download.fetch_metadata $SESSION --base-dir $DEV_DIR --types meetings
uv run -m etl.fetch_download.fetch_metadata $SESSION --base-dir $DEV_DIR --types agenda

echo
echo "=== STEP 2: Parse XML to JSON ==="
# Parse metadata.py saves to data/parsed/metadata/ by default, so specify output to dev_data
for xml in $DEV_DIR/raw/xml/*.xml; do
    [ -f "$xml" ] || continue
    basename=$(basename "$xml" .xml)
    echo "Parsing $(basename $xml)..."
    uv run -m etl.parsing.parse_metadata "$xml" -o "$DEV_DIR/parsed/metadata/${basename}.json"
done

echo
echo "=== STEP 3: Download first $MAX_DOCS PDFs ==="
for json in $DEV_DIR/parsed/metadata/*.json; do
    [ -f "$json" ] || continue
    echo "Downloading PDFs from $(basename $json)..."
    uv run -m etl.fetch_download.download_pdfs "$json" --max-docs $MAX_DOCS
done

echo
echo "=== STEP 4: Download HTML metadata pages ==="
for json in $DEV_DIR/parsed/metadata/*.json; do
    [ -f "$json" ] || continue
    echo "Downloading HTML for $(basename $json)..."
    uv run -m etl.fetch_download.download_metadata_html "$json" --max-docs $MAX_DOCS
done

echo
echo "=== STEP 5: Parse HTML metadata ==="
for htmldir in $DEV_DIR/documents/html/*; do
    [ -d "$htmldir" ] || continue
    echo "Parsing HTML in $(basename $htmldir)..."
    uv run -m etl.parsing.parse_metadata_html "$htmldir" || true
done

echo
echo "=== STEP 6: Parse PDFs ==="
# Parse drafts (committee and plenary)
for draftdir in $DEV_DIR/documents/pdfs/committee_*_drafts $DEV_DIR/documents/pdfs/plenary_drafts; do
    if [ -d "$draftdir" ]; then
        echo "Parsing draft PDFs in $(basename $draftdir)..."
        uv run -m etl.parsing.parse_draft_pdf "$draftdir" --max-files 2 || true
    fi
done

# Parse resolutions
if [ -d "$DEV_DIR/documents/pdfs/resolutions" ]; then
    echo "Parsing resolution PDFs..."
    uv run -m etl.parsing.parse_resolution_pdf "$DEV_DIR/documents/pdfs/resolutions" --max-files 2 || true
fi

# Parse committee reports
if [ -d "$DEV_DIR/documents/pdfs/committee-reports" ]; then
    echo "Parsing committee report PDFs..."
    uv run -m etl.parsing.parse_committee_report_pdf "$DEV_DIR/documents/pdfs/committee-reports" --max-files 2 || true
fi

# Parse meetings
if [ -d "$DEV_DIR/documents/pdfs/meetings" ]; then
    echo "Parsing meeting PDFs..."
    uv run -m etl.parsing.parse_meeting_pdf "$DEV_DIR/documents/pdfs/meetings" --max-files 2 || true
fi

# Parse agenda
if [ -d "$DEV_DIR/documents/pdfs/agenda" ]; then
    echo "Parsing agenda PDFs..."
    uv run -m etl.parsing.parse_agenda_pdf "$DEV_DIR/documents/pdfs/agenda" --max-files 2 || true
fi

echo
echo "========================================"
echo "Dev Pipeline Test Complete!"
echo "========================================"
echo
echo "Results:"
echo "  XML files:  $(find $DEV_DIR/raw/xml -name "*.xml" 2>/dev/null | wc -l | tr -d ' ')"
echo "  JSON files: $(find $DEV_DIR/parsed -name "*.json" 2>/dev/null | wc -l | tr -d ' ')"
echo "  PDF files:  $(find $DEV_DIR/documents/pdfs -name "*.pdf" 2>/dev/null | wc -l | tr -d ' ')"
echo "  HTML files: $(find $DEV_DIR/documents/html -name "*.html" 2>/dev/null | wc -l | tr -d ' ')"
echo
echo "Data stored in: $DEV_DIR/"
echo
echo "Next steps:"
echo "  1. Test trajectory building on dev data"
echo "  2. Test UI app with dev data"
echo "  3. Run: uv run uvicorn ui.app:app --reload"
echo
