# UN Document Database POC Plan

## Overview
Build a PostgreSQL database from parsed JSON documents to enable querying and analysis of UN General Assembly documents. This is a POC with schema flexibility to accommodate JSON format changes.

## Objectives
1. **ETL Pipeline**: Load existing JSONs into PostgreSQL
2. **Query Interface**: Enable SQL queries on structured data
3. **POC UI**: Simple interface for exploring text-heavy data
4. **Future-Ready**: Text-to-SQL capability foundation

---

## Phase 1: Database Schema & Core ETL (Week 1)

### 1.1 Schema Design
**Priority: Core tables that won't change much**

```
documents (core metadata)
  ↓
document_relationships (genealogy edges)
  ↓
actors (countries, speakers)
  ↓
votes, utterances, sponsorships (fact tables)
```

**Deliverables:**
- [ ] `schema.sql` - Complete DDL with indexes
- [ ] `schema_diagram.md` - Visual reference
- [ ] Migration approach for schema changes

**Files to create:**
- `db/schema.sql`
- `db/schema_diagram.md`
- `db/README.md` (setup instructions)

---

### 1.2 ETL Pipeline
**Extract existing JSONs → Transform → Load into PostgreSQL**

**Approach: Modular loaders per document type**
```python
db/
  etl/
    __init__.py
    base_loader.py       # Abstract base class
    document_loader.py   # Load documents table
    resolution_loader.py # Load resolutions + relationships
    draft_loader.py      # Load drafts
    meeting_loader.py    # Load meetings + utterances
    committee_loader.py  # Load committee reports + votes
    agenda_loader.py     # Load agenda items
    actors_loader.py     # Normalize country names
    run_etl.py          # Orchestration script
```

**Key ETL Principles:**
1. **Idempotent**: Can re-run without duplicates
2. **Logging**: Track what loaded, what failed
3. **Partial loads**: Load one document type at a time
4. **Validation**: JSON schema validation before insert
5. **Error tolerance**: Skip bad records, log them

**Deliverables:**
- [ ] ETL scripts for each document type
- [ ] `run_etl.py` - Main orchestrator with CLI args
- [ ] `etl_config.yaml` - Paths, connection strings
- [ ] Error log output to `logs/etl_errors.log`

**Files to create:**
- `db/etl/*.py` (8 files)
- `db/etl_config.yaml`
- `db/requirements.txt` (psycopg2, sqlalchemy, pydantic)

---

### 1.3 Database Setup Automation
**Make it easy to recreate DB from scratch**

```bash
# One command to set up everything
./db/setup_database.sh

# Steps it performs:
# 1. Create database if not exists
# 2. Run schema.sql
# 3. Create indexes
# 4. Load reference data (if any)
```

**Deliverables:**
- [ ] `setup_database.sh` - Automated setup
- [ ] `reset_database.sh` - Drop and recreate (dev only)
- [ ] Docker Compose for PostgreSQL (optional)

**Files to create:**
- `db/setup_database.sh`
- `db/reset_database.sh`
- `docker-compose.yml` (optional)

---

## Phase 2: Query Library & Validation (Week 2)

### 2.1 Common Query Patterns
**Pre-built queries for common use cases**

**Query categories:**
1. **Genealogy queries** - Trace document relationships
2. **Actor queries** - Find statements, votes by country
3. **Vote analysis** - Compare committee vs plenary
4. **Text search** - Full-text search on utterances/drafts
5. **Temporal queries** - Documents by date range
6. **Statistics** - Aggregate counts, summaries

**Deliverables:**
- [ ] `db/queries/*.sql` - Named query files
- [ ] `db/queries/README.md` - Query catalog
- [ ] Python query library for programmatic access

**Files to create:**
```
db/queries/
  genealogy/
    trace_resolution_backward.sql
    trace_agenda_forward.sql
    find_draft_descendants.sql
  actors/
    statements_by_country.sql
    votes_by_country.sql
    sponsorships_by_country.sql
  votes/
    committee_vs_plenary_comparison.sql
    vote_switchers.sql
  text_search/
    search_utterances.sql
    search_draft_text.sql
  stats/
    documents_per_session.sql
    voting_summary.sql
```

---

### 2.2 Query Python API
**Programmatic access for notebooks/scripts**

```python
from db.query_api import UNDatabase

db = UNDatabase()

# Use pre-built queries
tree = db.trace_resolution_backward("A/RES/78/220")

# Or raw SQL
results = db.execute("SELECT * FROM documents WHERE session = 78")

# With parameters
statements = db.query("statements_by_country", country="United States")
```

**Deliverables:**
- [ ] `db/query_api.py` - Python query interface
- [ ] Example notebook: `notebooks/query_examples.ipynb`
- [ ] Unit tests for query API

**Files to create:**
- `db/query_api.py`
- `db/tests/test_query_api.py`
- `notebooks/query_examples.ipynb`

---

### 2.3 Data Validation & Quality Checks
**Ensure data integrity after ETL**

```python
# Validation checks to run after ETL
checks = [
    "All resolutions have at least one related document",
    "All votes reference valid documents and actors",
    "All document relationships have valid endpoints",
    "Date fields are valid",
    "No orphaned utterances (meeting exists)",
]
```

**Deliverables:**
- [ ] `db/validate_data.py` - Data quality checks
- [ ] Report generator for data completeness

**Files to create:**
- `db/validate_data.py`
- `db/validation_rules.yaml`

---

## Phase 3: POC UI (Week 3)

### 3.1 Technology Stack Options

**Option A: Streamlit (Recommended for POC)**
- Fast to build
- Good for text-heavy data
- Built-in expandable sections
- Easy SQL integration

**Option B: Jupyter + Panel**
- Stay in notebook environment
- Good for iterative dev
- Can convert to web app later

**Option C: FastAPI + React**
- More work upfront
- Better for production
- Overkill for POC

**Decision: Start with Streamlit**

---

### 3.2 UI Architecture

```
ui/
  app.py              # Main Streamlit app
  pages/
    1_Browse.py       # Browse documents
    2_Search.py       # Search interface
    3_Genealogy.py    # Trace document relationships
    4_Analysis.py     # Vote analysis, statistics
    5_SQL.py          # Raw SQL interface
  components/
    document_viewer.py    # Display document metadata
    text_expander.py      # Collapsible text sections
    vote_visualizer.py    # Vote tally charts
    genealogy_graph.py    # Interactive graph view
  utils/
    db_connection.py      # Database connection pool
    formatters.py         # Format query results
```

---

### 3.3 UI Features (MVP)

#### **Page 1: Browse Documents**
- Dropdown: Select session, committee, doc type
- Table: Document list with key metadata
- Click row → Expand full details
- Show related documents as links

#### **Page 2: Search**
- Text search across utterances and draft text
- Filters: date range, speaker, document type
- Results with context highlighting
- Expandable text sections

#### **Page 3: Genealogy**
- Input: Document symbol
- Display: Interactive tree/graph
- Click nodes → View document details
- Export graph as JSON/image

#### **Page 4: Analysis**
- Pre-built analyses:
  - Vote comparison (committee vs plenary)
  - Sponsor network
  - Speaking frequency by country
  - Session statistics
- Visualizations: charts, tables

#### **Page 5: SQL Interface**
- Raw SQL editor with syntax highlighting
- Execute and display results
- Export results as CSV/JSON
- Query history
- Saved queries dropdown

---

### 3.4 Text Display Patterns

**Challenge: Display long text (drafts, utterances) without overwhelming UI**

**Solutions:**
1. **Expandable sections**
```python
with st.expander("Draft Text (1,234 words)"):
    st.text_area("", value=draft_text, height=300)
```

2. **Preview + "Show more"**
```python
preview = text[:500] + "..." if len(text) > 500 else text
st.write(preview)
if len(text) > 500:
    if st.button("Show full text"):
        st.write(text)
```

3. **Tabbed interface**
```python
tab1, tab2, tab3 = st.tabs(["Metadata", "Text", "Related"])
with tab1:
    # Show metadata table
with tab2:
    # Show full text with search highlighting
with tab3:
    # Show related documents
```

4. **Word count badges**
```python
st.metric("Draft length", f"{word_count} words")
```

**Deliverables:**
- [ ] Streamlit app with 5 pages
- [ ] Component library for common displays
- [ ] Documentation for running UI

**Files to create:**
- `ui/app.py` + all sub-files
- `ui/requirements.txt`
- `ui/README.md`

---

## Phase 4: Text-to-SQL Foundation (Week 4 - Optional)

### 4.1 Approach
Use LLM (GPT-4, Claude) to translate natural language → SQL

**Architecture:**
```
User query → LLM with schema context → SQL → Execute → Format results
```

**Required components:**
1. **Schema description** - Human-readable schema for LLM
2. **Example queries** - Few-shot examples for LLM
3. **SQL validator** - Check generated SQL before execution
4. **Query executor** - Run with safety limits
5. **Result formatter** - Present results naturally

### 4.2 Implementation Plan

**Step 1: Schema documentation for LLM**
```markdown
# Database Schema for LLM

## Tables
- documents: Core document metadata (symbol, title, date, session, committee)
- utterances: Statements made in meetings (speaker, text, meeting_symbol)
- votes: How countries voted (document_symbol, actor_id, vote_choice)
- actors: Countries and speakers (name, normalized_name)

## Common queries:
- "Find all statements by [country]": JOIN utterances → actors
- "Trace resolution backward": Recursive CTE on document_relationships
- "Compare votes": JOIN votes WHERE vote_context IN ('committee', 'plenary')
```

**Step 2: LLM integration**
```python
# ui/pages/6_Natural_Language.py
import anthropic  # or openai

def text_to_sql(question: str) -> str:
    prompt = f"""
    {SCHEMA_CONTEXT}

    User question: {question}

    Generate SQL query to answer this question.
    Return ONLY the SQL, no explanation.
    """

    response = anthropic.complete(prompt)
    sql = extract_sql(response)
    return sql

# Show generated SQL to user for transparency
st.code(sql, language="sql")

# Ask user to confirm before executing
if st.button("Execute this query"):
    results = execute_sql(sql)
    display_results(results)
```

**Step 3: Safety measures**
- Read-only database user
- Query timeout (30 seconds)
- Result limit (1000 rows)
- No DROP/DELETE/UPDATE allowed
- Show SQL before executing

**Deliverables:**
- [ ] Schema description for LLM
- [ ] Text-to-SQL interface page
- [ ] SQL validator and safety checks
- [ ] Few-shot examples library

**Files to create:**
- `ui/llm/schema_context.md`
- `ui/llm/text_to_sql.py`
- `ui/llm/examples.yaml`
- `ui/pages/6_Natural_Language.py`

---

## Project Structure (Final)

```
un_draft/
├── db/                           # Database layer
│   ├── schema.sql
│   ├── schema_diagram.md
│   ├── setup_database.sh
│   ├── reset_database.sh
│   ├── etl/                      # ETL scripts
│   │   ├── base_loader.py
│   │   ├── document_loader.py
│   │   ├── resolution_loader.py
│   │   ├── draft_loader.py
│   │   ├── meeting_loader.py
│   │   ├── committee_loader.py
│   │   ├── agenda_loader.py
│   │   ├── actors_loader.py
│   │   └── run_etl.py
│   ├── queries/                  # Query library
│   │   ├── genealogy/
│   │   ├── actors/
│   │   ├── votes/
│   │   ├── text_search/
│   │   └── stats/
│   ├── query_api.py              # Python query interface
│   ├── validate_data.py          # Data quality checks
│   └── requirements.txt
│
├── ui/                           # Streamlit UI
│   ├── app.py
│   ├── pages/
│   │   ├── 1_Browse.py
│   │   ├── 2_Search.py
│   │   ├── 3_Genealogy.py
│   │   ├── 4_Analysis.py
│   │   ├── 5_SQL.py
│   │   └── 6_Natural_Language.py  # Optional
│   ├── components/
│   │   ├── document_viewer.py
│   │   ├── text_expander.py
│   │   ├── vote_visualizer.py
│   │   └── genealogy_graph.py
│   ├── llm/                      # Text-to-SQL (optional)
│   │   ├── schema_context.md
│   │   ├── text_to_sql.py
│   │   └── examples.yaml
│   └── requirements.txt
│
├── notebooks/                    # Analysis notebooks
│   └── query_examples.ipynb
│
├── data/                         # Existing data
│   ├── parsed/
│   └── documents/
│
├── docker-compose.yml            # Optional: PostgreSQL container
├── DATABASE_PLAN.md              # This file
└── README.md                     # Update with DB setup
```

---

## Execution Strategy

### Week 1: Foundation
**Days 1-2: Schema**
- Design schema.sql (iterate with stakeholder)
- Create setup scripts
- Test schema creation

**Days 3-5: ETL Core**
- Build base_loader.py framework
- Implement document_loader.py (simplest)
- Implement resolution_loader.py
- Test with subset of data

**Days 6-7: Complete ETL**
- Finish remaining loaders
- Add error handling
- Run full ETL on all data
- Validate data quality

### Week 2: Query Layer
**Days 1-3: SQL Queries**
- Write common queries
- Document each query's purpose
- Test on real data

**Days 4-5: Python API**
- Build query_api.py
- Create example notebook
- Write unit tests

**Days 6-7: Validation**
- Data quality checks
- Performance profiling
- Index optimization

### Week 3: UI POC
**Days 1-2: Setup**
- Streamlit project setup
- Database connection
- Basic layout

**Days 3-4: Core Pages**
- Browse page
- Search page
- SQL interface

**Days 5-6: Advanced Pages**
- Genealogy visualization
- Analysis page
- Text display components

**Day 7: Polish**
- Styling
- Documentation
- Demo preparation

### Week 4 (Optional): Text-to-SQL
- LLM integration
- Safety measures
- Testing with various queries

---

## Success Criteria

### Phase 1 Complete When:
- [ ] All JSONs successfully loaded into database
- [ ] No data integrity errors
- [ ] ETL can be re-run idempotently
- [ ] Database can be recreated from scratch in < 5 minutes

### Phase 2 Complete When:
- [ ] 20+ common queries documented and working
- [ ] Python API provides clean interface
- [ ] Queries return results in < 1 second
- [ ] Data validation passes all checks

### Phase 3 Complete When:
- [ ] UI displays all document types correctly
- [ ] Long text is readable (expandable/collapsible)
- [ ] Genealogy visualization works
- [ ] SQL interface allows arbitrary queries
- [ ] Demo-able to stakeholders

### Phase 4 Complete When:
- [ ] Text-to-SQL generates correct queries 80%+ of time
- [ ] User can verify SQL before execution
- [ ] Safety measures prevent dangerous queries

---

## Risk Mitigation

### Risk 1: JSON Format Changes
**Mitigation:**
- Use JSONB column for flexible storage
- ETL loaders extract known fields, store rest as JSON
- Version schema with migrations

### Risk 2: Data Quality Issues
**Mitigation:**
- Validation checks after ETL
- Logs for all errors
- Skip bad records, don't fail entire ETL

### Risk 3: Performance Problems
**Mitigation:**
- Index all foreign keys
- Full-text search indexes
- Materialized views for complex queries
- Profile and optimize incrementally

### Risk 4: UI Too Slow
**Mitigation:**
- Pagination for large result sets
- Async loading for heavy queries
- Caching for repeated queries
- Connection pooling

---

## Future Enhancements (Post-POC)

1. **GraphQL API** - More flexible than REST
2. **Real-time updates** - WebSocket for live data
3. **Export functionality** - CSV, JSON, PDF reports
4. **User accounts** - Save queries, preferences
5. **Materialized views** - Pre-compute common queries
6. **Vector search** - Semantic search on documents
7. **Knowledge graph** - Neo4j for network analysis
8. **ML features** - Predict votes, detect patterns

---

## Resources Needed

### Tools
- PostgreSQL 14+
- Python 3.10+
- Streamlit
- SQLAlchemy
- psycopg2

### Optional
- Docker (for PostgreSQL)
- Anthropic/OpenAI API (for text-to-SQL)
- Neo4j (if graph features needed)

### Skills Required
- SQL (intermediate)
- Python (intermediate)
- Basic web development
- Data modeling

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Prioritize phases** - Do we need all 4 phases?
3. **Set up development environment**
4. **Create GitHub issues** from checkboxes
5. **Start with Phase 1.1** - Schema design

---

## Questions to Answer

1. **Database hosting**: Local dev only, or need production setup?
2. **Scale**: Just session 78, or all sessions?
3. **Users**: Single user, or multi-user system?
4. **Refresh cadence**: One-time load, or periodic updates?
5. **Budget**: Any $ for OpenAI/Anthropic API?

---

## Appendix: Quick Start Commands

```bash
# Setup database
cd db
./setup_database.sh

# Run ETL
uv run db/etl/run_etl.py --all

# Validate data
uv run db/validate_data.py

# Start UI
cd ui
streamlit run app.py

# Run query examples
jupyter notebook notebooks/query_examples.ipynb
```
