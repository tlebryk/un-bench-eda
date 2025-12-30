"""Simple FastAPI-based SQL UI for exploring the UN documents database."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple, Set, Optional
import re

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from db.config import engine, get_session, get_dev_engine
from db.models import Document
from rag.text_to_sql import generate_sql
from rag.rag_summarize import summarize_results

# Check if we should use dev database
USE_DEV_DB = os.getenv('USE_DEV_DB', 'false').lower() == 'true'
if USE_DEV_DB:
    dev_engine = get_dev_engine()
    if dev_engine:
        engine = dev_engine
        print("🔧 Using development database")
    else:
        print("⚠️  USE_DEV_DB=true but DEV_DATABASE_URL not set, using production database")

# Set up logging
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "text_to_sql.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

MAX_ROWS = 500
MAX_DISPLAY_CHARS = 600
ALLOWED_PREFIXES = ("select", "with", "explain")
LONG_TEXT_COLUMNS = {
    "text",
    "context",
    "description",
    "notes",
    "summary",
    "content",
}
LONG_TEXT_PREVIEW_CHARS = 320
DOCUMENT_ID_COLUMN_HINTS = {
    "document_id",
    "doc_id",
    "source_id",
    "target_id",
    "meeting_id",
    "resolution_id",
    "draft_id",
    "agenda_id",
}
SYMBOL_PATTERN = re.compile(r"[A-Z]/[A-Z0-9]", re.IGNORECASE)

SAMPLE_QUERIES = [
    "SELECT symbol, title, date FROM documents WHERE doc_type = 'resolution' ORDER BY date DESC LIMIT 5;",
    "SELECT d.symbol, v.vote_type, a.name FROM documents d JOIN votes v ON v.document_id = d.id JOIN actors a ON a.id = v.actor_id WHERE d.symbol = 'A/RES/78/220' LIMIT 10;",
    "WITH vote_summary AS (\n    SELECT d.symbol, v.vote_type, COUNT(*) AS count\n    FROM documents d\n    JOIN votes v ON v.document_id = d.id\n    WHERE d.doc_type = 'resolution'\n    GROUP BY d.symbol, v.vote_type\n)\nSELECT * FROM vote_summary WHERE symbol = 'A/RES/78/220';",
    """WITH target_resolution AS (\n    SELECT id, symbol, title\n    FROM documents\n    WHERE symbol = 'A/RES/78/220'\n)\nSELECT 'resolution' AS link_type, doc.doc_type, doc.symbol, doc.title\nFROM target_resolution tr\nJOIN documents doc ON doc.id = tr.id\nUNION ALL\nSELECT rel.relationship_type, src.doc_type, src.symbol, COALESCE(src.title, src.doc_metadata->'metadata'->>'title') AS title\nFROM target_resolution tr\nJOIN document_relationships rel ON rel.target_id = tr.id\nJOIN documents src ON src.id = rel.source_id\nORDER BY link_type;""",
]

app = FastAPI(title="UN Documents SQL UI", description="Text-heavy SQL workbench for the UN database")


def format_value(value: Any) -> Dict[str, Any]:
    """Convert arbitrary DB values into a display-friendly payload."""
    if value is None:
        rendered = ""
    elif isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, indent=2)
    else:
        rendered = str(value)

    is_truncated = len(rendered) > MAX_DISPLAY_CHARS
    display_value = f"{rendered[:MAX_DISPLAY_CHARS]}…" if is_truncated else rendered
    return {
        "display": display_value,
        "full": rendered,
        "truncated": is_truncated,
    }


def normalize_symbol(symbol: str) -> str:
    """Normalize symbols like A_RES_78_220 -> A/RES/78/220."""
    return symbol.strip().upper().replace("\\", "/").replace("_", "/")


def looks_like_symbol(value: str) -> bool:
    """Heuristic check to avoid treating arbitrary text as a document symbol."""
    normalized = normalize_symbol(value)
    if "/" not in normalized:
        return False
    return bool(SYMBOL_PATTERN.search(normalized))


def pick_pdf_url(metadata: Dict[str, Any]) -> Optional[str]:
    """Select the best PDF URL from metadata, preferring English when available."""
    if not metadata:
        return None

    files = metadata.get("files")
    if not files:
        files = metadata.get("metadata", {}).get("files")

    if not files or not isinstance(files, list):
        return None

    def _language_key(entry: Dict[str, Any]) -> str:
        return (entry.get("language") or "").lower()

    english_entry = next((f for f in files if "english" in _language_key(f)), None)
    entry = english_entry or files[0]
    return entry.get("url")


def fetch_document_links(symbols: Set[str], ids: Set[int]) -> Tuple[Dict[str, str], Dict[int, str]]:
    """Fetch document -> PDF link mappings for the provided identifiers."""
    if not symbols and not ids:
        return {}, {}

    session = get_session()
    symbol_map: Dict[str, str] = {}
    id_map: Dict[int, str] = {}

    try:
        query_symbols = list(symbols)
        if query_symbols:
            docs = session.query(Document).filter(Document.symbol.in_(query_symbols)).all()
            for doc in docs:
                url = pick_pdf_url(doc.doc_metadata)
                if not url:
                    record_id = (doc.doc_metadata or {}).get("id") or (doc.doc_metadata or {}).get("metadata", {}).get("record_id")
                    if record_id:
                        url = f"https://digitallibrary.un.org/record/{record_id}?ln=en"
                if url:
                    symbol_map[normalize_symbol(doc.symbol)] = url
                    id_map[doc.id] = url

        remaining_ids = [doc_id for doc_id in ids if doc_id not in id_map]
        if remaining_ids:
            docs = session.query(Document).filter(Document.id.in_(remaining_ids)).all()
            for doc in docs:
                url = pick_pdf_url(doc.doc_metadata)
                if not url:
                    record_id = (doc.doc_metadata or {}).get("id") or (doc.doc_metadata or {}).get("metadata", {}).get("record_id")
                    if record_id:
                        url = f"https://digitallibrary.un.org/record/{record_id}?ln=en"
                if url:
                    symbol_map.setdefault(normalize_symbol(doc.symbol), url)
                    id_map[doc.id] = url

    finally:
        session.close()

    return symbol_map, id_map


def annotate_document_links(formatted_rows: List[Dict[str, Dict[str, Any]]], raw_rows: List[Dict[str, Any]]) -> None:
    """Attach PDF links to result cells when we can infer a document reference."""
    if not formatted_rows:
        return

    symbol_refs: Set[str] = set()
    id_refs: Set[int] = set()

    for raw_row in raw_rows:
        for column, value in raw_row.items():
            if value is None:
                continue
            column_lower = column.lower()

            if isinstance(value, str):
                if "symbol" in column_lower or looks_like_symbol(value):
                    symbol_refs.add(normalize_symbol(value))
            elif isinstance(value, int):
                if column_lower in DOCUMENT_ID_COLUMN_HINTS or column_lower.endswith("document_id") or column_lower.endswith("_doc_id"):
                    id_refs.add(value)

    symbol_map, id_map = fetch_document_links(symbol_refs, id_refs)
    if not symbol_map and not id_map:
        return

    for row_dict, raw_row in zip(formatted_rows, raw_rows):
        for column, cell in row_dict.items():
            raw_value = raw_row.get(column)
            if raw_value is None:
                continue
            column_lower = column.lower()
            link: Optional[str] = None

            if isinstance(raw_value, str):
                normalized = normalize_symbol(raw_value)
                link = symbol_map.get(normalized)
            elif isinstance(raw_value, int):
                if column_lower in DOCUMENT_ID_COLUMN_HINTS or column_lower.endswith("document_id") or column_lower.endswith("_doc_id"):
                    link = id_map.get(raw_value)

            if link:
                cell["link"] = link

def is_query_allowed(sql_query: str) -> Tuple[bool, str]:
    """Basic guardrail: restrict to read-only SQL statements."""
    stripped = sql_query.strip().lower()
    if not stripped:
        return False, "Query is empty"

    if not stripped.startswith(ALLOWED_PREFIXES):
        allowed = ", ".join(ALLOWED_PREFIXES)
        return False, f"Only read-only statements starting with {allowed} are allowed."

    return True, ""


def execute_sql(sql_query: str) -> Dict[str, Any]:
    """Execute raw SQL and return structured results."""
    with engine.connect() as connection:
        result = connection.execute(text(sql_query))
        columns = list(result.keys())
        rows = result.fetchall()

    formatted_rows = []
    raw_rows = []
    for row in rows[:MAX_ROWS]:
        row_mapping = dict(row._mapping)
        raw_rows.append(row_mapping)
        row_dict = {}
        for column in columns:
            column_lower = column.lower()
            formatted = format_value(row_mapping.get(column))

            if column_lower in LONG_TEXT_COLUMNS:
                formatted["long_column"] = True
                raw_value = row_mapping.get(column)
                if isinstance(raw_value, str) and len(raw_value) > LONG_TEXT_PREVIEW_CHARS:
                    preview = raw_value[:LONG_TEXT_PREVIEW_CHARS].rstrip()
                    formatted["display"] = f"{preview}…"
                    formatted["long_text"] = raw_value

            row_dict[column] = formatted
        formatted_rows.append(row_dict)

    annotate_document_links(formatted_rows, raw_rows)

    truncated = len(rows) > MAX_ROWS
    return {
        "columns": columns,
        "rows": formatted_rows,
        "row_count": len(rows),
        "truncated": truncated,
    }


@app.get("/healthz")
def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    demo_mode = request.query_params.get("demo", "false").lower() == "true"
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "sql_query": SAMPLE_QUERIES[0],
            "result": None,
            "error": None,
            "samples": SAMPLE_QUERIES,
            "natural_language_query": "",
            "demo_mode": demo_mode,
        },
    )


@app.post("/", response_class=HTMLResponse)
def run_query(request: Request, sql_query: str = Form(...)):
    demo_mode = request.query_params.get("demo", "false").lower() == "true"
    sql_query = sql_query.strip()
    logger.info(f"Direct SQL query: {sql_query}")
    
    allowed, message = is_query_allowed(sql_query)

    if not allowed:
        logger.warning(f"Query not allowed: {message}")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "sql_query": sql_query,
                "result": None,
                "error": message,
                "samples": SAMPLE_QUERIES,
                "natural_language_query": "",
                "demo_mode": demo_mode,
            },
            status_code=400,
        )

    try:
        result = execute_sql(sql_query)
        logger.info(f"SQL executed successfully - Rows returned: {result['row_count']}, Truncated: {result['truncated']}")
        
        context = {
            "request": request,
            "sql_query": sql_query,
            "result": result,
            "error": None,
            "samples": SAMPLE_QUERIES,
            "natural_language_query": "",
            "demo_mode": demo_mode,
        }
        return templates.TemplateResponse("index.html", context)
    except SQLAlchemyError as exc:
        logger.error(f"SQL execution failed: {str(exc)}")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "sql_query": sql_query,
                "result": None,
                "error": str(exc),
                "samples": SAMPLE_QUERIES,
                "natural_language_query": "",
                "demo_mode": demo_mode,
            },
            status_code=400,
        )


@app.post("/api/query")
def api_query(sql_query: str = Form(...)):
    """Programmatic access point for automation."""
    sql_query = sql_query.strip()
    logger.info(f"API SQL query: {sql_query}")
    
    allowed, message = is_query_allowed(sql_query)
    if not allowed:
        logger.warning(f"Query not allowed: {message}")
        return JSONResponse({"error": message}, status_code=400)

    try:
        result = execute_sql(sql_query)
        logger.info(f"SQL executed successfully - Rows returned: {result['row_count']}, Truncated: {result['truncated']}")
        
        # Convert values back to strings for JSON response
        json_rows = []
        for row in result["rows"]:
            json_rows.append({col: cell["full"] for col, cell in row.items()})

        return {
            "columns": result["columns"],
            "row_count": result["row_count"],
            "truncated": result["truncated"],
            "rows": json_rows,
        }
    except SQLAlchemyError as exc:
        logger.error(f"SQL execution failed: {str(exc)}")
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/text-to-sql")
def api_text_to_sql(natural_language_query: str = Form(None), execute: bool = Form(False)):
    """Convert natural language to SQL, optionally execute it."""
    if not natural_language_query:
        return JSONResponse({"error": "natural_language_query field is required"}, status_code=400)
    
    # Log the natural language query
    logger.info(f"Text-to-SQL API request - Natural language: {natural_language_query}")
    
    try:
        sql_query = generate_sql(natural_language_query)
        logger.info(f"Generated SQL: {sql_query}")
        
        if execute:
            allowed, message = is_query_allowed(sql_query)
            if not allowed:
                logger.warning(f"Generated query not allowed: {message}")
                return JSONResponse({
                    "error": f"Generated query not allowed: {message}", 
                    "sql": sql_query,
                    "natural_language_query": natural_language_query
                }, status_code=400)
            
            try:
                result = execute_sql(sql_query)
                logger.info(f"SQL executed successfully - Rows returned: {result['row_count']}, Truncated: {result['truncated']}")
                
                json_rows = []
                for row in result["rows"]:
                    json_rows.append({col: cell["full"] for col, cell in row.items()})
                
                return {
                    "sql": sql_query,
                    "natural_language_query": natural_language_query,
                    "columns": result["columns"],
                    "row_count": result["row_count"],
                    "truncated": result["truncated"],
                    "rows": json_rows,
                }
            except SQLAlchemyError as exc:
                logger.error(f"SQL execution failed: {str(exc)}")
                return JSONResponse({
                    "error": f"SQL execution failed: {str(exc)}", 
                    "sql": sql_query,
                    "natural_language_query": natural_language_query
                }, status_code=400)
        else:
            logger.info("SQL generated but not executed")
            return {
                "sql": sql_query,
                "natural_language_query": natural_language_query
            }
    except Exception as exc:
        logger.error(f"Text-to-SQL generation failed: {str(exc)}", exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/text-to-sql", response_class=HTMLResponse)
def text_to_sql_query(request: Request, natural_language_query: str = Form(None), execute: bool = Form(False)):
    """Convert natural language to SQL and optionally execute it."""
    demo_mode = request.query_params.get("demo", "false").lower() == "true"
    if not natural_language_query:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "sql_query": "",
                "result": None,
                "error": "natural_language_query field is required",
                "samples": SAMPLE_QUERIES,
                "natural_language_query": "",
                "demo_mode": demo_mode,
            },
            status_code=400,
        )
    
    # Log the natural language query
    logger.info(f"Text-to-SQL UI request - Natural language: {natural_language_query}")
    
    try:
        sql_query = generate_sql(natural_language_query)
        logger.info(f"Generated SQL: {sql_query}")
        
        if execute:
            allowed, message = is_query_allowed(sql_query)
            if not allowed:
                return templates.TemplateResponse(
                    "index.html",
                    {
                        "request": request,
                        "sql_query": sql_query,
                        "result": None,
                        "error": f"Generated query not allowed: {message}",
                        "samples": SAMPLE_QUERIES,
                        "natural_language_query": natural_language_query,
                        "demo_mode": demo_mode,
                    },
                    status_code=400,
                )
            
            try:
                result = execute_sql(sql_query)
                logger.info(f"SQL executed successfully - Rows returned: {result['row_count']}, Truncated: {result['truncated']}")
                
                return templates.TemplateResponse(
                    "index.html",
                    {
                        "request": request,
                        "sql_query": sql_query,
                        "result": result,
                        "error": None,
                        "samples": SAMPLE_QUERIES,
                        "natural_language_query": natural_language_query,
                        "demo_mode": demo_mode,
                    },
                )
            except SQLAlchemyError as exc:
                logger.error(f"SQL execution failed: {str(exc)}")
                return templates.TemplateResponse(
                    "index.html",
                    {
                        "request": request,
                        "sql_query": sql_query,
                        "result": None,
                        "error": f"SQL execution failed: {str(exc)}",
                        "samples": SAMPLE_QUERIES,
                        "natural_language_query": natural_language_query,
                        "demo_mode": demo_mode,
                    },
                    status_code=400,
                )
        else:
            # Just show the generated SQL
            logger.info("SQL generated but not executed")
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "sql_query": sql_query,
                    "result": None,
                    "error": None,
                    "samples": SAMPLE_QUERIES,
                    "natural_language_query": natural_language_query,
                    "demo_mode": demo_mode,
                },
            )
    except Exception as exc:
        logger.error(f"Text-to-SQL generation failed: {str(exc)}", exc_info=True)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "sql_query": "",
                "result": None,
                "error": f"Failed to generate SQL: {str(exc)}",
                "samples": SAMPLE_QUERIES,
                "natural_language_query": natural_language_query,
                "demo_mode": demo_mode,
            },
            status_code=500,
        )


@app.post("/api/summarize")
def api_summarize(
    sql_query: str = Form(None),
    natural_language_query: str = Form(None),
    result_json: str = Form(None)
):
    """
    Summarize SQL query results using RAG.
    
    Requires:
    - Either sql_query (for direct SQL) or natural_language_query (for text-to-SQL)
    - result_json: JSON string of the query results from execute_sql
    """
    logger.info(f"Summarization API request - SQL: {sql_query}, NL: {natural_language_query}")
    
    # Determine the original question
    original_question = natural_language_query or "Summarize these results"
    
    if not result_json:
        return JSONResponse({"error": "result_json field is required"}, status_code=400)
    
    try:
        # Parse the result JSON
        result = json.loads(result_json)
        
        # Summarize the results
        summary = summarize_results(result, original_question)
        
        return {
            "summary": summary,
            "original_question": original_question,
            "row_count": result.get("row_count", 0)
        }
    except json.JSONDecodeError as exc:
        logger.error(f"Invalid JSON in result_json: {str(exc)}")
        return JSONResponse({"error": f"Invalid JSON: {str(exc)}"}, status_code=400)
    except Exception as exc:
        logger.error(f"Summarization failed: {str(exc)}", exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)
