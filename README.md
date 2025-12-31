# UN Document Scraper

A modular scraper for collecting UN General Assembly documents and building version history chains for the IGO-Gym benchmark project.

This project provides a set of Python scripts to fetch, parse, and download UN documents from the UN Digital Library.

For the full research context, see [project.md](project.md).

## Quick Start

The scraper uses a 3-stage pipeline:

### 1. Fetch metadata (XML)
```bash
# Fetch all document types for session 78
uv run -m etl.fetch_download.fetch_metadata 78

# Or fetch specific types
uv run -m etl.fetch_download.fetch_metadata 78 --types agenda voting plenary-drafts
```
This saves MARCXML to `data/raw/xml/`

### 2. Parse metadata (JSON)
```bash
# Parse a single XML file (auto-detects output path)
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_resolutions.xml

# Or specify custom output path
uv run -m etl.parsing.parse_metadata data/raw/xml/session_78_resolutions.xml -o custom_output.json
```
This creates JSON files in `data/parsed/metadata/`

### 3. Download PDFs
```bash
# Download all PDFs (English only by default)
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_resolutions.json

# Download first 5 PDFs
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_resolutions.json --max-docs 5

# Download all languages
uv run -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_resolutions.json --all-languages
```
This saves PDFs to `data/documents/pdfs/{resolutions,drafts,agenda,...}/`

### 4. Download HTML metadata pages (optional)
```bash
# Download HTML metadata pages for all document types
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_resolutions.json

# Download first 5 HTML pages
uv run -m etl.fetch_download.download_metadata_html data/parsed/metadata/session_78_resolutions.json --max-docs 5
```
This saves HTML to `data/documents/html/{resolutions,drafts,committee-reports,agenda,meetings,voting}/`

### 5. Parse HTML metadata (optional)
```bash
# Parse HTML files (auto-detects document type from path)
uv run -m etl.parsing.parse_metadata_html data/documents/html/resolutions

# Parse committee reports
uv run -m etl.parsing.parse_metadata_html data/documents/html/committee-reports

# Parse first 5 files
uv run -m etl.parsing.parse_metadata_html data/documents/html/resolutions --max-files 5
```
This saves parsed JSON to `data/parsed/html/{resolutions,drafts,committee-reports,agenda,meetings,voting}/`

### Quick test
```bash
# Simple test (3 resolutions to test_data/)
bash tests/etl_tests/test_pipeline.sh

# Full dev pipeline (2 docs per type to dev_data/ for testing downstream tasks)
bash tests/etl_tests/test_dev_pipeline.sh
```

### Working with dev_data

After running the dev pipeline, test the complete workflow without affecting production data:

```bash
# 1. Run dev pipeline (downloads 2 docs per type to dev_data/)
bash tests/etl_tests/test_dev_pipeline.sh

# 2. Start PostgreSQL (both prod and dev databases)
docker-compose up -d

# 3. Setup dev database (PostgreSQL on port 5434)
uv run -m db.setup_db --dev

# 4. Load dev_data into dev database
uv run -m etl.run_etl --dev

# 5. Test trajectory building on dev data
uv run -m etl.trajectories.trace_genealogy A/RES/78/300 --data-root dev_data/parsed/html --verbose
uv run -m etl.trajectories.build_trajectory A/RES/78/300 --data-root dev_data/parsed/html --pretty -o dev_data/trajectory_test.json

# 6. Run UI app with dev database
USE_DEV_DB=true uv run uvicorn ui.app:app --reload
```

All trajectory scripts support the `--data-root` flag to point to `dev_data/parsed/html` instead of the default `data/parsed/html`.

**Dev vs Production:**
- **Data**: `dev_data/` (minimal test data) vs `data/` (full production data)
- **Database**: PostgreSQL `un_documents_dev` on port 5434 vs PostgreSQL `un_documents` on port 5433
- **ETL**: `uv run -m etl.run_etl --dev` vs `uv run -m etl.run_etl`
- **UI**: `USE_DEV_DB=true uv run uvicorn ui.app:app --reload` vs `uv run uvicorn ui.app:app --reload`

## Genealogy tracing demo

Use `trace_genealogy.py` to walk from an agenda item, draft, or resolution through the related drafts, committee reports, meetings, and agenda references. The script now supports three output modes:

```bash
# Existing text tree view
uv run -m etl.trajectories.trace_genealogy A/RES/78/220

# Structured node-link graph JSON (pass '-' to stream to stdout)
uv run -m etl.trajectories.trace_genealogy A/RES/78/220 --graph-json scratch/iran_graph.json

# Render a lightweight HTML demo you can open locally
uv run -m etl.trajectories.trace_genealogy A/RES/78/220 --graph-html scratch/iran_graph.html

# Produce a Mermaid diagram snippet for docs
uv run -m etl.trajectories.trace_genealogy A/RES/78/220 --graph-mermaid scratch/iran_graph.mmd
```

Quick sanity check: `uv run -m etl.trajectories.example_trace` enumerates all three traversal modes (agenda → forwards, resolution → backwards, draft ↔ both) so you can confirm coverage before running heavier jobs.

The JSON graph output is the recommended starting point for the future gym backend. It contains node metadata (`symbol`, `doc_type`, `title`, `found`) and typed edges that connect agenda items → drafts → committee reports/meetings → resolutions. The lightweight HTML helper is only meant for demos; swap it out once the backend graph stabilizes.

## Build and inspect RL trajectories

Once you have genealogy coverage for a resolution, you can convert it into a MARL-ready trajectory JSON and review the resulting sequence of states/actions.

```bash
# Build a trajectory for a resolution using all locally parsed data
uv run -m etl.trajectories.build_trajectory A/RES/78/220 --pretty -o trajectory_A_RES_78_220.json

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
uv run -m etl.trajectories.visualize_trajectory trajectory_A_RES_78_220.json

# Helpful flags
uv run -m etl.trajectories.visualize_trajectory trajectory_A_RES_78_220.json \
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
uv run -m etl.fetch_download.fetch_metadata 78 --types resolutions

# Just voting records (for linking drafts to resolutions)
uv run -m etl.fetch_download.fetch_metadata 78 --types voting

# Agenda and plenary drafts
uv run -m etl.fetch_download.fetch_metadata 78 --types agenda plenary-drafts

# Committee drafts only
uv run -m etl.fetch_download.fetch_metadata 78 --types committee-drafts

# Meeting records
uv run -m etl.fetch_download.fetch_metadata 78 --types meetings
```

Available types: `resolutions`, `committee-drafts`, `plenary-drafts`, `agenda`, `meetings`, `voting`, `all` (default)

### Complete collection for a session

Collect all document types for multiple sessions:
```bash
# Collect documents for sessions 75, 76, 77, 78, 79
SESSIONS="75 76 77 78 79" bash etl/collect_multiple_sessions.sh
```

Or test all new document types for one session:
```bash
uv run -m tests.etl_tests.test_new_features
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
- `etl/fetch_download/fetch_metadata.py` - Fetch MARCXML from UN Digital Library API
- `etl/parsing/parse_metadata.py` - Parse XML to JSON with PDF URLs
- `etl/fetch_download/download_pdfs.py` - Download PDFs from extracted URLs
- `etl/fetch_download/download_metadata_html.py` - Download HTML metadata pages from UN Digital Library
- `etl/parsing/parse_metadata_html.py` - Parse HTML metadata pages to JSON (supports all document types)
- `etl/trajectories/trace_genealogy.py` - Trace document genealogies
- `etl/trajectories/build_trajectory.py` - Build RL trajectories
- `tests/etl_tests/test_new_features.py` - Test all new document types
- `tests/etl_tests/test_pipeline.sh` - Quick validation test
- `etl/collect_multiple_sessions.sh` - Batch collection script

**Documentation:**
- `project.md` - Research project description (IGO-Gym benchmark)
- `un_document_structure.md` - UN document naming conventions
- `new_scrape_plan.md` - Document collection requirements
- `ENGINEERING_NOTEBOOK.md` - Implementation notes and known issues

# UI

## Local Development

### Option 1: Full Stack with Docker Compose (Recommended)
```bash
# Start everything (databases + UI)
docker-compose up

# Or run in background
docker-compose up -d

# View logs
docker-compose logs -f ui

# Stop everything
docker-compose down
```
Access at http://localhost:8000

The UI now prompts for a shared password at `/login`. Set `SHARED_PASSWORD` in your environment (Render dashboard, `.env`, etc.) and share the value out-of-band with collaborators who need access.

### Option 2: Databases Only + Local UI
```bash
# Start just databases
docker-compose up postgres postgres_dev -d

# Run UI with uv (hot reload for development)
uv run uvicorn ui.app:app --reload
```
Access at http://localhost:8000

### Option 3: Individual Services
```bash
# Just UI (auto-starts postgres via depends_on)
docker-compose up ui

# Just production database
docker-compose up postgres

# Just dev database
docker-compose up postgres_dev
```

## Deployment (Render + Supabase)

### Setup
1. **Supabase**: Create project, get connection string, run `DATABASE_URL="postgresql://..." uv run -m db.setup_db`
2. **Render**: New Web Service, Runtime=**Docker**, set env vars:
   - `DATABASE_URL` (from Supabase)
   - `OPENAI_API_KEY`
   - `ENABLE_AUTH=true`
   - `SHARED_PASSWORD=<your-password>`
3. **GitHub Actions**: Add `RENDER_DEPLOY_HOOK_URL` secret (from Render Settings → Deploy Hook)

### Environment Variables
- **Default**: Password-protected login via `ENABLE_AUTH=true` + `SHARED_PASSWORD`
- **Local override**: Set `ENABLE_AUTH=false` if you need to bypass the login locally

### Known Limitations
- **PDF links**: Currently expect local paths. Metadata may contain UN Digital Library URLs. Future: upload to Supabase Storage or S3.
- **Free tier**: Render sleeps after 15min inactivity (~30s wake-up). Upgrade to Starter ($7/mo) for always-on.

### Files
- `Dockerfile` - Multi-stage build using uv for Render
- `pyproject.toml` & `uv.lock` - Python dependencies (managed by uv)
- `.env.example` - Environment variable template
- `.github/workflows/deploy.yml` - CI/CD pipeline
