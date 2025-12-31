# UN General Assembly Document Structure & Data Layout

## Overview

This document explains how UN General Assembly documents are organized, named, and accessed. This is essential for building a systematic scraper to collect draft version history for the IGO-Gym benchmark.

---

## 1. Document Symbol Patterns

### 1.1 Basic Structure

UN document symbols follow a hierarchical pattern:

```
[ORGAN]/[SUBSIDIARY]/[SESSION or YEAR]/[TYPE].[NUMBER]/[MODIFICATIONS]
```

**Examples:**
- `A/RES/78/243` - General Assembly Resolution, 78th session, number 243
- `A/C.3/78/L.60` - General Assembly, 3rd Committee, 78th session, Limited distribution doc 60
- `A/C.3/78/L.60/Rev.1` - Same document, Revision 1

### 1.2 Key Components

**Organ Codes:**
- `A/` = General Assembly
- `S/` = Security Council
- `E/` = Economic and Social Council
- `ST/` = Secretariat

**Subsidiary Bodies:**
- `/C.#/` = Main Committee (# = 1-6)
- `/CONF.` = Conference
- `/AC.` = Ad hoc committee

**Document Types:**
- `/RES/` = Resolution (final adopted text)
- `/L.` = Limited distribution (typically **draft resolutions**)
- `/PV.` = Verbatim records (meeting transcripts)
- `/SR.` = Summary records
- `/INF/` = Information series

**Modification Suffixes:**
- `/Rev.#` = Revision (replaces previous version)
- `/Add.#` = Addendum (supplementary content, often additional sponsors)
- `/Corr.#` = Corrigendum (corrections)
- `/Amend.#` = Amendment

### 1.3 Critical Patterns for Version Tracking

**Draft Resolutions (L Documents):**
- Committee drafts: `A/C.[1-6]/[SESSION]/L.[NUMBER]`
- Plenary drafts: `A/[SESSION]/L.[NUMBER]`
- Example: `A/C.3/78/L.60`

**Final Resolutions:**
- Pattern: `A/RES/[SESSION]/[NUMBER]`
- Example: `A/RES/78/243`

**Revision Chain:**
```
A/C.3/78/L.60           (Original draft)
A/C.3/78/L.60/Add.1     (Additional sponsors)
A/C.3/78/L.60/Rev.1     (First revision)
A/C.3/78/L.60/Rev.2     (Second revision)
→ A/RES/78/243          (Final adopted resolution)
```

---

## 2. Organizational Hierarchy

### 2.1 Sessions

- Each General Assembly session is numbered sequentially (e.g., 78th, 79th)
- Sessions run roughly September to September
- Since 1976, session numbers appear in all GA document symbols

### 2.2 Main Committees

All UN member states participate in six Main Committees:

| Committee | Symbol | Subject Area |
|-----------|--------|--------------|
| First | A/C.1/ | Disarmament and international security |
| Second | A/C.2/ | Economic and financial |
| Third | A/C.3/ | Social, humanitarian, cultural, human rights |
| Fourth | A/C.4/ | Special political and decolonization |
| Fifth | A/C.5/ | Administrative and budgetary |
| Sixth | A/C.6/ | Legal matters |

### 2.3 Document Workflow

Typical path from draft to resolution:

1. **Committee Phase:**
   - Draft introduced: `A/C.#/SESSION/L.NUMBER`
   - Revisions negotiated: `A/C.#/SESSION/L.NUMBER/Rev.1`, etc.
   - Committee votes on draft
   - Committee report to plenary: `A/SESSION/NUMBER`

2. **Plenary Phase:**
   - Plenary considers committee report
   - Plenary votes on recommendation
   - Adopted as resolution: `A/RES/SESSION/NUMBER`

3. **Supporting Documents:**
   - Meeting records: `A/C.#/SESSION/SR.NUMBER` or `A/C.#/SESSION/PV.NUMBER`
   - Voting records: Link drafts to final resolutions

---

## 3. Data Sources & APIs

### 3.1 UN Digital Library (Primary Source)

**URL:** https://digitallibrary.un.org/

**Key Features:**
- 1.17M+ items (761K+ documents)
- Comprehensive from 1993-present
- API access for programmatic collection
- Voting records collection (23K+ records)

**API Endpoint:**
```
https://digitallibrary.un.org/search?p=[QUERY]&of=[FORMAT]&jrec=[START]&rg=[LIMIT]
```

**Key Parameters:**
- `p` = search pattern (e.g., `191__a:"A/RES/78/*"` for document symbol search)
- `of` = output format
  - `xm` = MARCXML (recommended for metadata)
  - `recjson` = JSON format
- `jrec` = starting record number (for pagination)
- `rg` = records per page (recommend 100)

**Example Queries:**

All 78th session resolutions:
```
https://digitallibrary.un.org/search?p=191__a:"A/RES/78/*"&of=xm&rg=100&jrec=1
```

All Third Committee drafts, 78th session:
```
https://digitallibrary.un.org/search?p=191__a:"A/C.3/78/L.*"&of=xm&rg=100&jrec=1
```

All documents with revisions:
```
https://digitallibrary.un.org/search?p=191__a:"*/Rev.*"&of=xm&rg=100&jrec=1
```

Voting records:
```
https://digitallibrary.un.org/search?c=Voting+Data&p=191__a:"A/RES/78/*"&of=recjson&rg=100
```

### 3.2 UN Official Document System (ODS)

**URL:** https://documents.un.org/

**Key Features:**
- Free access to documents from 1993+
- Full-text search
- CSV/JSON export (limited to 500 records)

**Limitations:**
- No official public API
- Export limited to 500 symbols
- Requires web scraping for bulk access

### 3.3 MARCXML Metadata Fields

Key fields in UN Digital Library API responses:

| MARC Field | Description | Example |
|------------|-------------|---------|
| 191__a | Document Symbol | A/RES/78/243 |
| 245 | Title | "Human rights in the administration of justice" |
| 269 | Publication Date | 2024-11-15 |
| 710 | Authors/Sponsors | Mexico, Germany |
| 590 | Series | "General Assembly Resolutions" |
| 650 | Subjects | Human rights, Justice |
| 991 | Agenda Item | "Agenda item 73" |

---

## 4. Version Tracking Strategy

### 4.1 How to Map Drafts to Final Resolutions

**Method 1: Voting Records (Recommended)**
1. Query voting records for a resolution
2. Extract linked draft symbol from voting data
3. Search for all revisions of that draft

**Method 2: Committee Reports**
- Pattern: `A/[SESSION]/[NUMBER]`
- Reports explicitly reference which draft became which resolution
- Example: Third Committee report `A/79/434` → Resolution `A/RES/79/194`

**Method 3: Pattern Matching**
- Drafts often have similar numbering to final resolutions
- Not reliable as primary method, use for verification

### 4.2 Building Version Chains

For each final resolution:

1. Find the draft symbol (via voting records)
2. Search for all modifications:
   - Base: `A/C.#/SESSION/L.NUMBER`
   - Revisions: `A/C.#/SESSION/L.NUMBER/Rev.*`
   - Addenda: `A/C.#/SESSION/L.NUMBER/Add.*`
   - Corrigenda: `A/C.#/SESSION/L.NUMBER/Corr.*`
3. Sort by modification type and number
4. Build temporal sequence

**Example Chain:**
```
A/C.3/78/L.60           → Original draft
A/C.3/78/L.60/Add.1     → Additional sponsors added
A/C.3/78/L.60/Rev.1     → Text revised
A/C.3/78/L.60/Rev.2     → Further revisions
A/RES/78/243            → Final adopted resolution
```

### 4.3 Document Availability

**What's Available:**
- Metadata: All documents from 1993+ (comprehensive)
- Full text PDFs: Most documents from 1993+
- Voting records: Links between drafts and resolutions
- Meeting records: Procedural context

**What's Limited:**
- XML format: Not comprehensive (mostly PDF)
- Pre-1993 documents: Less complete coverage
- Explicit version relationships: Must be reconstructed

---

## 5. Systematic Collection Strategy

### 5.1 Enumeration Approach

**Session-Based Collection (Recommended):**

```
For each session (e.g., 78, 79):
  1. Get all resolutions: A/RES/{session}/*
  2. Get all committee drafts: A/C.[1-6]/{session}/L.*
  3. Get all plenary drafts: A/{session}/L.*
  4. Get voting records for resolutions
  5. Map drafts to resolutions
  6. Build version chains
```

**Committee-Based Collection:**

```
For each committee (1-6):
  For each session:
    1. Get all drafts: A/C.{#}/{session}/L.*
    2. Get all revisions (pattern: */Rev.*, */Add.*)
    3. Build version families
```

### 5.2 Practical API Usage

**Pagination Pattern:**
```python
base_url = "https://digitallibrary.un.org/search"
params = {
    "p": '191__a:"A/RES/78/*"',
    "of": "xm",
    "rg": 100
}

total_records = get_total_count(base_url, params)
for start in range(1, total_records, 100):
    params["jrec"] = start
    response = requests.get(base_url, params=params)
    records = parse_marcxml(response.content)
    process_records(records)
```

**Rate Limiting:**
- Recommended: 1-2 requests per second
- Implement exponential backoff for errors
- Cache responses locally

### 5.3 Data Storage Structure

Recommended organization:

```
data/
├── metadata/
│   ├── sessions/
│   │   ├── 78_resolutions.json
│   │   ├── 78_drafts.json
│   │   └── 78_voting.json
│   └── version_chains/
│       └── 78_chains.json
├── documents/
│   ├── pdfs/
│   │   ├── A_RES_78_243.pdf
│   │   ├── A_C.3_78_L.60.pdf
│   │   └── A_C.3_78_L.60_Rev.1.pdf
│   └── text/
│       └── (extracted text from PDFs)
└── logs/
    └── collection.log
```

---

## 6. Document Universe Mapping

### 6.1 Complete Taxonomy

```
General Assembly Documents
│
├── Plenary Documents (A/session/*)
│   ├── Resolutions (A/RES/session/*)           [FINAL ADOPTED TEXTS]
│   ├── Draft Resolutions (A/session/L.*)       [WORKING DOCUMENTS]
│   │   ├── Revisions (/Rev.*)
│   │   ├── Addenda (/Add.*)
│   │   └── Corrigenda (/Corr.*)
│   ├── Meeting Records (A/session/PV.*)
│   └── Reports from committees
│
└── Main Committee Documents (A/C.[1-6]/session/*)
    ├── Draft Resolutions (A/C.#/session/L.*)   [WORKING DOCUMENTS]
    │   ├── Revisions (/Rev.*)
    │   ├── Addenda (/Add.*)
    │   └── Corrigenda (/Corr.*)
    ├── Meeting Records (A/C.#/session/SR.* or PV.*)
    └── Reports to Plenary (A/session/*)
```

### 6.2 Estimated Dataset Size

**Per Session (e.g., 78th):**
- Resolutions: ~300
- Committee drafts: ~400-500
- Plenary documents: ~500-1000
- Total relevant documents: ~1,500-2,500

**For 5 Sessions (75-79):**
- Total documents: ~7,500-12,500
- Version chains (draft→final): ~1,000-2,000

### 6.3 Priority Documents for IGO-Gym

**Highest Priority:**
1. Draft resolutions (L documents) - Working documents with revisions
2. Final resolutions (RES documents) - Adopted versions
3. Voting records - Links drafts to finals, includes sponsor data

**Medium Priority:**
1. Committee reports - Procedural summaries
2. Meeting records - Context and debate history

**Lower Priority:**
1. Information documents - Supplementary materials
2. Conference documents - Often one-off events

---

## 7. Implementation Workflow

### Phase 1: Metadata Collection
1. Query UN Digital Library for session documents
2. Parse MARCXML responses
3. Extract: symbol, title, date, sponsors, subjects
4. Store metadata in JSON files

### Phase 2: Version Chain Construction
1. For each resolution, query voting records
2. Extract draft symbol from voting data
3. Search for all revisions (pattern matching)
4. Build graph: draft → revisions → final
5. Store relationships in JSON

### Phase 3: Document Download
1. For each document in version chain:
2. Download PDF from UN Digital Library
3. Organize by session/committee
4. Log download status

### Phase 4: Validation
1. Manually verify 10-20 version chains
2. Check completeness (all revisions found?)
3. Validate draft→final mappings
4. Document any anomalies

---

## 8. Key Insights

### Strengths of UN Document System
- Systematic, predictable symbol patterns
- Comprehensive coverage from 1993+
- API access for programmatic collection
- Rich metadata (sponsors, votes, dates)
- Voting records link drafts to finals

### Challenges
- No single "parent document" field
- Version chains must be reconstructed
- Primarily PDF format (requires text extraction)
- Rate limits on API access
- Some pre-1993 gaps

### Best Practices
1. Start with one session as pilot (validate approach)
2. Use voting records for draft→resolution mapping
3. Implement aggressive caching
4. Rate limit API requests (1-2 per second)
5. Manually validate sample of chains
6. Log all collection activities

---

## 9. References

- UN Digital Library: https://digitallibrary.un.org/
- UN ODS: https://documents.un.org/
- Research Guides: https://research.un.org/en/docs
- Document Symbols Guide: https://research.un.org/en/docs/symbols
- API Documentation: https://digitallibrary.un.org/help/search-engine-api

---

## 10. Quick Reference

**Find all resolutions for session 78:**
```
p=191__a:"A/RES/78/*"
```

**Find all Third Committee drafts for session 78:**
```
p=191__a:"A/C.3/78/L.*"
```

**Find all documents with revisions:**
```
p=191__a:"*/Rev.*"
```

**Get voting records for session 78 resolutions:**
```
c=Voting+Data&p=191__a:"A/RES/78/*"
```

**MARCXML format (recommended):**
```
of=xm
```

**Pagination (100 records starting at record 1):**
```
rg=100&jrec=1
```
