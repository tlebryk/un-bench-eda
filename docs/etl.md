# ETL Pipeline Guide

Single reference for how we fetch, parse, validate, and load UN documents into Postgres.

---

## 1. Pipeline Overview

**Goal:** Transform raw UN Digital Library artifacts (XML, HTML, PDFs) into structured tables that power the database, trajectories, RAG stack, and UI.

**High-level flow**
```
fetch_download/      →   parsing/                 →   etl/load_*.py                 →  db (documents, votes, ...)
UN API (XML, HTML)       JSON metadata / parsed       SQLAlchemy loaders + BaseLoader       QA + downstream trajectories
```

### Entry points

**Note:** The ETL pipeline has 3 separate stages (Fetch → Parse → Load) that must be run independently.

- `uv run python -m etl.run_etl --reset` – **Load stage only:** load all parsed JSON files into database (does NOT fetch or parse)
- `uv run python -m etl.fetch_download.fetch_metadata 78 --types resolutions drafts committee-reports` – **Fetch stage:** download metadata XML from UN
- `uv run python -m etl.parsing.parse_metadata_html data/documents/html/committee-reports/` – **Parse stage:** convert HTML → JSON
- `uv run python scripts/setup_db.py` – apply schema (see `db/models.py`)

All scripts rely on uv; configure targets via argparse flags (`--types`, `--session`, `--max-docs`, etc.).

---

## 2. Architecture & Code Layout

```
etl/
├── fetch_download/         # API requests + file downloads (Stage 1: Fetch)
├── parsing/                # XML/HTML/PDF parsing (Stage 2: Parse)
├── load_*.py               # SQL loaders per document type (classes, not runnable scripts)
├── trajectories/           # QA + genealogy helpers
├── validate_etl.py         # Cross-step validation utilities
└── run_etl.py              # Stage 3: Load (calls load_*.py classes to insert parsed JSON into DB)
```

### Loader hierarchy (`db/etl/*.py`)
```
BaseLoader (abstract logger/stats helpers)
 ├── DocumentLoader
 │    ├── ResolutionLoader
 │    ├── DraftLoader
 │    ├── MeetingLoader (builds utterances + votes + procedural events)
 │    ├── CommitteeReportLoader
 │    └── AgendaLoader
 └── ActorLoader (normalizes names and caches IDs)
```

Key BaseLoader behaviors (see `db/etl/base_loader.py`):
- Validates JSON, logs per-file progress, and commits/rolls back per file to stay idempotent.
- Computes hashes + symbol extraction helpers to avoid duplicates.
- Emits structured stats (total/success/failed/skipped) and log files (`logs/etl_*.log`).

### Procedural Votes & Oral Amendments
As of Jan 2026, the pipeline supports **procedural votes** (e.g., motions for division, oral amendments).
- **Parser:** Extracts `procedural_events` from meeting text.
- **Schema:** Stored in `vote_events` table, linked to `votes` (where `document_id` is NULL).
- **Goal:** Enable tracking of failed amendments and complex voting maneuvers that don't result in a final resolution document.

### Actor normalization
`ActorLoader` loads cached actors from DB, applies normalization rules (e.g., *United States of America → United States*), and exposes `get_or_create_actor()` to other loaders. Aliases land in the JSONB metadata for future cleanup.

---

## 3. Runbook (Session 78 example)

The ETL pipeline has 3 **SEPARATE** stages that must be run independently:

### Stage 1: Fetch (Download from UN website)

```bash
# Fetch metadata XML
uv run python -m etl.fetch_download.fetch_metadata 78 --types resolutions drafts committee-reports meetings agenda

# Download HTML/PDF files
uv run python -m etl.fetch_download.download_metadata_html data/raw/xml/session_78_resolutions.xml
uv run python -m etl.fetch_download.download_pdfs data/parsed/metadata/session_78_resolutions.json
```

### Stage 2: Parse (Convert files to JSON)

```bash
# Parse metadata (XML/HTML → JSON)
uv run python -m etl.parsing.parse_metadata data/raw/xml/session_78_resolutions.xml
uv run python -m etl.parsing.parse_metadata_html data/documents/html/committee-reports/

# Parse PDFs (PDF → JSON)
# IMPORTANT: Use DIRECTORY mode to ensure output goes to data/parsed/
uv run python -m etl.parsing.parse_meeting_pdf data/documents/pdfs/meetings/
# Outputs to: data/parsed/pdfs/meetings/ (auto-detected)
```

### Stage 3: Load (JSON → PostgreSQL)

```bash
# Single command loads ALL parsed JSON files
uv run python -m etl.run_etl --reset

# Or load specific types only
uv run python -m etl.run_etl --resolutions-only
uv run python -m etl.run_etl --meetings-only
uv run python -m etl.run_etl --documents-only
```

**Note:** The individual loaders (load_documents.py, load_meetings.py, etc.) are classes, not runnable scripts. They are called by run_etl.py. Do not try to invoke them directly with `python -m`.

### Stage 4: Validate & QA

```bash
uv run python -m etl.trajectories.qa_trajectories -n 50 --seed 42
uv run python -m etl.validate_etl
```

---

## 4. Parser Output Locations

The parsers use auto-detection to determine where to write output JSON files:

### Directory mode (recommended)

When you pass a directory as input, the parser automatically transforms the path:

```bash
uv run python -m etl.parsing.parse_meeting_pdf data/documents/pdfs/meetings/
# Input:  data/documents/pdfs/meetings/
# Output: data/parsed/pdfs/meetings/ (auto-transforms 'documents' → 'parsed')
```

### Single file mode

When you pass a single PDF file, the parser writes the JSON to the **same directory** as the input file:

```bash
uv run python -m etl.parsing.parse_meeting_pdf data/documents/pdfs/meetings/A_78_PV.107.pdf
# Input:  data/documents/pdfs/meetings/A_78_PV.107.pdf
# Output: data/documents/pdfs/meetings/A_78_PV.107.json (same directory!)
```

### Important: Loader expectations

The loader (`run_etl.py`) **always reads from `data/parsed/`**, not `data/documents/`.

If you parse individual files in single-file mode, you must manually copy the JSON to the `data/parsed/` directory before loading:

```bash
# After single-file parse
cp data/documents/pdfs/meetings/A_78_PV.107.json data/parsed/pdfs/meetings/

# Then load
uv run python -m etl.run_etl --reset
```

### Override output location

You can explicitly specify the output directory with `-o`:

```bash
uv run python -m etl.parsing.parse_meeting_pdf data/documents/pdfs/meetings/A_78_PV.107.pdf \
  -o data/parsed/pdfs/meetings/
```

---

## 5. QA, Monitoring & Incident Notes

### Committee report incident (Jan 2026)
- **Symptom:** Only 20% (4/20) of trajectories had committee reports; 491 HTML files downloaded but only 111 parsed.
- **Fix:** Re-run `parse_metadata_html` over the entire committee-reports directory, then re-run loaders. Coverage jumped to 80% (16/20 trajectories complete). Remaining symbols missing entirely from fetch: `A/78/460`, `A/78/463/Add.1`, `A/78/922`, `A/78/429` – require targeted downloads via `etl.trajectories.fill_missing_documents`.

### Guardrails now baked in
- **File count parity:**
  ```python
  from pathlib import Path
  html = len(list(Path("data/documents/html/committee-reports").glob("*.html")))
  json = len(list(Path("data/parsed/html/committee-reports").glob("*.json")))
  assert html == json, f"Parsing incomplete: {html} HTML vs {json} JSON"
  ```
- **Trajectory QA:** `uv run python -m etl.trajectories.qa_trajectories -n 50 --seed 42` after every run; fails build if incomplete trajectories >10%.
- **Document-driven backfill:** `uv run python -m etl.trajectories.fill_missing_documents qa_results.json --download --parse` to grab referenced documents that weren’t caught by bulk queries.

### Validation checklist
1. `etl.validate_etl` ensures every downloaded file was parsed, and every parsed file loaded.
2. `scripts/seed_dev_db.py` + integration tests exercise genealogy traversal and multi-step tooling against the dev DB.
3. Logs: tail `logs/etl_*.log` for per-loader failures; `logs/multistep_tools.log` for downstream consumption health.

---

## 6. Known gaps & backlog
- Pagination support in `fetch_metadata.py` (currently manual when max hits reached).
- Sponsor extraction still happens in trajectory builders; move into dedicated DB tables (`sponsorships`) once parser stabilizes.
- Meeting PDF parser (`parse_committee_sr.py`) is new—monitor word counts + section parsing for regressions.
- Ensure we add the missing document columns highlighted in `docs/README_DATABASE.md` before we rely on them in downstream code.

---

## 7. References
- Implementation: `etl/`, `db/etl/`, `scripts/setup_db.py`
- Schema + downstream usage: `docs/README_DATABASE.md`, `docs/gym.md`, `docs/rag_enhancement_plan.md`
- Tests: `tests/etl_tests/`, `tests/integration/`

---

## Appendix: GA session scrape scope (summary of historical plan)

When targeting a single General Assembly session (e.g., 78th), enumerate artifacts systematically instead of guessing symbols. The Digital Library search endpoints support filters (`f[]=session:78`, `f[]=recordtype:Doc`) and wildcard symbol filters (`f[]=symbol:A/RES/78/*`). Recommended coverage order:

1. **Agenda + allocation:** fetch `A/78/251`, `A/78/251/Rev.1`, `A/78/252` directly by symbol. These anchor agenda items to committees/plenary.
2. **Draft resolutions/decisions:** query plenary drafts `A/78/L.*` and committee drafts `A/C.{1-6}/78/L.*` (include `Rev.`, `Add.`, `Corr.` versions). Search results include record IDs for follow-up downloads.
3. **Resolutions & decisions:** `f[]=symbol:A/RES/78/*` and `f[]=symbol:A/DEC/78/*`. Metadata often references committee reports, meetings, and draft symbols.
4. **Committee reports:** search by session + title (“Report of the Third Committee”) or use the references embedded in resolution metadata (`A/78/408`, `A/78/481/Add.3`, etc.).
5. **Meeting records:** combine plenary verbatim records `A/78/PV.*` and committee summary records `A/C.{1-6}/78/SR.*`. Resolution metadata and genealogy QA highlight the exact meeting codes you need.
6. **Voting data:** `recordtype:Vote` filtered by session or symbol. Use these when the resolution metadata lacks vote breakdowns.

Every download step should record counts (XML records fetched, HTML/PDF saved, JSON parsed) so `etl.validate_etl` can spot gaps immediately. The committee-report incident from January 2026 is a reminder: if a symbol appears in a resolution but not on disk, feed it into `etl.trajectories.fill_missing_documents` to backfill.
