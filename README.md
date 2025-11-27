# UN Document Scraper

A modular scraper for collecting UN General Assembly documents and building version history chains for the IGO-Gym benchmark project.

This project provides a set of Python scripts to fetch, parse, and download UN documents from the UN Digital Library.

For the full research context, see [project.md](project.md).

## Quick Start

The scraper uses a 3-stage pipeline:

### 1. Fetch metadata (XML)
```bash
# Fetch all document types for session 78
uv run fetch_metadata.py 78

# Or fetch specific types
uv run fetch_metadata.py 78 --types agenda voting plenary-drafts
```
This saves MARCXML to `data/raw/xml/`

### 2. Parse metadata (JSON)
```bash
# Parse a single XML file (auto-detects output path)
uv run parse_metadata.py data/raw/xml/session_78_resolutions.xml

# Or specify custom output path
uv run parse_metadata.py data/raw/xml/session_78_resolutions.xml -o custom_output.json
```
This creates JSON files in `data/parsed/metadata/`

### 3. Download PDFs
```bash
# Download all PDFs (English only by default)
uv run download_pdfs.py data/parsed/metadata/session_78_resolutions.json

# Download first 5 PDFs
uv run download_pdfs.py data/parsed/metadata/session_78_resolutions.json --max-docs 5

# Download all languages
uv run download_pdfs.py data/parsed/metadata/session_78_resolutions.json --all-languages
```
This saves PDFs to `data/documents/pdfs/{resolutions,drafts,agenda,...}/`

### 4. Download HTML metadata pages (optional)
```bash
# Download HTML metadata pages for all document types
uv run download_metadata_html.py data/parsed/metadata/session_78_resolutions.json

# Download first 5 HTML pages
uv run download_metadata_html.py data/parsed/metadata/session_78_resolutions.json --max-docs 5
```
This saves HTML to `data/documents/html/{resolutions,drafts,committee-reports,agenda,meetings,voting}/`

### 5. Parse HTML metadata (optional)
```bash
# Parse HTML files (auto-detects document type from path)
uv run parse_metadata_html.py data/documents/html/resolutions

# Parse committee reports
uv run parse_metadata_html.py data/documents/html/committee-reports

# Parse first 5 files
uv run parse_metadata_html.py data/documents/html/resolutions --max-files 5
```
This saves parsed JSON to `data/parsed/html/{resolutions,drafts,committee-reports,agenda,meetings,voting}/`

### Quick test
```bash
bash test_pipeline.sh  # Downloads 3 sample PDFs
```

### Fetch specific document types

```bash
# Just resolutions
uv run fetch_metadata.py 78 --types resolutions

# Just voting records (for linking drafts to resolutions)
uv run fetch_metadata.py 78 --types voting

# Agenda and plenary drafts
uv run fetch_metadata.py 78 --types agenda plenary-drafts

# Committee drafts only
uv run fetch_metadata.py 78 --types committee-drafts

# Meeting records
uv run fetch_metadata.py 78 --types meetings
```

Available types: `resolutions`, `committee-drafts`, `plenary-drafts`, `agenda`, `meetings`, `voting`, `all` (default)

### Complete collection for a session

Collect all document types for multiple sessions:
```bash
# Collect documents for sessions 75, 76, 77, 78, 79
SESSIONS="75 76 77 78 79" bash collect_multiple_sessions.sh
```

Or test all new document types for one session:
```bash
uv run test_new_features.py
```

## Data Organization

The pipeline organizes data in multiple stages:

```
data/
├── raw/xml/                          # Stage 1: Fetched MARCXML
│   ├── session_78_resolutions.xml
│   ├── session_78_committee_1_drafts.xml
│   ├── session_78_plenary_drafts.xml
│   ├── session_78_agenda.xml
│   ├── session_78_meetings.xml
│   └── session_78_voting.xml
│
├── parsed/metadata/                  # Stage 2: Parsed JSON from XML
│   ├── session_78_resolutions.json
│   ├── session_78_committee_1_drafts.json
│   ├── session_78_plenary_drafts.json
│   └── ...
│
├── documents/
│   ├── pdfs/                         # Stage 3: Downloaded PDFs
│   │   ├── resolutions/
│   │   ├── drafts/
│   │   ├── agenda/
│   │   ├── meetings/
│   │   └── voting/
│   │
│   └── html/                         # Stage 4: Downloaded HTML metadata pages
│       ├── resolutions/
│       ├── drafts/
│       ├── committee-reports/
│       ├── agenda/
│       ├── meetings/
│       └── voting/
│
└── parsed/html/                      # Stage 5: Parsed JSON from HTML
    ├── resolutions/
    ├── drafts/
    ├── committee-reports/
    ├── agenda/
    ├── meetings/
    └── voting/
```

## Project Structure

**Scripts:**
- `fetch_metadata.py` - Fetch MARCXML from UN Digital Library API
- `parse_metadata.py` - Parse XML to JSON with PDF URLs
- `download_pdfs.py` - Download PDFs from extracted URLs
- `download_metadata_html.py` - Download HTML metadata pages from UN Digital Library
- `parse_metadata_html.py` - Parse HTML metadata pages to JSON (supports all document types)
- `test_new_features.py` - Test all new document types
- `test_pipeline.sh` - Quick validation test
- `collect_multiple_sessions.sh` - Batch collection script

**Documentation:**
- `project.md` - Research project description (IGO-Gym benchmark)
- `un_document_structure.md` - UN document naming conventions
- `new_scrape_plan.md` - Document collection requirements
- `ENGINEERING_NOTEBOOK.md` - Implementation notes and known issues