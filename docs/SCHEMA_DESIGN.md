# Database Schema Design Document

**STATUS:** This is a design document with aspirational features. For the **actual implemented schema**, see `db/models.py` or `docs/README_DATABASE.md`.

**Implemented:** documents, actors, votes, document_relationships, utterances, utterance_documents
**Not Yet Implemented:** body_text_vector, sponsorships, agenda_items, committee_report_items, files

---

## Design Principles

1. **Normalize relationships, keep text flexible** - Use JSONB for metadata that varies by doc type
2. **Index for genealogy queries** - Fast forward/backward traversal
3. **Full-text search ready** - tsvector columns for text search
4. **Future-proof** - Easy to add columns without breaking existing code

---

## Core Tables

### 1. `documents`
**Purpose:** Core metadata for ALL document types

```sql
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    symbol TEXT UNIQUE NOT NULL,        -- e.g., "A/RES/78/220", "A/C.3/78/L.41"
    doc_type TEXT NOT NULL,             -- 'resolution', 'draft', 'meeting', 'committee_report', 'agenda'
    session INTEGER,                    -- e.g., 78
    committee INTEGER,                  -- e.g., 3 for Third Committee (NULL for plenary)
    record_id TEXT,                     -- UN Digital Library record ID

    -- Core metadata
    title TEXT,
    date DATE,
    action_note TEXT,                   -- Action date (often for resolutions)

    -- Flexible metadata (varies by doc type)
    metadata JSONB,                     -- Everything else: distribution, language, rapporteur, etc.

    -- Full text search (if document has body text)
    body_text TEXT,                     -- Full text of drafts, resolution text
    body_text_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', COALESCE(body_text, ''))) STORED,

    -- Tracking
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    source_file TEXT                    -- Original JSON file path
);

-- Indexes
CREATE INDEX idx_documents_symbol ON documents(symbol);
CREATE INDEX idx_documents_type ON documents(doc_type);
CREATE INDEX idx_documents_session ON documents(session);
CREATE INDEX idx_documents_committee ON documents(committee);
CREATE INDEX idx_documents_date ON documents(date);
CREATE INDEX idx_documents_metadata ON documents USING GIN(metadata);
CREATE INDEX idx_documents_body_fts ON documents USING GIN(body_text_vector);
```

**Why JSONB for metadata?**
- Resolutions have: voting, distribution, authors
- Drafts have: original_language, distribution
- Meetings have: president, chair, meeting_number
- Committee reports have: rapporteur, agenda_item

Storing in JSONB allows flexible schema without nullable columns.

---

### 2. `document_relationships`
**Purpose:** Genealogy edges (draft → resolution, agenda → draft, etc.)

```sql
CREATE TABLE document_relationships (
    id SERIAL PRIMARY KEY,
    source_symbol TEXT NOT NULL REFERENCES documents(symbol) ON DELETE CASCADE,
    target_symbol TEXT NOT NULL REFERENCES documents(symbol) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,    -- 'draft_of', 'committee_report_for', 'meeting_for', 'agenda_item'

    -- Optional metadata about relationship
    metadata JSONB,                     -- e.g., which paragraph references this

    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(source_symbol, target_symbol, relationship_type)
);

-- Indexes for fast bidirectional traversal
CREATE INDEX idx_rel_source ON document_relationships(source_symbol);
CREATE INDEX idx_rel_target ON document_relationships(target_symbol);
CREATE INDEX idx_rel_type ON document_relationships(relationship_type);
CREATE INDEX idx_rel_source_type ON document_relationships(source_symbol, relationship_type);
CREATE INDEX idx_rel_target_type ON document_relationships(target_symbol, relationship_type);
```

**Relationship types:**
- `draft_of` - Draft → Resolution
- `committee_report_for` - Committee Report → Resolution
- `meeting_for` - Meeting → Resolution
- `agenda_item` - Agenda → Document
- `revision_of` - L.41/Rev.1 → L.41
- `references` - Generic reference

---

### 3. `actors`
**Purpose:** Countries, speakers, organizations

```sql
CREATE TABLE actors (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,                 -- Original name from document
    normalized_name TEXT NOT NULL,      -- Standardized name for matching
    actor_type TEXT NOT NULL,           -- 'country', 'observer', 'un_official', 'ngo'

    -- Aliases for fuzzy matching
    aliases TEXT[],                     -- ['United States', 'USA', 'United States of America']

    metadata JSONB,                     -- Additional info (ISO code, region, etc.)

    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(normalized_name, actor_type)
);

CREATE INDEX idx_actors_normalized ON actors(normalized_name);
CREATE INDEX idx_actors_type ON actors(actor_type);
CREATE INDEX idx_actors_aliases ON actors USING GIN(aliases);
```

**Actor normalization examples:**
- "United States of America" → "United States"
- "Republic of Korea" → "South Korea"
- "Bolivarian Republic of Venezuela" → "Venezuela"

---

### 4. `votes`
**Purpose:** How actors voted on documents

```sql
CREATE TABLE votes (
    id SERIAL PRIMARY KEY,
    document_symbol TEXT NOT NULL REFERENCES documents(symbol) ON DELETE CASCADE,
    vote_context TEXT NOT NULL,         -- 'committee', 'plenary'
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    vote_choice TEXT NOT NULL,          -- 'in_favour', 'against', 'abstaining', 'absent'

    -- Optional: vote details
    metadata JSONB,                     -- Explanation of vote, etc.

    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(document_symbol, vote_context, actor_id)
);

CREATE INDEX idx_votes_document ON votes(document_symbol);
CREATE INDEX idx_votes_actor ON votes(actor_id);
CREATE INDEX idx_votes_context ON votes(vote_context);
CREATE INDEX idx_votes_choice ON votes(vote_choice);
```

---

### 5. `utterances`
**Purpose:** Statements made in meetings

```sql
CREATE TABLE utterances (
    id SERIAL PRIMARY KEY,
    meeting_symbol TEXT NOT NULL REFERENCES documents(symbol) ON DELETE CASCADE,
    speaker_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,  -- Can be null if speaker unknown
    speaker_role TEXT,                  -- 'President', 'The Acting President', 'delegate'
    speaker_raw TEXT,                   -- Original speaker string from PDF

    text TEXT NOT NULL,
    word_count INTEGER,
    position_in_meeting INTEGER,        -- Order within meeting

    -- Full text search
    text_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,

    -- Metadata
    metadata JSONB,                     -- Resolution metadata if utterance announces vote, etc.

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_utterances_meeting ON utterances(meeting_symbol);
CREATE INDEX idx_utterances_speaker ON utterances(speaker_actor_id);
CREATE INDEX idx_utterances_position ON utterances(meeting_symbol, position_in_meeting);
CREATE INDEX idx_utterances_fts ON utterances USING GIN(text_vector);
```

---

### 6. `sponsorships`
**Purpose:** Which actors sponsored which drafts/resolutions

```sql
CREATE TABLE sponsorships (
    id SERIAL PRIMARY KEY,
    document_symbol TEXT NOT NULL REFERENCES documents(symbol) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    sponsor_type TEXT NOT NULL,         -- 'primary', 'co-sponsor'

    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(document_symbol, actor_id)
);

CREATE INDEX idx_sponsorships_document ON sponsorships(document_symbol);
CREATE INDEX idx_sponsorships_actor ON sponsorships(actor_id);
CREATE INDEX idx_sponsorships_type ON sponsorships(sponsor_type);
```

---

### 7. `agenda_items`
**Purpose:** Agenda item details (can also query via documents table)

```sql
CREATE TABLE agenda_items (
    id SERIAL PRIMARY KEY,
    document_symbol TEXT NOT NULL REFERENCES documents(symbol) ON DELETE CASCADE,
    item_number INTEGER,
    sub_item TEXT,                      -- 'a', 'b', 'c'

    -- Full item reference
    item_full TEXT GENERATED ALWAYS AS (
        CASE
            WHEN sub_item IS NOT NULL THEN item_number::TEXT || sub_item
            ELSE item_number::TEXT
        END
    ) STORED,

    subjects TEXT[],                    -- Subject tags

    UNIQUE(document_symbol)
);

CREATE INDEX idx_agenda_items_number ON agenda_items(item_number);
CREATE INDEX idx_agenda_items_full ON agenda_items(item_full);
```

---

### 8. `committee_report_items`
**Purpose:** Individual draft items within committee reports

```sql
CREATE TABLE committee_report_items (
    id SERIAL PRIMARY KEY,
    report_symbol TEXT NOT NULL REFERENCES documents(symbol) ON DELETE CASCADE,
    section_letter TEXT,                -- 'A', 'B', 'C'
    draft_symbol TEXT,                  -- Draft this item is about

    title TEXT,
    adoption_status TEXT,               -- 'adopted', 'rejected'
    vote_info TEXT,                     -- Human-readable vote summary

    -- Vote details stored here OR in votes table (decide based on query patterns)

    metadata JSONB,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_committee_items_report ON committee_report_items(report_symbol);
CREATE INDEX idx_committee_items_draft ON committee_report_items(draft_symbol);
```

---

### 9. `files`
**Purpose:** Track PDF/HTML files associated with documents

```sql
CREATE TABLE files (
    id SERIAL PRIMARY KEY,
    document_symbol TEXT NOT NULL REFERENCES documents(symbol) ON DELETE CASCADE,
    language TEXT NOT NULL,             -- 'English', 'Español', 'Français', etc.
    file_type TEXT NOT NULL,            -- 'pdf', 'html'
    filename TEXT,
    url TEXT,
    local_path TEXT,                    -- Path to downloaded file

    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(document_symbol, language, file_type)
);

CREATE INDEX idx_files_document ON files(document_symbol);
CREATE INDEX idx_files_language ON files(language);
```

---

## Materialized Views (Optional - for performance)

### Meeting statistics
```sql
CREATE MATERIALIZED VIEW meeting_stats AS
SELECT
    meeting_symbol,
    COUNT(*) as total_utterances,
    SUM(word_count) as total_words,
    COUNT(DISTINCT speaker_actor_id) as unique_speakers
FROM utterances
GROUP BY meeting_symbol;

CREATE INDEX ON meeting_stats(meeting_symbol);
```

### Vote summaries
```sql
CREATE MATERIALIZED VIEW vote_summaries AS
SELECT
    document_symbol,
    vote_context,
    COUNT(*) FILTER (WHERE vote_choice = 'in_favour') as yes_count,
    COUNT(*) FILTER (WHERE vote_choice = 'against') as no_count,
    COUNT(*) FILTER (WHERE vote_choice = 'abstaining') as abstain_count,
    ARRAY_AGG(a.normalized_name) FILTER (WHERE vote_choice = 'in_favour') as yes_countries,
    ARRAY_AGG(a.normalized_name) FILTER (WHERE vote_choice = 'against') as no_countries
FROM votes v
JOIN actors a ON v.actor_id = a.id
GROUP BY document_symbol, vote_context;

CREATE INDEX ON vote_summaries(document_symbol);
```

---

## Sample Queries

### Trace resolution backward
```sql
WITH RECURSIVE genealogy AS (
    -- Start with resolution
    SELECT symbol, doc_type, title, 0 as depth
    FROM documents
    WHERE symbol = 'A/RES/78/220'

    UNION ALL

    -- Follow relationships backward
    SELECT d.symbol, d.doc_type, d.title, g.depth + 1
    FROM genealogy g
    JOIN document_relationships dr ON dr.target_symbol = g.symbol
    JOIN documents d ON d.symbol = dr.source_symbol
)
SELECT * FROM genealogy ORDER BY depth;
```

### All statements by USA
```sql
SELECT
    d.symbol,
    d.title,
    d.date,
    u.text,
    u.word_count
FROM utterances u
JOIN actors a ON u.speaker_actor_id = a.id
JOIN documents d ON u.meeting_symbol = d.symbol
WHERE a.normalized_name = 'United States'
ORDER BY d.date;
```

### Vote switchers (committee → plenary)
```sql
SELECT
    a.normalized_name,
    v_committee.vote_choice as committee_vote,
    v_plenary.vote_choice as plenary_vote,
    d.symbol,
    d.title
FROM votes v_committee
JOIN votes v_plenary
    ON v_committee.actor_id = v_plenary.actor_id
    AND v_committee.document_symbol = v_plenary.document_symbol
JOIN actors a ON a.id = v_committee.actor_id
JOIN documents d ON d.symbol = v_committee.document_symbol
WHERE v_committee.vote_context = 'committee'
  AND v_plenary.vote_context = 'plenary'
  AND v_committee.vote_choice != v_plenary.vote_choice;
```

---

## Data Type Decisions

### Why TEXT instead of VARCHAR?
- PostgreSQL treats them identically performance-wise
- TEXT is more flexible (no length limits)
- Easier to migrate schema

### Why JSONB instead of JSON?
- Binary format = faster queries
- Supports indexing with GIN
- Can query nested fields efficiently

### Why generated columns for tsvector?
- Automatically updated on text changes
- No need for triggers
- Always in sync with source text

---

## Migration Strategy

Since JSON format is subject to change:

1. **Version the schema**: `schema_v1.sql`, `schema_v2.sql`
2. **Migration scripts**: `migrations/001_initial.sql`, `002_add_field.sql`
3. **ETL versioning**: ETL scripts check schema version
4. **Backward compatibility**: Old JSONs can still load (missing fields → NULL)

---

## Size Estimates

For session 78:
- ~330 resolutions
- ~500 drafts
- ~150 committee reports
- ~100 meetings
- ~10,000 utterances
- ~50,000 votes

**Estimated DB size: ~500 MB - 1 GB** (including indexes)

---

## Next Steps

1. Review schema with stakeholder
2. Create `schema.sql` from this design
3. Test schema creation on dev database
4. Iterate based on ETL implementation needs
