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

## Genealogy tracing demo

Use `trace_genealogy.py` to walk from an agenda item, draft, or resolution through the related drafts, committee reports, meetings, and agenda references. The script now supports three output modes:

```bash
# Existing text tree view
uv run trace_genealogy.py A/RES/78/220

# Structured node-link graph JSON (pass '-' to stream to stdout)
uv run trace_genealogy.py A/RES/78/220 --graph-json scratch/iran_graph.json

# Render a lightweight HTML demo you can open locally
uv run trace_genealogy.py A/RES/78/220 --graph-html scratch/iran_graph.html

# Produce a Mermaid diagram snippet for docs
uv run trace_genealogy.py A/RES/78/220 --graph-mermaid scratch/iran_graph.mmd
```

Quick sanity check: `uv run example_trace.py` enumerates all three traversal modes (agenda → forwards, resolution → backwards, draft ↔ both) so you can confirm coverage before running heavier jobs.

The JSON graph output is the recommended starting point for the future gym backend. It contains node metadata (`symbol`, `doc_type`, `title`, `found`) and typed edges that connect agenda items → drafts → committee reports/meetings → resolutions. The lightweight HTML helper is only meant for demos; swap it out once the backend graph stabilizes.

## Build and inspect RL trajectories

Once you have genealogy coverage for a resolution, you can convert it into a MARL-ready trajectory JSON and review the resulting sequence of states/actions.

```bash
# Build a trajectory for a resolution using all locally parsed data
uv run build_trajectory.py A/RES/78/220 --pretty -o trajectory_A_RES_78_220.json

# `build_trajectory.py`:
#   • crawls the genealogy via `trace_genealogy.py`
#   • stitches agenda, drafts, committee reports, and plenary meetings into timesteps
#   • emits metadata + per-timestep state/action/observation blocks for the MARL env
```

Each timestep currently ends up in one of five coarse stages (`agenda_allocation`, `draft_submission`, `committee_vote`, `plenary_discussion`, `plenary_vote`) and stores three payloads: `state` (document symbol, dates, meeting numbers), `action` (sponsor, vote rolls, statements), and `observation` (publication/distribution flags plus tallies). This is the contract the RL env consumes, so tweak the builder before changing downstream agents.

You can restrict output formatting with `--pretty` (pretty-print JSON) and point to a custom filename via `-o/--output`. The script prints a quick timeline summary when the build finishes.

To explore the resulting file without writing custom tooling, use the lightweight CLI visualizer:

```bash
# Default view: walk every timestep with aggregate info
uv run visualize_trajectory.py trajectory_A_RES_78_220.json

# Helpful flags
uv run visualize_trajectory.py trajectory_A_RES_78_220.json \
    --timestep 3 \            # focus on a single stage
    --verbose \               # show full vote rolls, longer excerpts
    --comparison \            # compare committee vs plenary tallies
    --countries               # summarize actions per country
```

`--comparison` reproduces committee vs plenary deltas, while `--countries` aggregates everything a country did (sponsorship + votes) into a mini action log. The visualizer only reads the saved JSON, so you can share trajectories with teammates and inspect them without needing the full scrape.

🗂️  `viz/` contains finished outputs for the Iran case study (`A/RES/78/220`):
- `viz/analyze_iran_genealogy.py` → `viz/analysis_iran_genealogy.json` + `viz/analysis_iran_genealogy_report.md` (timeline, vote comparison, data availability table)
- `viz/iran_graph.html`, `viz/ukr_graph.html`, etc. → static previews emitted by `trace_genealogy.py --graph-html`

Use these artifacts as reference when evaluating whether a new session has enough coverage to build trajectories.

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

# UI
uv run uvicorn ui.app:app --reload