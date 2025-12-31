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

This creates 4 tables:
- `documents` - All UN documents (resolutions, drafts, etc.)
- `actors` - Countries and organizations
- `votes` - Voting records (plenary and committee)
- `document_relationships` - Links between documents

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
DATA_ROOT=/Users/theolebryk/projects/un_draft/data
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
