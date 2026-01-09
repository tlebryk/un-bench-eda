# RAG Enhancement Plan: Evidence-Grounded Question Answering

## Current State Analysis

### Existing RAG Capabilities
1. **Text-to-SQL** (`rag/text_to_sql.py`)
   - Converts natural language questions to SQL queries
   - Uses OpenAI API with schema description
   - Generates read-only SELECT queries

2. **Summarization** (`rag/rag_summarize.py`)
   - Summarizes SQL query results
   - Extracts text from `body_text`, `text` (utterances), `doc_metadata`, or `title`
   - Limited to 5 results (`MAX_RESULTS_FOR_SUMMARIZATION = 5`)
   - Generic summary prompt, not question-answering focused

3. **UI Integration** (`ui/app.py`, `ui/templates/index.html`)
   - Natural language query input
   - SQL generation and execution
   - Optional "Summarize Results" button
   - Demo mode exists but not RAG-focused

4. **Multi-step Tooling** (`rag/multistep/`)
   - `tools.py` exposes `get_related_documents`, `get_votes`, `get_utterances`, and `answer_with_evidence`
   - `orchestrator.py` runs OpenAI Responses API calls with those tools and logs each step
   - `logs/multistep_tools.log` captures arguments, runtimes, and result summaries for debugging

### Current Limitations
1. **Generic summarization**: Not optimized for answering specific questions
2. **No speculation prevention**: No explicit guardrails against making up information
3. **No structured citations**: Can't trace answers back to specific documents/symbols
4. **UI gap**: Multi-step orchestration lives in `rag/multistep/` but the FastAPI layer still exposes only the single-shot summarize endpoint

## Multi-step Stack (January 2026)

The tooling referenced below already ships in the repo and should be treated as the starting point for any new work:

- **Tool suite** – `rag/multistep/tools.py` declares JSON schemas for `get_related_documents`, `get_votes`, `get_utterances`, and `answer_with_evidence`. Each helper has a matching executor that runs directly against PostgreSQL via SQLAlchemy.
- **Orchestrator** – `rag/multistep/orchestrator.py` calls the OpenAI Responses API (`client.responses.create`) with the `gpt-5-nano-2025-08-07` model, loops up to six tool invocations, and logs every step to `logs/multistep_tools.log` before delegating to `rag.rag_qa.answer_question()`.
- **Genealogy via SQL** – `execute_get_related_documents()` uses a recursive CTE to traverse `document_relationships` in both directions, grouping outputs into meetings, drafts, committee reports, and agenda items so subsequent tools (utterances, votes) know what to fetch. The query lives alongside the executor for quick reference:
  ```sql
  WITH RECURSIVE related_docs AS (
    SELECT id, symbol, doc_type, 'self'::varchar AS relationship_type, 0 AS depth
    FROM documents WHERE symbol = :symbol
    UNION ALL
    SELECT d.id, d.symbol, d.doc_type, dr.relationship_type, rd.depth + 1
    FROM related_docs rd
    JOIN document_relationships dr ON dr.target_id = rd.id OR dr.source_id = rd.id
    JOIN documents d ON d.id = dr.source_id OR d.id = dr.target_id
    WHERE rd.depth < 3 AND d.id != rd.id
  )
  SELECT DISTINCT symbol, doc_type, relationship_type
  FROM related_docs
  WHERE relationship_type != 'self'
  ORDER BY doc_type, symbol;
  ```
- **Evidence formatting** – Orchestrator accumulates tool outputs as `rows/columns` dictionaries, which plug directly into `rag.rag_qa.extract_evidence_context()` for citation generation.
- **Regression tests** – `tests/integration/test_related_documents_integration.py` covers traversal + chaining, while `tests/rag/test_multistep_tools.py` exercises the tool wrappers. Run them after seeding the dev DB (`docker-compose up postgres_dev`, `USE_DEV_DB=true`, `uv run python scripts/seed_dev_db.py`).

Keep this stack in sync as enhancements land—UI wiring, guardrails, and prompt work should build on it instead of re-implementing functionality.

## Enhancement Goals

### Primary Objectives
1. **Question-Answering Focus**: Move from generic summarization to direct Q&A
2. **No Speculation**: Strict prompt engineering to prevent hallucination
3. **Data-Driven Only**: Responses must be based solely on retrieved database content
4. **Demo Workflow**: Clear, showcase-ready RAG demo path

## Proposed Architecture

### 1. Enhanced RAG Pipeline (`rag/rag_qa.py` - NEW)

**Purpose**: Supplement generic summarization with question-answering that:
- Answers the specific question asked
- Cites evidence from retrieved documents
- Prevents speculation
- Handles cases where data is insufficient

**Key Components**:

```python
def answer_question(
    query_results: Dict[str, Any],
    original_question: str,
    sql_query: str,
    model: str = "gpt-5-nano-2025-08-07"  # Matches orchestrator + current SDK support
) -> Dict[str, Any]:
    """
    Returns:
    {
        "answer": str,  # Direct answer to question
        "evidence": List[Dict],  # List of cited sources
        "confidence": str,  # "high", "medium", "low", "insufficient_data"
        "sources": List[str]  # Document symbols referenced
    }
    """
```

**OPtional: Evidence Extraction**:
- Extract document symbols from query results
- Extract relevant text passages that support the answer
- Track which documents/utterances contributed to the answer
- Include metadata (dates, titles, vote counts, etc.)

**Prompt Engineering**:
```
You are analyzing UN General Assembly documents and meeting records.

CRITICAL RULES:
1. Answer ONLY based on the provided data. Do not use external knowledge.
2. If the data doesn't contain enough information to answer, say "Insufficient data: [what's missing]"
3. Cite specific documents by symbol (e.g., "A/RES/78/220") when making claims
4. Quote exact passages when possible
5. Distinguish between what the data shows vs. what you infer

Original question: {original_question}

SQL Query used: {sql_query}

Retrieved data:
{formatted_results}

Provide:
1. Direct answer to the question
2. Evidence citations (document symbols, quotes, dates)
3. Confidence level (high/medium/low/insufficient_data)
```

### 2. Enhanced Text Extraction (`rag/rag_qa.py`)
We currently only RAG over a set number of text fields. Long term, we need additional features: if a query does not return all the text / info needed for a summarization,we need to run another query to get it. Second, we should RAG over all relevant info (structured metadata, vote counts, doc names, actor names etc.), not just summarize the big text fields. Should handle RAG over all tables (see `docs/README_DATABASE.md`).

```python
def extract_evidence_context(
    query_results: Dict[str, Any],
    max_results: int = 20  # Increased from 5
) -> List[Dict[str, Any]]:
    """
    Returns:
    [
        {
            "type": "document" | "utterance" | "vote_summary",
            "symbol": "A/RES/78/220",
            "text": "...",
            "metadata": {"date": "...", "title": "...", ...}
        },
        ...
    ]
    """
```

### 3. UI Enhancements (`ui/app.py`, `ui/templates/index.html`)

**New Endpoint**: `/api/rag-answer`
- Replaces or complements `/api/summarize`
- Returns structured answer with citations
- Handles both natural language and SQL queries

**UI Changes**:
- Handle both summarize we've run a query, but also allow for direct QA. this can be abstracted from the user and set via configs, especially in demo mode (see demo path).
- Display answer prominently
- Show evidence citations as expandable sections
- Link citations to document symbols (clickable → view document)
- Show confidence indicator (stretch)
- Display "Insufficient data" warnings when appropriate

**Demo Mode Enhancement**:
- Add RAG demo workflow: `/demo/rag`
- Pre-populated example questions
- Step-by-step walkthrough:
  1. Ask question
  2. In demo mode, hide SQL!
  3. Show retrieved results
  4. Show evidence-grounded answer
  5. Show citations

### 4. Prompt Engineering for Grounding

**System Prompt Template**:
```
You are a research assistant analyzing UN General Assembly documents.

STRICT RULES:
1. Base answers ONLY on the provided database results
2. Cite sources using document symbols (e.g., "According to A/RES/78/220...")
3. Quote exact text when making specific claims
4. If data is insufficient, explicitly state what's missing
5. Do NOT speculate, infer beyond what's stated, or use external knowledge
6. Distinguish between:
   - What the data explicitly states
   - What can be inferred from the data
   - What is unknown/not in the data

Question: {question}
SQL Query: {sql_query}
Retrieved Data: {evidence_context}

Provide a structured answer with citations.
```

**Response Format**:
```
Answer: [direct answer to question]

Evidence:
- [Document symbol]: "[quoted passage]"
- [Document symbol]: [structured data point]

Confidence: [high/medium/low/insufficient_data]

Sources: [list of document symbols]
```

### 5. Demo Workflow Design

**Path**: `/demo/rag` or `/?demo=true&mode=rag`

**Features**:
1. **Example Questions** (pre-populated):
   - "What did the USA vote on resolution A/RES/78/220?"
   - "Which countries abstained from voting on Iran-related resolutions in session 78?"
   - "What did France say about climate change in plenary meetings?"
   - "Show me all resolutions about human rights in session 78"

2. **Interactive Flow**:
   - User selects or types question
   - System shows: "Executing query..."
   - System shows: "Retrieved X documents"
   - System shows: "Generating evidence-grounded answer..."
   - System displays answer with citations

3. **Visualization**:
   - Answer box (prominent)
   - Evidence panel (expandable)
   - Source documents (clickable list)
   - Confidence indicator (color-coded)

## Implementation Plan

### Phase 1: Core RAG Q&A Module
1. Create `rag/rag_qa.py` with:
   - `extract_evidence_context()` - Enhanced text extraction
   - `answer_question()` - Main Q&A function
   - `format_evidence()` - Citation formatting
   - `assess_confidence()` - Confidence scoring

2. Update prompts for strict grounding
3. Add unit tests for evidence extraction

### Phase 2: API Integration
1. Add `/api/rag-answer` endpoint to `ui/app.py`
2. Update UI to use new endpoint
3. Replace "Summarize" with "Answer Question"
4. Add citation display components

### Phase 3: Demo Workflow
1. Create demo route/page
2. Add example questions
3. Add step-by-step visualization
4. Add documentation

### Phase 4: Enhanced Features
1. Multi-step reasoning (if question requires multiple queries)
2. Query refinement suggestions
3. Related questions suggestions
4. Export answers with citations

## Technical Details

### Evidence Extraction Strategy
1. **Document Text** (`body_text` column):
   - Extract full text for resolutions/drafts
   - Include document symbol, title, date
   - Truncate if too long (keep first N chars + last N chars)

2. **Utterances** (`text` column):
   - Extract speaker, affiliation, meeting context
   - Include agenda item number
   - Preserve chronological order

3. **Structured Data** (votes, relationships):
   - Format as readable summaries
   - Include counts, percentages
   - Link to document symbols

4. **Metadata**:
   - Extract relevant fields (dates, titles, session numbers)
   - Include in evidence context

### Citation Format
- **Document citations**: `A/RES/78/220` (linkable to document view)
- **Utterance citations**: `A/78/PV.80, section 11 (France)` (linkable to meeting)
- **Quote citations**: `"exact quoted text" (A/RES/78/220)`

### Confidence Levels
- **High**: Clear answer with multiple supporting sources
- **Medium**: Answer with some supporting sources, minor gaps
- **Low**: Partial answer, limited sources
- **Insufficient_data**: Cannot answer from available data

## Success Metrics

1. **Accuracy**: Answers are factually correct based on source data
2. **Grounding**: 100% of claims have citations
3. **No Hallucination**: Zero instances of unsupported claims
4. **User Experience**: Clear, actionable answers with traceable sources
5. **Demo Quality**: Showcase-ready workflow that demonstrates capabilities

## Migration Strategy

1. **Backward Compatibility**: Keep `/api/summarize` for existing workflows
2. **Gradual Rollout**: Add `/api/rag-answer` alongside existing endpoint
3. **Feature Flag**: Allow switching between old and new RAG modes
4. **A/B Testing**: Compare old summarization vs. new Q&A approach

## Future Enhancements

1. **Multi-Query Reasoning**: Break complex questions into multiple SQL queries
2. **Semantic Search**: Use embeddings for better document retrieval
3. **Cross-Document Analysis**: Answer questions requiring multiple documents
4. **Temporal Reasoning**: Handle questions about changes over time
5. **Comparative Analysis**: Compare voting patterns, statements across countries/topics

## Files to Create/Modify

### New Files
- `rag/rag_qa.py` - Core Q&A module
- `docs/rag_qa_guide.md` - User guide
- `tests/rag/test_rag_qa.py` - Unit tests

### Modified Files
- `ui/app.py` - Add `/api/rag-answer` endpoint
- `ui/templates/index.html` - Update UI for Q&A display
- `rag/__init__.py` - Export new functions
- `README.md` - Document new RAG capabilities
