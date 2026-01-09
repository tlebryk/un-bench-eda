# UN Documents Database - Quick Win MVP

This database provides structured access to UN General Assembly resolutions with voting records and document relationships.

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

This installs:
- SQLAlchemy (database ORM)
- psycopg2-binary (PostgreSQL driver)
- python-dotenv (configuration)

### 2. Start PostgreSQL

```bash
docker-compose up -d
```

Verify it's running:
```bash
docker ps  # Should show un_documents_db
```

### 3. Create Database Schema

```bash
uv run python scripts/setup_db.py
```

This creates the SQLAlchemy models defined in `db/models.py`:
- `documents` - All UN documents (resolutions, drafts, meetings, agenda, etc.)
- `document_relationships` - Links between documents
- `actors` - Countries, observers, UN officials
- `votes` - Committee + plenary roll-call records
- `utterances` - Parsed statements from meetings
- `utterance_documents` - Junction table linking utterances to the documents they mention

### 4. Load Data

```bash
uv run python -m etl.run_etl --reset
```

This loads:
- 336 resolutions from session 78
- 110 plenary meetings
- 282 actors (countries and observers)
- 13,600+ individual vote records extracted from meetings
- Document relationships (drafts → resolutions)

**Expected output:**
```
============================================================
UN Documents ETL - Quick Win MVP
============================================================

📊 Loading Resolutions...
Found 336 resolution files
✅ Committed all changes

==================================================
Loaded:  336
Skipped: 0
Errors:  0
==================================================

📊 Loading Meetings and Votes...
Found 110 meeting files
  A/78/PV.50: Extracted 2364 votes
  A/78/PV.42: Extracted 5227 votes
  ...
✅ Committed all changes

==================================================
Loaded:  16
Skipped: 94
Errors:  0
==================================================

✅ ETL Complete!
```

### 5. Validate Data

```bash
uv run python scripts/validate_db.py
```

### 6. Run Sample Queries

```bash
uv run python scripts/sample_queries.py
```

### 7. Launch the SQL UI

```bash
uv run uvicorn ui.app:app --reload
```

Open http://127.0.0.1:8000/ to get a text box that executes read-only SQL (`SELECT`, `WITH`, `EXPLAIN`). The UI shows up to 500 rows per query and collapses long text blocks so you can expand them on demand. (If you loaded data before this UI existed, rerun `uv run python -m etl.run_etl --resolutions-only` so agenda, committee, and meeting relationships are stored.) Useful commands:

- `SELECT symbol, title FROM documents WHERE doc_type = 'resolution' ORDER BY date DESC LIMIT 10;`
- `SELECT vote_type, COUNT(*) FROM votes JOIN documents ON votes.document_id = documents.id WHERE documents.symbol = 'A/RES/78/220' GROUP BY vote_type;`
- `SELECT source_id, target_id, relationship_type FROM document_relationships LIMIT 10;`
- ```sql
  WITH target_resolution AS (
      SELECT id, symbol, title
      FROM documents
      WHERE symbol = 'A/RES/78/220'
  )
  SELECT 'resolution' AS link_type, doc.doc_type, doc.symbol, doc.title
  FROM target_resolution tr
  JOIN documents doc ON doc.id = tr.id
  UNION ALL
  SELECT rel.relationship_type, src.doc_type, src.symbol,
         COALESCE(src.title, src.doc_metadata->'metadata'->>'title') AS title
  FROM target_resolution tr
  JOIN document_relationships rel ON rel.target_id = tr.id
  JOIN documents src ON src.id = rel.source_id;
  ```

If you need the raw JSON output, POST the same SQL to `/api/query`.

### 8. Text-to-SQL Feature

The SQL UI now includes a text-to-SQL feature powered by OpenAI. You can ask questions in natural language and it will generate SQL queries for you.

**Setup:**
1. Create a `.env` file in the project root (if it doesn't exist)
2. Add your OpenAI API key:
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   DATABASE_URL=postgresql://un_user:un_password@localhost:5433/un_documents
   ```
3. The app uses `gpt-5-mini-2025-08-07` by default (cheap and fast). You can change this in `text_to_sql.py`.

**Usage:**
- In the SQL UI (http://127.0.0.1:8000), use the "Ask in Natural Language" section at the top
- Type questions like:
  - "Show me all resolutions where USA voted against"
  - "Find all documents from session 78"
  - "What did Libya say about resolution A/RES/78/220?"
- Click "Generate SQL" to see the SQL, or "Generate & Run" to execute it immediately

**API Endpoint:**
```bash
# Generate SQL only
curl -X POST http://localhost:8000/api/text-to-sql \
  -F "natural_language_query=Show me all resolutions where USA voted against" \
  -F "execute=false"

# Generate and execute SQL
curl -X POST http://localhost:8000/api/text-to-sql \
  -F "natural_language_query=Show me all resolutions where USA voted against" \
  -F "execute=true"
```

**Command Line:**
```bash
uv run text_to_sql.py "Show me all resolutions where USA voted against"
```

---

## Schema Snapshot (January 2026)

`db/models.py` is the source of truth for the database. `scripts/setup_db.py` builds the six tables listed below, and the schema mirrors the structures used by the RAG + multi-step agents.

### Table overview
- **documents** – canonical record for every artifact (resolutions, drafts, committee reports, meetings, agenda, decisions). Stores normalized fields plus a JSONB `doc_metadata` blob for source-specific attributes.
- **document_relationships** – directional edges such as `draft_of`, `committee_report_for`, `meeting_for`, `agenda_item` that power genealogy traversal.
- **actors** – normalized participants (countries, observers, UN officials) so we can join votes + utterances.
- **votes** – roll-call data from committee/plenary stages; keyed to both `documents` and `actors`.
- **utterances** – parsed statements from plenary meetings and committee summary records with speaker metadata.
- **utterance_documents** – many-to-many helper that ties utterances to the specific drafts/resolutions they reference (`reference_type='voting_on'`, `mentioned`, etc.).
- **subjects** – Controlled vocabulary of document topics.
- **document_subjects** – Many-to-many link between documents and subjects.
- **sponsorships** – Tracks which actors sponsored a document (initial vs. additional).

### Current implementation status
- **Fully implemented:** the six tables above, including cascading relationships and helper methods exposed in `db/models.py`.
- **Partially implemented:**
  - `documents` is missing a few optional columns from the earlier design (`committee`, `record_id`, `action_note`, `body_text_vector`, `updated_at`, `source_file`), but the JSONB metadata keeps the data accessible.
  - `actors` only stores `name` + `actor_type`; alias handling / normalized names are still TODO.
  - Full-text search columns (`body_text_vector`) and associated GIN indexes are not created yet.
  - `document_relationships` lacks a uniqueness constraint on `(source_id, target_id, relationship_type)`—watch for duplicates in ETL jobs.
- **Not yet implemented tables:** `sponsorships`, `agenda_items`, `committee_report_items`, and `files`. Sponsors currently live inside trajectory JSON; agenda tables are inferred through relationships.

### Foreign key + traversal strategy
- All relationships use integer IDs, not symbols. This matches the SQLAlchemy models and dramatically simplifies joins in scripts like `rag/multistep/tools.py`.
- Recursive traversal (for genealogy queries) happens via SQL CTEs that fan out from `documents.id` through `document_relationships`. See the `execute_get_related_documents` helper for the canonical query pattern.

### Backlog / next improvements
- Add the missing document columns noted above plus updated timestamps.
- Introduce dedicated `sponsorships` + `agenda_items` tables once extraction scripts land.
- Build materialized views or helper SQL to expose JSONB fields that the UI/RAG layers query frequently.
- Add GIN indexes for `doc_metadata` and future `body_text_vector` columns to support full-text search.
- Stand up an `actor_aliases` helper table to normalize spelling variants in votes/utterances.

### Meeting utterances pipeline (now folded into schema)
- **Sources:** Plenary verbatim records (`A/78/PV.*`) parsed by `etl/parsing/parse_meeting_pdf.py` and committee summary records (`A/C.*/78/SR.*`) parsed by `etl/parsing/parse_committee_sr.py`.
- **Loader:** `etl/load_meetings.py` persists the meeting document itself, each utterance row (speaker metadata, section, agenda item, word counts), related votes, and the `utterance_documents` junction entries tying statements back to drafts/resolutions/agenda items.
- **Why JSONB metadata?** Voting information or resolution references can show up inline (“draft resolution A/C.3/78/L.41 as orally revised ...”); parsers capture those snippets in `utterance_metadata` so downstream RAG or UI layers can surface context without re-parsing PDF text.
- **Genealogy traversal:** `execute_get_related_documents()` (used by the multi-step tooling) starts from a resolution symbol, traverses `document_relationships`, and hands the resulting meeting symbols to `execute_get_utterances()` so we can assemble “resolution → meeting → utterance” chains.

#### Practical queries
```sql
-- All statements about a specific resolution
SELECT u.speaker_name,
       u.speaker_affiliation,
       u.agenda_item_number,
       u.text,
       m.symbol AS meeting_symbol,
       m.date AS meeting_date
FROM utterances u
JOIN utterance_documents ud ON ud.utterance_id = u.id
JOIN documents d ON d.id = ud.document_id
JOIN documents m ON m.id = u.meeting_id
WHERE d.symbol = 'A/RES/78/281'
ORDER BY m.date, u.position_in_meeting;

-- Trace utterances from a draft backwards through agenda items
WITH resolution_tree AS (
    SELECT id FROM documents WHERE symbol = 'A/C.3/78/L.41'
    UNION
    SELECT d.id
    FROM documents d
    JOIN document_relationships dr ON dr.target_id = d.id OR dr.source_id = d.id
    JOIN resolution_tree rt ON (dr.target_id = rt.id OR dr.source_id = rt.id)
)
SELECT u.id, u.speaker_affiliation, LEFT(u.text, 200) AS excerpt,
       d.symbol AS referenced_document, m.symbol AS meeting_symbol
FROM utterances u
JOIN utterance_documents ud ON ud.utterance_id = u.id
JOIN documents d ON d.id = ud.document_id
JOIN documents m ON m.id = u.meeting_id
WHERE ud.document_id IN (SELECT id FROM resolution_tree)
ORDER BY m.date, u.position_in_meeting;
```

Use these patterns in RAG, UI, or trajectory QA to pull precise statements (e.g., voting utterances labeled `reference_type='voting_on'`).

---

## Database Schema

### documents

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| symbol | string | UN document symbol (e.g., A/RES/78/220) |
| doc_type | string | resolution, draft, meeting, etc. |
| session | integer | Session number (e.g., 78) |
| title | text | Document title |
| date | date | Document date |
| body_text | text | Full text from PDF (resolutions, drafts) |
| doc_metadata | jsonb | Full JSON for flexibility |
| created_at | timestamp | Creation timestamp |

### actors

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| name | string | Country or organization name |
| actor_type | string | country, observer, un_official |
| created_at | timestamp | Creation timestamp |

### votes

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| document_id | integer | Foreign key to documents |
| actor_id | integer | Foreign key to actors |
| vote_type | string | in_favour, against, abstaining |
| vote_context | string | plenary, committee |
| created_at | timestamp | Creation timestamp |

### document_relationships

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| source_id | integer | Source document (e.g., draft) |
| target_id | integer | Target document (e.g., resolution) |
| relationship_type | string | draft_of, committee_report_for, etc. |
| rel_metadata | jsonb | Additional relationship metadata |
| created_at | timestamp | Creation timestamp |

### utterances

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| meeting_id | integer | Foreign key to documents (meeting) |
| section_id | string | Section identifier within meeting |
| agenda_item_number | string | Agenda item being discussed |
| speaker_actor_id | integer | Foreign key to actors (nullable) |
| speaker_name | string | Speaker name parsed from PDF |
| speaker_role | string | Role (e.g., "President", "delegate") |
| speaker_raw | text | Original speaker string from PDF |
| speaker_affiliation | string | Country or organization |
| text | text | Full utterance text |
| word_count | integer | Word count of utterance |
| position_in_meeting | integer | Order within meeting |
| position_in_section | integer | Order within section |
| utterance_metadata | jsonb | Additional metadata |
| created_at | timestamp | Creation timestamp |

### utterance_documents

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| utterance_id | integer | Foreign key to utterances |
| document_id | integer | Foreign key to documents |
| reference_type | string | Type of reference (mentioned, voting_on, etc.) |
| context | text | Context where document was mentioned |
| created_at | timestamp | Creation timestamp |

### subjects

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| name | string | Subject name (unique) |

### document_subjects

| Column | Type | Description |
|--------|------|-------------|
| document_id | integer | Foreign key to documents |
| subject_id | integer | Foreign key to subjects |

### sponsorships

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| document_id | integer | Foreign key to documents |
| actor_id | integer | Foreign key to actors |
| sponsorship_type | string | initial, additional |
| created_at | timestamp | Creation timestamp |

---

## Example Queries

### Python (SQLAlchemy)

```python
from db.config import get_session
from db.models import Document, Actor, Vote

session = get_session()

# How did USA vote on A/RES/78/220?
result = session.query(
    Document.symbol,
    Vote.vote_type
).join(Vote).join(Actor).filter(
    Document.symbol == 'A/RES/78/220',
    Actor.name.ilike('%united states%')
).first()

print(f"{result.symbol}: {result.vote_type}")
```

### Raw SQL

```bash
# Connect to database
docker exec -it un_documents_db psql -U un_user -d un_documents

# Example queries
SELECT symbol, title FROM documents WHERE doc_type = 'resolution' LIMIT 10;

SELECT a.name, COUNT(*) as vote_count
FROM votes v
JOIN actors a ON v.actor_id = a.id
GROUP BY a.id
ORDER BY vote_count DESC
LIMIT 10;

SELECT
    d.symbol,
    v.vote_type,
    a.name
FROM documents d
JOIN votes v ON v.document_id = d.id
JOIN actors a ON a.id = v.actor_id
WHERE d.symbol = 'A/RES/78/220'
LIMIT 10;
```

---

## Common Tasks

### Sync Local Database to Supabase (Recommended)

**Much faster than running ETL over network!**

```bash
# 1. Ensure local database is up to date
docker-compose up -d
uv run -m etl.run_etl --reset  # (or just --resolutions-only if already loaded)

# 2. Sync to Supabase (~1-2 minutes)
./scripts/sync_to_supabase.sh

# 3. Verify
uv run -m scripts.verify_supabase
```

**What it does:**
- Exports local PostgreSQL database to SQL dump
- Imports dump to Supabase
- Much faster than ETL (2 minutes vs 30+ minutes)

**Manual method:**
```bash
# Export local database
docker exec un_documents_db pg_dump -U un_user -d un_documents \
    --clean --if-exists > /tmp/un_documents.sql

# Import to Supabase (replace with your credentials)
PGPASSWORD=your_password psql \
    -h db.xyz.supabase.co \
    -p 5432 \
    -U postgres \
    -d postgres \
    -f /tmp/un_documents.sql
```

### Reset Database

To drop all tables and reload data:

```bash
uv run python -m etl.run_etl --reset
```

### Query Database Directly

```bash
docker exec -it un_documents_db psql -U un_user -d un_documents
```

### Stop Database

```bash
docker-compose down
```

### View Logs

```bash
docker-compose logs -f postgres
```

---

## File Structure

```
un_draft/
├── docker-compose.yml          # PostgreSQL container
├── .env                         # Database connection config
├── db/
│   ├── __init__.py
│   ├── config.py               # Database connection
│   ├── models.py               # SQLAlchemy models
│   └── utils.py                # Database utilities
├── etl/
│   ├── __init__.py
│   ├── base.py                 # Base loader class
│   ├── load_resolutions.py    # Resolution loader
│   ├── load_meetings.py        # Meeting loader (extracts votes)
│   └── run_etl.py              # Master ETL script
└── scripts/
    ├── setup_db.py             # Initialize schema
    ├── validate_db.py          # Validation checks
    └── sample_queries.py       # Example queries
```

---

## Troubleshooting

### "No module named 'db'"

Make sure you're in the project root directory:
```bash
cd /Users/theolebryk/projects/un_draft
```

### "could not connect to server"

Start PostgreSQL:
```bash
docker-compose up -d
```

### "relation does not exist"

Create tables:
```bash
uv run python scripts/setup_db.py
```

### "Empty database"

Load data:
```bash
uv run python -m etl.run_etl --reset
```

---

## Next Steps

After the MVP is working, you can expand to:

1. **Load drafts with full text** - Enable text search on draft language
2. **Load meetings with utterances** - Enable speaker statement queries
3. **Load committee reports** - Track committee vs plenary voting differences
4. **Add full-text search** - Search across all documents
5. **Build Streamlit UI** - Visual query interface

---

## Configuration

Edit `.env` to change database connection:

```
DATABASE_URL=postgresql://un_user:un_password@localhost:5432/un_documents
APP_DATABASE_URL=postgresql://un_app_user:password@localhost:5432/un_documents
DATA_ROOT=/Users/theolebryk/projects/un_draft/data
```

---

## Database Security (Read-Only User)

For production deployments, use separate database credentials for queries vs. setup/migrations. This implements defense-in-depth security.

### Setup Read-Only User

```bash
# Run the setup script (requires admin DATABASE_URL)
uv run python db/setup_readonly_user.py

# Or manually run the SQL file
psql $DATABASE_URL -f db/setup_readonly_user.sql
```

This creates:
- `un_app_readonly` role with SELECT-only permissions
- `un_app_user` with the read-only role assigned

### Configure Application

Add to `.env`:
```
# Admin user (for setup_db.py and migrations)
DATABASE_URL=postgresql://un_user:admin_password@localhost:5432/un_documents

# Read-only user (for application queries)
APP_DATABASE_URL=postgresql://un_app_user:readonly_password@localhost:5432/un_documents
```

The application will automatically use `APP_DATABASE_URL` for queries, providing:
- Protection against accidental writes
- Protection against SQL injection leading to data modification
- Compliance with principle of least privilege

### Using in Code

```python
from db.config import get_session, get_admin_session

# Read-only session (uses APP_DATABASE_URL if set)
session = get_session()
results = session.query(Document).all()  # ✅ Works

# Admin session (uses DATABASE_URL, for setup only)
admin_session = get_admin_session()
new_doc = Document(symbol='A/RES/78/220')
admin_session.add(new_doc)  # ✅ Works (admin has write permissions)
admin_session.commit()
```

### Validation Layers

The system provides multiple layers of validation:

1. **Application-level** (text_to_sql.py): Blocks INSERT/UPDATE/DELETE/DROP keywords
2. **Database-level**: Read-only user can only SELECT
3. **Connection-level**: Separate credentials for queries vs. setup

### Testing Read-Only Permissions

```bash
# Should work (SELECT)
psql $APP_DATABASE_URL -c "SELECT COUNT(*) FROM documents;"

# Should fail (INSERT)
psql $APP_DATABASE_URL -c "INSERT INTO documents (symbol) VALUES ('test');"
# Error: permission denied for table documents
```

---

## Performance

Current database statistics (session 78 only):
- Documents: 336 resolutions + 16 meetings
- Actors: 282 countries and observers
- Votes: 13,600+ individual records
- Relationships: 311 draft→resolution links
- Database size: ~15 MB
- Load time: ~45 seconds
- Query time: <100ms for simple queries
