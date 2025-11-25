# UN Document Scraper

A modular scraper for collecting UN General Assembly documents and building version history chains for the IGO-Gym benchmark project.

## Overview

This scraper collects UN documents from the UN Digital Library, builds version chains tracking the evolution of draft resolutions through revisions to final adopted resolutions, and optionally downloads the documents as PDFs.

## Components

### 1. Documentation
- **`un_document_structure.md`**: Comprehensive guide to UN document organization, naming conventions, and data sources

### 2. Core Modules

- **`metadata_collector.py`**: Collects document metadata from the UN Digital Library API
  - Query by session, committee, or document type
  - Parse MARCXML responses
  - Cache responses for efficiency
  - Rate limiting

- **`version_chain.py`**: Builds version chains linking drafts to final resolutions
  - Parse document symbols
  - Group versions by base symbol
  - Map drafts to resolutions using voting records
  - Track revisions, addenda, and corrigenda

- **`document_downloader.py`**: Downloads PDF documents
  - Download from UN Digital Library/ODS
  - Organize by session and committee
  - Track download progress
  - Handle retries and errors

### 3. Scripts

- **`pilot_collection.py`**: Complete pilot collection pipeline
  - Collect metadata for a session
  - Build version chains
  - Optionally download documents
  - Generate statistics and validation samples

### 4. Tests

- **`tests/test_modules.py`**: Unit tests for all modules

## Installation

### Requirements

```bash
pip install requests
```

Optional for testing:
```bash
pip install pytest
```

### Setup

1. Clone the repository
2. Navigate to the scrape directory
3. Run the pilot collection script

## Usage

### Quick Start: Pilot Collection

Collect metadata for the 78th session (without downloading documents):

```bash
python pilot_collection.py --session 78
```

Collect metadata and download documents:

```bash
python pilot_collection.py --session 78 --download
```

Limit downloads for testing:

```bash
python pilot_collection.py --session 78 --download --max-downloads 10
```

### Using Individual Modules

#### Metadata Collection

```python
from metadata_collector import UNMetadataCollector

collector = UNMetadataCollector()

# Get all resolutions for session 78
resolutions = collector.get_session_resolutions(78)

# Get Third Committee drafts
drafts = collector.get_committee_drafts(3, 78)

# Get voting records
voting_records = collector.get_voting_records(78)

# Save metadata
from pathlib import Path
collector.save_metadata(resolutions, Path("data/resolutions.json"))
```

#### Version Chain Building

```python
from version_chain import VersionChainBuilder

builder = VersionChainBuilder()

# Build chains
chains = builder.build_all_chains(resolutions, drafts, voting_records)

# Get statistics
stats = builder.get_statistics(chains)
print(stats)

# Save chains
builder.save_chains(chains, Path("data/chains.json"))
```

#### Document Downloading

```python
from document_downloader import UNDocumentDownloader

downloader = UNDocumentDownloader()

# Download single document
path = downloader.download_document("A/RES/78/243")

# Batch download
successful, failed = downloader.batch_download(metadata_list)

# Download version chain
downloads = downloader.download_version_chain(chain_data)
```

## Output Structure

```
data/
├── metadata/
│   ├── sessions/
│   │   ├── 78_resolutions.json
│   │   ├── 78_committee_1_drafts.json
│   │   ├── ...
│   │   └── 78_complete_metadata.json
│   └── version_chains/
│       └── 78_chains.json
├── documents/
│   └── pdfs/
│       └── session_78/
│           ├── committee_1/
│           ├── committee_2/
│           ├── ...
│           └── plenary/
├── cache/
│   └── (API response cache)
└── logs/
    ├── pilot_collection.log
    └── downloads.json
```

## Testing

Run unit tests:

```bash
python -m pytest tests/test_modules.py -v
```

Or directly:

```bash
python tests/test_modules.py
```

## Data Flow

1. **Metadata Collection**
   - Query UN Digital Library API by session
   - Collect resolutions, drafts, and voting records
   - Parse MARCXML responses
   - Cache responses locally

2. **Version Chain Building**
   - Group drafts by base symbol
   - Map drafts to final resolutions using voting records
   - Sort versions chronologically
   - Build complete chains: draft → revisions → final

3. **Document Download** (Optional)
   - Download PDFs for all documents in chains
   - Organize by session and committee
   - Track success/failure
   - Log all downloads

## Document Symbol Patterns

### Resolutions
- Pattern: `A/RES/{session}/{number}`
- Example: `A/RES/78/243`

### Draft Resolutions
- Committee: `A/C.{1-6}/{session}/L.{number}`
- Plenary: `A/{session}/L.{number}`
- Example: `A/C.3/78/L.60`

### Revisions
- Pattern: `{base}/Rev.{number}`
- Example: `A/C.3/78/L.60/Rev.1`

### Other Modifications
- Addendum: `{base}/Add.{number}`
- Corrigendum: `{base}/Corr.{number}`
- Amendment: `{base}/Amend.{number}`

## API Rate Limiting

The scraper implements rate limiting to avoid overwhelming UN servers:

- **Metadata collection**: 0.5 seconds between requests
- **Document downloads**: 1.0 seconds between requests
- **Automatic retries**: Up to 3 attempts with exponential backoff

## Caching

- API responses are cached locally in `data/cache/`
- Downloaded documents are checked before re-downloading
- Download history tracked in `data/logs/downloads.json`

## Validation

The pilot collection script displays sample version chains for manual validation:

```bash
python pilot_collection.py --session 78 --validate 10
```

This shows 10 sample chains with their version sequences for verification.

## Troubleshooting

### No drafts found for resolutions

This can happen if:
1. Voting records don't contain draft symbols
2. Drafts use different naming conventions
3. Documents are from before digital library coverage (pre-1993)

Solution: The scraper still creates chains with just the resolution.

### Download failures

Common causes:
1. Document not available as PDF
2. Network issues
3. URL construction issues (need record ID)

Solution: Check `data/logs/downloads.json` for error details. Failed downloads can be retried.

### MARCXML parsing issues

If metadata seems incomplete:
1. Check the raw XML in cache directory
2. Verify MARC field mappings in `metadata_collector.py`
3. Some fields may be optional or missing for certain documents

## Future Enhancements

Potential improvements:
1. Support for other UN bodies (Security Council, ECOSOC)
2. Text extraction from PDFs
3. Diff computation between versions
4. Parallel downloads
5. Resume interrupted collections
6. Web interface for browsing chains

## References

- UN Digital Library: https://digitallibrary.un.org/
- UN ODS: https://documents.un.org/
- Research Guides: https://research.un.org/en/docs
- Document Symbols Guide: https://research.un.org/en/docs/symbols

## License

This scraper is for research purposes as part of the IGO-Gym benchmark project.

## Contact

For issues or questions, consult the project documentation or create an issue in the repository.