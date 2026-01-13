# UN Document Scraper - Engineering Notebook

**Project:** IGO-Gym Benchmark - UN Document Version History Dataset
**Date Started:** 2025-11-20
**Last Updated:** 2025-11-20
**Status:** ✅ Working pipeline, ready for scale-up

---

## Current Working State

The core of the scraper is a 3-stage Python pipeline: `fetch_metadata.py`, `parse_metadata.py`, and `download_pdfs.py`. An end-to-end test is provided via `test_pipeline.sh`. Data is organized into `data/raw/xml/`, `data/parsed/metadata/`, and `data/documents/pdfs/`.

## Project Goal

To build a scraper for collecting UN General Assembly documents (resolutions and drafts) to create a dataset of document version histories for training LLMs on multilateral decision-making processes.

## Architecture Overview

The system employs a modular, 3-stage pipeline:

```
Stage 1: FETCH        Stage 2: PARSE       Stage 3: DOWNLOAD
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ UN API       │────▶│ MARCXML      │────▶│ PDF Files    │
│ (HTTPS GET)  │     │ Parser       │     │ (Downloads)  │
└──────────────┘     └──────────────┘     └──────────────┘
      │                     │                     │
      ▼                     ▼                     ▼
   XML Files            JSON Files          PDF Files
```

This design ensures modularity, debuggability through intermediate files, resumability, and testability.

### 1. UN API Query Pattern (CRITICAL)

The UN Digital Library API requires `f=symbol` for field-specific searches, as wildcard searches using MARC field syntax (e.g., `191__a:"A/RES/78/*"`) do not work reliably.

### 2. PDF URLs in MARC Tag 856

Direct PDF download URLs are embedded in the MARCXML responses within MARC tag `856`, subfield `u`.

### 3. Encoding Issue with Language Names

Non-English language names sometimes display as garbled text in XML. This was resolved by explicitly opening XML files with UTF-8 encoding and by using URL suffix matching (e.g., `-EN.pdf`) for language detection during downloads.

## Implementation Details

### Module 1: `fetch_metadata.py`

**Purpose:** Queries the UN Digital Library API and saves raw MARCXML responses to `data/raw/xml/`.
**Key Features:** Fetches resolutions and committee drafts for a given session. Uses `f=symbol` parameter in API requests.

### Module 2: `parse_metadata.py`

**Purpose:** Parses MARCXML files to extract structured metadata, saving it as JSON to `data/parsed/metadata/`.
**Key Features:** Extracts `record_id`, `symbol`, `title`, `date`, `subjects`, `authors`, and a list of `files` (including `language`, `size`, `url`).

### Module 3: `download_pdfs.py`

**Purpose:** Downloads PDF files based on parsed metadata, storing them in `data/documents/pdfs/`.
**Key Features:**
*   English-only mode (default).
*   Rate limiting (0.5s delay).
*   Retry logic with exponential backoff.
*   Skips existing files.
*   Sanitizes UN document symbols for safe filenames (e.g., `A/RES/78/242 A` → `A_RES_78_242_A.pdf`).

## Known Issues & Limitations

### 1. Resolution Data Quality (Session 78)

Only ~1% of resolution records for Session 78 contain downloadable PDFs, likely due to incomplete data on the UN's side.
**Workaround:** Committee drafts (`A/C.*`) consistently have 100% success rates for PDF links; focus collection efforts here.

### 2. Low Revision Frequency

Revisions (`/Rev.#`, `/Add.#`, `/Corr.#`) occur in only about 4% of drafts. Significant data collection (multiple sessions) is needed to build a substantial dataset of version chains.

### 3. Voting Records Not Yet Collected

The current pipeline does not collect voting records, which are necessary for programmatically linking drafts to their final resolutions. This is a planned next step.

## Next Steps / Roadmap

### Phase 1: Complete Basic Collection (✅ DONE)

*   Research UN document structure, identify API patterns, and build the modular fetch → parse → download pipeline.
*   Test on Session 78, verify PDF downloads, fix language encoding, and configure English-only downloads.

### Phase 2: Version Chain Building (NEXT)

**Goal:** Link base drafts to their revisions and final resolutions.
**Tasks:**
1.  Collect voting records for resolutions.
2.  Parse draft symbols to identify base documents and modifications (e.g., `A/C.3/78/L.60/Rev.1` → `{base: 'A/C.3/78/L.60', type: 'Rev', num: 1}`).
3.  Integrate and expand the `scratch/version_chain.py` module to build full version graphs.

### Phase 3: Multi-Session Collection

**Goal:** Collect 5-10 sessions for a comprehensive dataset.
**Strategy:** Focus on committee drafts for recent, well-digitized sessions (e.g., 75-79), using the `collect_multiple_sessions.sh` script.

### Phase 4: Dataset Finalization

**Goal:** Organize and document the collected data.
**Tasks:**
1.  Structure data by session (`data/sessions/{session}/metadata/`, `data/sessions/{session}/pdfs/`).
2.  Generate statistics on collected documents, version chain completeness, and language coverage.
3.  Create a comprehensive dataset README with provenance and usage examples.

## Code Patterns & Best Practices

### API Request Pattern

Implement a `fetch_with_retry` function using `requests` with exponential backoff for robustness against network issues and API rate limits.

### XML Parsing Pattern

Use `xml.etree.ElementTree` with explicit UTF-8 encoding and the correct MARCXML namespace (`{'marc': 'http://www.loc.gov/MARC21/slim'}`) to parse MARCXML.

### File Naming Pattern

Sanitize UN document symbols to create safe filenames by replacing `/`, ` `, and `*` characters (e.g., `A/RES/78/242 A` → `A_RES_78_242_A.pdf`).

## Troubleshooting Guide

*   **Empty API Response:** Ensure the `f=symbol` parameter is correctly used in API requests. Test with `curl` to verify API accessibility.
*   **No Files in Parsed JSON:** Verify that MARC tag `856` (containing file information) exists in the raw XML response for the problematic records.
*   **Encoding Errors in Language Names:** Confirm XML files are read with UTF-8 encoding, and use URL suffix (`-EN.pdf`) for robust language detection.
*   **Download Fails (403/404):** Check URL accessibility directly with `curl`. Implement retry logic and log failed downloads.

## Contact & Resources

### UN Digital Library Resources

*   **API Base:** https://digitallibrary.un.org/search
*   **API Docs:** https://digitallibrary.un.org/help/search-engine-api
*   **Document Symbols Guide:** https://research.un.org/en/docs/symbols

---


### 📞 Handoff Notes

**What works well:**
- Committee draft collection (100% success, rich metadata)
- English-only filtering (checks language name OR URL suffix)
- Modular design (each stage independent, resumable)
- Automatic directory organization

**What to watch:**
- Resolutions may become available in newer sessions (try 79, 80)
- Rate limiting on downloads (currently 0.5s, may need adjustment)
- Version chains need explicit linking (not automatic yet)

**What to skip:**
- Don't try to collect resolutions until datas quality improves
- Don't expect many multi-level revisions (focus on Rev.1)
- Don't worry about non-English docs (English-only is sufficient)

---

**Known limitations**
There is still the issue of connecting resolutions to drafts and amendments. We havent shown we can get every part of the pipeline for a single case (draft, amendments, and resolution). maybe next step is run fully on 78, see what we get, and then get claude to figure out why we're not getting all the resolutions (might have to do with the _A suffix). see fetch_metadata.py

*pagination is not implemented on the metadata fetch*

*we don't tie drafts to resolutions or drafts to amendments right now to my knowledge* 

*don't do voting records I believe*

*Optional other session level data like meeting items etc.*

**End of Engineering Notebook**

**Last verified:** 2025-11-20
**Status:** ✅ Production-ready pipeline, ready for scale-up


## 11/26/2025

TODOs: 
-  [ ] resolutions are still coming from XML... which has gaps like A_RES_78_2-EN.pdf which exists at https://docs.un.org/en/a/res/78/2 in the docs.un and should exist on the digital library as well https://digitallibrary.un.org/record/4025277?ln=en&v=pdf. Need to debug this 
- [ ] Run longer... to get comprehensive run so we can trace one thing end to end.
      Pick single resolution, we need all 
         - [  ] plenary drafts [118]
         - [  ] committee reports  [126]
         - [  ] plenary meetings [110]
         - [  ] committee drafts [~200]
      then see if we can step backwards and forwards parsing the parsed json. 
- [ x ] extend html scraping to
   -  [ X ] agenda
   -  [ x ] plenary meetings
   -  [ x ] drafts 
   -  [ x ] committee documents. 
- [ x ] extend html parsing to
   -  [ x ] agenda, plenary meetings
   -  [ x ] drafts
   -  [ x ]  committee documents
- ~[ X ] extend pdf parsing from just agenda & drafts to also 
   -  [ X ] meetings
   -  ~[ X ] initcommittee draft: update: good, but pdf parsing is messy... we get noise in there from headings and footers. Don't get the title correctly either. Probably true for all. 
   -  [ x ] committee report
   -  [ x ] resolutions (should be duplicative of drafts)
- [ X ] double check committee xml scraping; UPDATE: we don't; only get committee drafts, and not reports/ 
- [ X ] Pagination bug: do we handle more than 200 results for any of our fetch_metadata queries? 
- [ x ] pdf parse vs html parse misalignment in script args and output file convention. 
- [ x ] pdf parse on meetings to segment by agenda item, and related docs. 
- [ X] parsing committee reports broken, so to potentially is parse meetings. 
- [ ] Build a bunch of trajectories


## 12/2/2025  

Current state: No one else can trace UNGA resolutions from agenda to draft, to committee deliberations to plenary deliberations. 

Current issues:
- Is this task worthwhile? There's still ambiguity for the agenda -> draft phase, 
- lack summary reports 
- We get country level data, but our speaker level data is messy (only given last name, which we'd ideally connect with other sources potentially)
- Parsing gameplan: 
   - get a sample meeting, and see how we parse. 
      - plenary meeting sample  78_.pv.80



Proposals: research over historical UN records. 

- 

Sample queries: 

- Simple: pull all the statements by Country 


- Complex: pull all statements by Country on Y issue 
      might require semantic embeddings if keyword search or metadata insufficient
- Summarize: pull all statements by Country on Y issue and summarize in a paragraph their general stance on the issue 
- Analysis: pull all statements by Country on Y issue and summarize with an eye towards Z [e.g. how their views have changed over time]
- Simluatory: how would Country react/vote on new sample resolution? 


- coalition mapping: How has X country voted on Y issue? 


## 12/7/2026
Feature requests:
   Make a waiting icon so that once a request is generated for summary or query, the user knows the system is thinking. 
   any improvements to UI for text heavy fields... how can text heavy cols be default wider in the UI, but also expand if need be (pop out maybe? )
   Links to documents - user can click and it downloads/opens the document pdf. 
   Convert HKS Brand Guidelines to a png/jpg so we agent can view it and align the content. 


12/30/25;

Supabase kinda working, tried to load files but can't read yet.

## 12/31/2025

**Schema & RAG Pipeline Fix**

Fixed critical gap where resolution body text wasn't being stored in database:
- **Added** `body_text` column to `documents` table (db/models.py:21)
- **Updated** ETL loader to merge PDF text with HTML metadata (etl/load_resolutions.py:39-110)
  - Handles both old (`draft_text`) and new (`raw_text`/`text_segments`) PDF formats
  - Handles combined symbols like `A/RES/78/80[A]` → `A_RES_78_80_A-B.json`
- **Updated** text-to-SQL schema description to include `body_text` (rag/text_to_sql.py:54)
- **Updated** RAG summarization to prioritize: `body_text` → `text` (utterances) → `doc_metadata` → `title` (rag/rag_summarize.py:47-118)

Coverage: 336/336 resolutions (100%) now have full PDF text available for search and summarization.

Migration: `ALTER TABLE documents ADD COLUMN body_text TEXT;` then reload with `uv run -m etl.run_etl --resolutions-only`



RAG debugging/error assignment:
  parsing: etl failed to properly parse the raw docs in @data/documents\                                                                                                                                                                          
  Database: we failed to properly configure a database to handle the data parsed into @data/parsed/\                                                                                                                                              
  Orchestration: our orchestrator model had a bad prompt or bad tool descriptions so they didn't use them or the tools themselves were bad, insuffient, or too much (distracting from valuabel tools)\                                            
  text to sql: our text to sql prompt is bad\                                                                                                                                                                                                     
  model: everything was perfect, our model was just too dumb to figure this out. \     