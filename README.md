# UN Document Scraper

A modular scraper for collecting UN General Assembly documents and building version history chains for the IGO-Gym benchmark project.

This project provides a set of Python scripts to fetch, parse, and download UN documents from the UN Digital Library.

For the full research context, see [project.md](project.md).

## Quick Start

A 3-stage pipeline is used to collect the documents:
1. **`fetch_metadata.py`**: Fetches XML from the UN Digital Library API.
2. **`parse_metadata.py`**: Parses the XML to create a JSON file with PDF URLs.
3. **`download_pdfs.py`**: Downloads the PDFs.

### Run a quick test

To verify the pipeline is working, run the test script:
```bash
bash test_pipeline.sh
```
This will download 3 PDFs to the `data/documents/pdfs/resolutions/` directory.

### Collect documents

A convenience script is provided to collect documents from multiple sessions:
```bash
# Collect documents for sessions 75, 76, 77, 78, 79
SESSIONS="75 76 77 78 79" bash collect_multiple_sessions.sh
```

## Project Structure

*   `fetch_metadata.py`, `parse_metadata.py`, `download_pdfs.py`: The main pipeline scripts.
*   `collect_multiple_sessions.sh`: A shell script to automate collection of multiple sessions.
*   `test_pipeline.sh`: A shell script to run a quick test of the pipeline.
*   `data/`: The directory where all collected data is stored.
*   `project.md`: The high-level research project description.
*   `un_document_structure.md`: A reference guide on how UN documents are structured and named.
*   `DEVELOPMENT.md`: A detailed guide for developers who want to modify or extend the scraper.

## For Developers

For more detailed technical information, including the architecture, known issues, and future enhancements, see [DEVELOPMENT.md](DEVELOPMENT.md).