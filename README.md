# UN Document Scraper

A modular scraper for collecting UN General Assembly documents and building version history chains for the IGO-Gym benchmark project.

This project provides a set of Python scripts to fetch, parse, and download UN documents from the UN Digital Library.

For the full research context, see [project.md](project.md).

## Quick Start

The scraper uses a 3-stage pipeline:

### 1. Fetch metadata (XML)
```bash
# Fetch all document types for session 78
python3 fetch_metadata.py 78

# Or fetch specific types
python3 fetch_metadata.py 78 --types agenda voting plenary-drafts
```
This saves MARCXML to `data/raw/xml/`

### 2. Parse metadata (JSON)
```bash
# Parse all XML files in directory
python3 parse_metadata.py data/raw/xml/session_78_*.xml
```
This creates JSON files in `data/parsed/metadata/`

### 3. Download PDFs
```bash
# Download all PDFs (English only by default)
python3 download_pdfs.py data/parsed/metadata/session_78_*.json
```
This saves PDFs to `data/documents/pdfs/{resolutions,drafts,agenda,...}/`

### Quick test
```bash
bash test_pipeline.sh  # Downloads 3 sample PDFs
```

### Fetch specific document types

```bash
# Just resolutions
python3 fetch_metadata.py 78 --types resolutions

# Just voting records (for linking drafts to resolutions)
python3 fetch_metadata.py 78 --types voting

# Agenda and plenary drafts
python3 fetch_metadata.py 78 --types agenda plenary-drafts

# Committee drafts only
python3 fetch_metadata.py 78 --types committee-drafts

# Meeting records
python3 fetch_metadata.py 78 --types meetings
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
python3 test_new_features.py
```

## Data Organization

The pipeline organizes data in three stages:

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
├── parsed/metadata/                  # Stage 2: Parsed JSON
│   ├── session_78_resolutions.json
│   ├── session_78_committee_1_drafts.json
│   ├── session_78_plenary_drafts.json
│   └── ...
│
└── documents/pdfs/                   # Stage 3: Downloaded PDFs
    ├── resolutions/
    ├── drafts/
    ├── agenda/
    ├── meetings/
    └── voting/
```

## Project Structure

**Scripts:**
- `fetch_metadata.py` - Fetch MARCXML from UN Digital Library API
- `parse_metadata.py` - Parse XML to JSON with PDF URLs
- `download_pdfs.py` - Download PDFs from extracted URLs
- `test_new_features.py` - Test all new document types
- `test_pipeline.sh` - Quick validation test
- `collect_multiple_sessions.sh` - Batch collection script

**Documentation:**
- `project.md` - Research project description (IGO-Gym benchmark)
- `un_document_structure.md` - UN document naming conventions
- `new_scrape_plan.md` - Document collection requirements
- `ENGINEERING_NOTEBOOK.md` - Implementation notes and known issues