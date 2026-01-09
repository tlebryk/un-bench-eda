# UN Document Scraper & Deliberation Gym

A complete pipeline for collecting UN General Assembly documents, building resolution trajectories, and training reinforcement learning agents on UN negotiation processes.

**Components:**
1. **ETL Pipeline:** Fetch, parse, and download UN documents from the UN Digital Library
2. **Trajectory Builder:** Construct resolution genealogies and RL-ready trajectories
3. **UN Deliberation Gym:** OpenAI Gym environment for modeling country voting behavior
4. **Interactive Visualization:** Terminal and web UIs for exploring trajectories

For the full research context, see [project.md](project.md).

## Documentation Map

- [docs/etl.md](docs/etl.md) – End-to-end ETL runbook (fetch → parse → load, QA, incident notes)
- [docs/README_DATABASE.md](docs/README_DATABASE.md) – Schema details, meeting utterances storage, genealogy traversal
- [docs/gym.md](docs/gym.md) & [docs/training_eval.md](docs/training_eval.md) – Gym internals, evaluation, world-model/IRL experiments
- [docs/rag_enhancement_plan.md](docs/rag_enhancement_plan.md) – RAG + multi-step orchestration design and backlog

## Dependency Management

This project uses **uv** with **dependency groups** to manage different components efficiently:

- **Core dependencies** (always installed): App, RAG, DB, Gym
- **ETL group**: PDF parsing (`pdfplumber`) - only needed for ETL operations
- **Training group**: PyTorch (`torch`) - only needed for training scripts (~900MB)

### Installation Options

```bash
# Core only (app, rag, db, gym - recommended for most work)
make install
# or: uv sync

# Add ETL capabilities (PDF parsing)
make install-etl
# or: uv sync --group etl

# Add training capabilities (PyTorch)
make install-training
# or: uv sync --group training

# Everything
make install-all
# or: uv sync --group etl --group training

# Full development setup
make dev
# or: uv sync --group dev --group etl --group training
```

**Why this approach?**
- Single environment (no multiple venvs to manage)
- Space efficient (torch only installed when needed)
- Fast installs (core dependencies are lightweight)
- Clear separation of concerns

See `Makefile` for convenient commands, or use `make help` for all options.

## Quick Start

### UN Deliberation Gym

Try the interactive RL environment:

```bash
# Interactive mode (you choose actions)
uv run python -m un_gym.cli.play --country France

# Expert mode (watch historical behavior)
uv run python -m un_gym.cli.play --country Germany --expert

# Generate web visualization
uv run python -m un_gym.cli.generate_web_viz \
    --country France \
    --output viz_france.html

open viz_france.html
```

See **[docs/gym.md](docs/gym.md)** for full gym documentation.

### ETL Pipeline

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

Once you have genealogy coverage for a resolution, you can convert it into a MARL-ready trajectory JSON and use it with the UN Deliberation Gym.

### Build trajectory

```bash
# Build a trajectory for a resolution using all locally parsed data
uv run -m etl.trajectories.build_trajectory A/RES/78/220 --pretty -o trajectory_A_RES_78_220.json

# `build_trajectory.py`:
#   • crawls the genealogy via `trace_genealogy.py`
#   • stitches agenda, drafts, committee reports, and plenary meetings into timesteps
#   • emits metadata + per-timestep state/action/observation blocks for the RL env
```

Each timestep ends up in one of five stages (`agenda_allocation`, `draft_submission`, `committee_vote`, `plenary_discussion`, `plenary_vote`) with three payloads:
- **state:** Document symbol, dates, meeting numbers
- **action:** Sponsors, vote rolls, statements
- **observation:** Publication/distribution flags, vote tallies

### Visualize trajectory

Multiple ways to explore trajectories:

```bash
# CLI visualizer
uv run -m etl.trajectories.visualize_trajectory trajectory_A_RES_78_220.json \
    --verbose \               # show full vote rolls
    --comparison \            # compare committee vs plenary
    --countries               # summarize per-country actions

# Interactive gym (terminal UI)
uv run python -m un_gym.cli.play \
    --trajectory trajectory_A_RES_78_220.json \
    --country France \
    --expert                  # auto-play historical actions

# Web visualization (with resolution text)
uv run python -m un_gym.cli.generate_web_viz \
    --trajectory trajectory_A_RES_78_220.json \
    --country France \
    --output viz.html

open viz.html
```

🗂️  **Reference outputs** for the Iran case study (`A/RES/78/220`):
- `viz/analyze_iran_genealogy.py` → analysis JSON + report
- `viz/iran_graph.html`, `viz/ukr_graph.html` → static graph previews
- `scratch/220.json` → example trajectory for gym

See **[docs/gym.md](docs/gym.md)** for full gym documentation and API reference.

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

# Committee summary records
uv run -m etl.fetch_download.fetch_metadata 78 --types committee-summary-records

# Meeting records
uv run -m etl.fetch_download.fetch_metadata 78 --types meetings
```

Available types: `resolutions`, `committee-drafts`, `committee-reports`, `committee-summary-records`, `plenary-drafts`, `agenda`, `meetings`, `voting`, `all` (default)

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

### ETL Pipeline
- `etl/fetch_download/` - Fetch MARCXML and HTML from UN Digital Library
- `etl/parsing/` - Parse XML and HTML to JSON
- `etl/trajectories/` - Trace genealogies and build RL trajectories
- `etl/run_etl.py` - Main ETL orchestration
- `tests/etl_tests/` - ETL pipeline tests

### UN Deliberation Gym
- `un_gym/env.py` - Main RL environment (OpenAI Gym API)
- `un_gym/spaces.py` - State/action space definitions
- `un_gym/data_adapter.py` - Trajectory JSON → gym episodes
- `un_gym/dynamics.py` - Transition dynamics (empirical sampling)
- `un_gym/metrics.py` - Evaluation metrics
- `un_gym/viz.py` - Plotting utilities
- `un_gym/interactive.py` - Terminal UI
- `un_gym/cli/` - Command-line tools (play, generate_web_viz)
- `tests/gym/` - Gym tests (33 tests, all passing)

### Documentation
- **[docs/gym.md](docs/gym.md)** - **Complete gym documentation** (API, features, research directions)
- `project.md` - Research project description (IGO-Gym benchmark)
- `un_document_structure.md` - UN document naming conventions
- `docs/new_scrape_plan.md` - Document collection requirements
- `docs/MEETING_UTTERANCES.md` - Statement extraction guide

### Database & UI
- `db/` - PostgreSQL schema and setup
- `ui/` - FastAPI web application
- `docker-compose.yml` - Local development stack

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

### Option 2: Docker UI with Hot Reload (Recommended for Development)
```bash
# Start UI with hot reload - changes to HTML/Python files are reflected immediately
# No need to rebuild when editing templates, static files, or Python code
# Uses production database by default
docker-compose up ui_reload

# Or using Makefile
make docker-reload
```
Access at http://localhost:8000

**Benefits:**
- ✅ Hot reload - no rebuild needed for code changes
- ✅ Mounts `ui/`, `db/`, `rag/` directories as volumes
- ✅ Changes to HTML templates, CSS, and Python code reload automatically
- ✅ Auth disabled by default (`ENABLE_AUTH=false`) for easier development

**To use with dev database instead:**
```bash
# Connect to dev database (postgres_dev) instead of production
docker-compose up ui_reload_dev_db

# Or using Makefile
make docker-reload-dev-db
```
Access at http://localhost:8001 (different port to avoid conflicts)

### Option 3: Databases Only + Local UI
```bash
# Start just databases
docker-compose up postgres postgres_dev -d

# Run UI with uv (hot reload for development)
uv run uvicorn ui.app:app --reload

# Or using Makefile
make app
```
Access at http://localhost:8000

### Option 4: Individual Services
```bash
# Just UI (auto-starts postgres via depends_on)
docker-compose up ui

# Just production database
docker-compose up postgres

# Just dev database
docker-compose up postgres_dev
```

## Debugging

### Tool Call Logging

Tool calls (multistep RAG) are logged to `logs/multistep_tools.log` with detailed timing, arguments, and results.

```bash
# Watch tool calls in real-time
make logs-tail

# Or manually
tail -f logs/multistep_tools.log

# Check if tools are being called
grep "TOOL CALL" logs/multistep_tools.log
```

Logs are persistent (mounted as Docker volumes) and include execution time, arguments, and result summaries for each tool call.

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
