# Meeting Utterances Database Design

## Overview

This document describes how meeting utterances (speeches/statements) are stored in the database and how to trace genealogy from any document identifier (resolution, draft, agenda item) to find all relevant comments.

This covers both:
1. **Plenary Meetings** (`A/78/PV.*`) - Verbatim records of the General Assembly.
2. **Committee Summary Records** (`A/C.*/78/SR.*`) - Summarized records of the Main Committees.

## Database Schema

### New Tables

#### `utterances`
Stores individual speech utterances from plenary meetings and committee summary records.

**Key Fields:**
- `meeting_id` - Links to the meeting document
- `section_id` - Tracks which agenda item section (e.g., "A/78/PV.80_section_11")
- `agenda_item_number` - The agenda item number (e.g., "11", "20")
- `speaker_name` - Parsed speaker name (e.g., "El-Sonni")
- `speaker_affiliation` - Country or organization (e.g., "Libya")
- `speaker_role` - Role (e.g., "The President", "delegate", "Chair")
- `text` - Full text of the utterance
- `position_in_meeting` - Order within the entire meeting
- `position_in_section` - Order within the agenda item section
- `utterance_metadata` - JSONB field for resolution metadata, vote details, etc.

#### `utterance_documents`
Junction table linking utterances to documents they reference.

**Key Fields:**
- `utterance_id` - Links to the utterance
- `document_id` - Links to the referenced document (draft, resolution, etc.)
- `reference_type` - Type of reference ("mentioned", "voting_on", etc.)
- `context` - The sentence/context where the document was mentioned

## Data Flow

### 1. Parsing
Two parsers handle different meeting formats:
- `parse_meeting_pdf.py`: Handles Plenary Verbatim Records (PV).
- `parse_committee_sr.py`: Handles Committee Summary Records (SR).

The parsers extract:
- Meeting metadata (symbol, date, session, etc.)
- Sections organized by agenda items
- Utterances with speaker information
- Document references in each utterance
- Resolution metadata (when voting occurs)

### 2. ETL (etl/load_meetings.py)
The meeting loader:
1. Creates/updates the meeting document
2. Extracts each utterance with speaker information
3. Links utterances to documents they reference (via `utterance_documents`)
4. Extracts vote records from utterances that contain voting information

### 3. Storage
- Each utterance is stored with full text and speaker information
- Document references are stored in the junction table
- This enables bidirectional queries:
  - From utterance → find all referenced documents
  - From document → find all utterances that mention it

## Genealogy Tracing

### From Resolution Number
```sql
-- Find all utterances about a specific resolution
SELECT 
    u.id,
    u.speaker_name,
    u.speaker_affiliation,
    u.agenda_item_number,
    u.text,
    m.symbol as meeting_symbol,
    m.date as meeting_date
FROM utterances u
JOIN utterance_documents ud ON ud.utterance_id = u.id
JOIN documents d ON d.id = ud.document_id
JOIN documents m ON m.id = u.meeting_id
WHERE d.symbol = 'A/RES/78/281'
ORDER BY m.date, u.position_in_meeting;
```

### From Draft Number
```sql
-- Find all utterances about a specific draft
SELECT 
    u.id,
    u.speaker_name,
    u.speaker_affiliation,
    u.agenda_item_number,
    u.text,
    m.symbol as meeting_symbol
FROM utterances u
JOIN utterance_documents ud ON ud.utterance_id = u.id
JOIN documents d ON d.id = ud.document_id
JOIN documents m ON m.id = u.meeting_id
WHERE d.symbol = 'A/78/L.56'
ORDER BY u.position_in_meeting;
```

### From Agenda Item
```sql
-- Find all utterances in a specific agenda item
SELECT 
    u.id,
    u.speaker_name,
    u.speaker_affiliation,
    u.text,
    m.symbol as meeting_symbol,
    m.date as meeting_date
FROM utterances u
JOIN documents m ON m.id = u.meeting_id
WHERE u.agenda_item_number = '11'
ORDER BY m.date, u.position_in_meeting;
```

### Complete Genealogy Trace
```sql
-- Trace from resolution back through drafts to all related utterances
WITH resolution_tree AS (
    -- Start with the resolution
    SELECT id, symbol, doc_type
    FROM documents
    WHERE symbol = 'A/RES/78/281'
    
    UNION
    
    -- Find all related documents (drafts, etc.)
    SELECT d.id, d.symbol, d.doc_type
    FROM documents d
    JOIN document_relationships dr ON dr.target_id = d.id
    JOIN resolution_tree rt ON rt.id = dr.source_id
)
SELECT 
    u.id,
    u.speaker_name,
    u.speaker_affiliation,
    u.agenda_item_number,
    LEFT(u.text, 200) as text_preview,
    d.symbol as referenced_document,
    m.symbol as meeting_symbol,
    m.date as meeting_date
FROM utterances u
JOIN utterance_documents ud ON ud.utterance_id = u.id
JOIN resolution_tree rt ON rt.id = ud.document_id
JOIN documents d ON d.id = ud.document_id
JOIN documents m ON m.id = u.meeting_id
ORDER BY m.date, u.position_in_meeting;
```

## Usage Examples

### Setup
```bash
# 1. Create database schema (includes new tables)
uv run python scripts/setup_db.py

# 2. Load meetings with utterances
uv run python -m etl.run_etl --meetings-only

# 3. Test with specific meeting
uv run python test_meeting_etl.py
```

### Query Examples

#### Find who said what about a resolution
```sql
SELECT 
    u.speaker_name,
    u.speaker_affiliation,
    u.text
FROM utterances u
JOIN utterance_documents ud ON ud.utterance_id = u.id
JOIN documents d ON d.id = ud.document_id
WHERE d.symbol = 'A/RES/78/281'
ORDER BY u.position_in_meeting;
```

#### Find all statements by a specific country
```sql
SELECT 
    u.text,
    m.symbol as meeting_symbol,
    u.agenda_item_number
FROM utterances u
JOIN documents m ON m.id = u.meeting_id
WHERE u.speaker_affiliation = 'Libya'
ORDER BY m.date, u.position_in_meeting;
```

#### Find utterances that mention multiple documents
```sql
SELECT 
    u.id,
    u.speaker_name,
    u.text,
    ARRAY_AGG(d.symbol) as referenced_documents
FROM utterances u
JOIN utterance_documents ud ON ud.utterance_id = u.id
JOIN documents d ON d.id = ud.document_id
GROUP BY u.id, u.speaker_name, u.text
HAVING COUNT(DISTINCT d.id) > 1
ORDER BY u.id;
```

## FastAPI UI Integration

The FastAPI UI (`ui/app.py`) can now query utterances. Example queries:

```sql
-- Find all utterances about resolution 78/281
SELECT 
    u.speaker_name,
    u.speaker_affiliation,
    u.agenda_item_number,
    LEFT(u.text, 300) as text_preview,
    m.symbol as meeting
FROM utterances u
JOIN utterance_documents ud ON ud.utterance_id = u.id
JOIN documents d ON d.id = ud.document_id
JOIN documents m ON m.id = u.meeting_id
WHERE d.symbol = 'A/RES/78/281'
ORDER BY u.position_in_meeting;
```

## Data Quality Notes

1. **Speaker Resolution**: Currently uses the given name from the PDF. Future improvements could:
   - Normalize speaker names across meetings
   - Link speakers to actor records
   - Handle variations in name formatting

2. **Document Linking**: Documents are linked based on:
   - Explicit mentions in utterance text
   - Section-level document references
   - Resolution metadata in utterances

3. **Agenda Items**: Each utterance is linked to its agenda item number, enabling queries by topic.

## Future Enhancements

1. **Full-text search**: Add PostgreSQL full-text search on utterance text
2. **Speaker normalization**: Create speaker actor records and link utterances
3. **Sentiment analysis**: Add sentiment scores to utterances
4. **Topic modeling**: Link utterances to topics/themes
5. **Temporal analysis**: Track how positions change over time

