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
uv run -m etl.fetch_download.fetch_metadata 78 --types resolutions
uv run -m etl.fetch_download.fetch_metadata 78 --types agenda
uv run -m etl.fetch_download.fetch_metadata 78 --types plenary-drafts
uv run -m etl.fetch_download.fetch_metadata 78 --types committee-drafts
uv run -m etl.fetch_download.fetch_metadata 78 --types meetings
# uv run -m etl.fetch_download.fetch_metadata 78 --types voting

echo
echo "=== STEP 2: Parse XML to JSON ==="
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_resolutions.xml
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_agenda.xml
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_plenary_drafts.xml
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_committee_reports.xml
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_committee_1_drafts.xml
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_committee_2_drafts.xml
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_committee_3_drafts.xml
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_committee_4_drafts.xml
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_committee_5_drafts.xml
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_committee_6_drafts.xml
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_meetings.xml
# uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_voting.xml

echo
echo "=== STEP 3: Download English PDFs ==="
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_resolutions.json
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_agenda.json
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_plenary_drafts.json
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_committee_1_drafts.json
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_committee_2_drafts.json
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_committee_3_drafts.json
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_committee_4_drafts.json
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_committee_5_drafts.json
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_committee_6_drafts.json
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_committee_reports.json
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_meetings.json


echo
echo "=== STEP 4:  Download HTML metadata pages ==="
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_resolutions.json
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_agenda.json
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_plenary_drafts.json
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_committee_1_drafts.json
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_committee_2_drafts.json
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_committee_3_drafts.json
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_committee_4_drafts.json
#########################################################
# START HERE
#########################################################
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_committee_5_drafts.json
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_committee_6_drafts.json
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_committee_reports.json
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_meetings.json

echo
echo "=== STEP 5: Parse HTML metadata pages ==="
uv run -m etl.parsing.parse_metadata_html data/documents/html/resolutions
uv run -m etl.parsing.parse_metadata_html data/documents/html/agenda
uv run -m etl.parsing.parse_metadata_html data/documents/html/plenary_drafts
uv run -m etl.parsing.parse_metadata_html data/documents/html/committee_1_drafts
uv run -m etl.parsing.parse_metadata_html data/documents/html/committee_2_drafts
uv run -m etl.parsing.parse_metadata_html data/documents/html/committee_3_drafts
uv run -m etl.parsing.parse_metadata_html data/documents/html/committee_4_drafts
uv run -m etl.parsing.parse_metadata_html data/documents/html/committee_5_drafts
uv run -m etl.parsing.parse_metadata_html data/documents/html/committee_6_drafts
uv run -m etl.parsing.parse_metadata_html data/documents/html/committee_reports
uv run -m etl.parsing.parse_metadata_html data/documents/html/meetings

echo "=== STEP 6: Parse pdfs ==="
uv run -m etl.parsing.parse_draft_pdf data/documents/pdfs/drafts
uv run -m etl.parsing.parse_resolution_pdf data/documents/pdfs/resolutions
uv run -m etl.parsing.parse_committee_report_pdf data/documents/pdfs/committee-reports
uv run -m etl.parsing.parse_meeting_pdf data/documents/pdfs/meetings
uv run -m etl.parsing.parse_agenda_pdf data/documents/pdfs/agenda

# echo "=== STEP 7: Build trajectory ==="
# uv run build_trajectory.py data/documents/pdfs/resolutions