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

echo
echo "=== STEP 1: Fetch metadata (Session 78 resolutions) ==="
uv run fetch_metadata.py 78 --types resolutions
uv run fetch_metadata.py 78 --types agenda
uv run fetch_metadata.py 78 --types plenary-drafts
uv run fetch_metadata.py 78 --types committee-drafts
uv run fetch_metadata.py 78 --types meetings
# uv run fetch_metadata.py 78 --types voting

echo
echo "=== STEP 2: Parse XML to JSON ==="
uv run parse_metadata.py data/raw/xml/session_78_resolutions.xml
uv run parse_metadata.py data/raw/xml/session_78_agenda.xml
uv run parse_metadata.py data/raw/xml/session_78_plenary_drafts.xml
uv run parse_metadata.py data/raw/xml/session_78_committee_reports.xml
uv run parse_metadata.py data/raw/xml/session_78_committee_1_drafts.xml
uv run parse_metadata.py data/raw/xml/session_78_committee_2_drafts.xml
uv run parse_metadata.py data/raw/xml/session_78_committee_3_drafts.xml
uv run parse_metadata.py data/raw/xml/session_78_committee_4_drafts.xml
uv run parse_metadata.py data/raw/xml/session_78_committee_5_drafts.xml
uv run parse_metadata.py data/raw/xml/session_78_committee_6_drafts.xml
uv run parse_metadata.py data/raw/xml/session_78_meetings.xml
# uv run parse_metadata.py data/raw/xml/session_78_voting.xml

echo
echo "=== STEP 3: Download English PDFs ==="
uv run download_pdfs.py data/parsed/metadata/session_78_resolutions.json
uv run download_pdfs.py data/parsed/metadata/session_78_agenda.json
uv run download_pdfs.py data/parsed/metadata/session_78_plenary_drafts.json
uv run download_pdfs.py data/parsed/metadata/session_78_committee_1_drafts.json
uv run download_pdfs.py data/parsed/metadata/session_78_committee_2_drafts.json
uv run download_pdfs.py data/parsed/metadata/session_78_committee_3_drafts.json
uv run download_pdfs.py data/parsed/metadata/session_78_committee_4_drafts.json
uv run download_pdfs.py data/parsed/metadata/session_78_committee_5_drafts.json
uv run download_pdfs.py data/parsed/metadata/session_78_committee_6_drafts.json
uv run download_pdfs.py data/parsed/metadata/session_78_committee_reports.json
uv run download_pdfs.py data/parsed/metadata/session_78_meetings.json


echo 
echo "=== STEP 4:  Download HTML metadata pages ==="
uv run download_metadata_html.py data/parsed/metadata/session_78_resolutions.json
uv run download_metadata_html.py data/parsed/metadata/session_78_agenda.json
uv run download_metadata_html.py data/parsed/metadata/session_78_plenary_drafts.json
uv run download_metadata_html.py data/parsed/metadata/session_78_committee_1_drafts.json
uv run download_metadata_html.py data/parsed/metadata/session_78_committee_2_drafts.json
uv run download_metadata_html.py data/parsed/metadata/session_78_committee_3_drafts.json
uv run download_metadata_html.py data/parsed/metadata/session_78_committee_4_drafts.json
#########################################################
# START HERE
#########################################################
uv run download_metadata_html.py data/parsed/metadata/session_78_committee_5_drafts.json
uv run download_metadata_html.py data/parsed/metadata/session_78_committee_6_drafts.json
uv run download_metadata_html.py data/parsed/metadata/session_78_committee_reports.json
uv run download_metadata_html.py data/parsed/metadata/session_78_meetings.json

echo 
echo "=== STEP 5: Parse HTML metadata pages ==="
uv run parse_metadata_html.py data/documents/html/resolutions
uv run parse_metadata_html.py data/documents/html/agenda
uv run parse_metadata_html.py data/documents/html/plenary_drafts
uv run parse_metadata_html.py data/documents/html/committee_1_drafts
uv run parse_metadata_html.py data/documents/html/committee_2_drafts
uv run parse_metadata_html.py data/documents/html/committee_3_drafts
uv run parse_metadata_html.py data/documents/html/committee_4_drafts
uv run parse_metadata_html.py data/documents/html/committee_5_drafts
uv run parse_metadata_html.py data/documents/html/committee_6_drafts
uv run parse_metadata_html.py data/documents/html/committee_reports
uv run parse_metadata_html.py data/documents/html/meetings

echo "=== STEP 6: Parse pdfs ==="
uv run parse_draft_pdf.py data/documents/pdfs/drafts
uv run parse_draft_pdf .py data/documents/pdfs/resolutions
uv run parse_committee_report_pdf.py data/documents/pdfs/committee-reports
uv run parse_meeting_pdf.py data/documents/pdfs/meetings
uv run parse_agenda_pdf.py data/documents/pdfs/agenda

# echo "=== STEP 7: Build trajectory ==="
# uv run build_trajectory.py data/documents/pdfs/resolutions