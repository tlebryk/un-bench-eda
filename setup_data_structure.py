"""
Setup proper data directory structure for UN document scraper.
"""

from pathlib import Path

def create_data_structure():
    """Create organized directory structure for data storage."""

    base = Path("data")

    # Top-level directories
    dirs = [
        # Raw API responses (XML)
        "data/raw/xml",

        # Parsed metadata (JSON)
        "data/parsed/metadata",

        # Downloaded documents
        "data/documents/pdfs/resolutions",
        "data/documents/pdfs/drafts",

        # Version chains
        "data/processed/version_chains",

        # Logs
        "data/logs",

        # Test/temporary files
        "data/test",
    ]

    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"✓ Created: {dir_path}")

    # Create README in data directory
    readme_content = """# UN Document Scraper - Data Directory

## Structure

```
data/
├── raw/
│   └── xml/               # Raw MARCXML responses from UN API
│       ├── session_78_resolutions.xml
│       └── session_78_committee_*_drafts.xml
│
├── parsed/
│   └── metadata/          # Parsed JSON metadata with PDF URLs
│       ├── session_78_resolutions.json
│       └── session_78_committee_*_drafts.json
│
├── documents/
│   └── pdfs/             # Downloaded PDF files
│       ├── resolutions/  # Final adopted resolutions
│       └── drafts/       # Draft documents and revisions
│
├── processed/
│   └── version_chains/   # Built version chains (draft → final)
│       └── session_78_chains.json
│
├── logs/                 # Execution logs
│   ├── fetch.log
│   ├── parse.log
│   └── download.log
│
└── test/                 # Test and temporary files
    └── (scratch space)
```

## File Naming Conventions

### Raw XML
- Resolutions: `session_{N}_resolutions.xml`
- Committee drafts: `session_{N}_committee_{C}_drafts.xml`
- Voting records: `session_{N}_voting.xml`

### Parsed JSON
- Same as XML but with `.json` extension

### PDFs
- Symbol-based: `{SANITIZED_SYMBOL}.pdf`
- Example: `A_RES_78_242_A.pdf`

## Session Numbers

- 78: 2023-2024
- 79: 2024-2025 (ongoing)
- 77: 2022-2023
- etc.

## Data Provenance

All data sourced from UN Digital Library: https://digitallibrary.un.org/
API Documentation: https://digitallibrary.un.org/help/search-engine-api
"""

    (base / "README.md").write_text(readme_content)
    print(f"✓ Created: data/README.md")

    print("\n✅ Data directory structure ready!")
    print("\nNext steps:")
    print("  1. Run: python fetch_metadata.py 78 --base-dir data")
    print("  2. Run: python parse_metadata.py data/raw/xml/session_78_resolutions.xml")
    print("  3. Run: python download_pdfs.py data/parsed/metadata/session_78_resolutions.json")

if __name__ == "__main__":
    create_data_structure()
