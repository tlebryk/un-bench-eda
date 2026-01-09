"""Simple FastAPI-based SQL UI for exploring the UN documents database."""

from __future__ import annotations

import json
import logging
import os
import secrets
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple, Set, Optional
import re
from urllib.parse import quote, urlparse

from fastapi import FastAPI, Form, Request, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from db.config import engine, get_session, is_supabase, USE_DEV_DB
from db.models import Document
from rag.text_to_sql import generate_sql
from rag.rag_summarize import summarize_results
from rag.rag_qa import answer_question

# Set up logging
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Log connection status on startup
if is_supabase and not USE_DEV_DB:
    logger.info("🚀 Starting UI with PRODUCTION database (Supabase)")
elif USE_DEV_DB:
    logger.info("🚀 Starting UI with DEVELOPMENT database")
else:
    logger.info("🚀 Starting UI with LOCAL database")

# Will be set after RAG_PROMPT_STYLE is defined below
_logged_prompt_style = False

APP_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

# Verify static directory exists
STATIC_DIR = APP_DIR / "static"
if not STATIC_DIR.exists():
    logger.warning(f"Static directory not found at {STATIC_DIR}")
else:
    logger.info(f"Static directory found at {STATIC_DIR}")

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

# Example questions for demo mode
DEMO_QUESTIONS = [
    "Why did countries vote against A/RES/78/220?",
    "Which countries abstained from voting on Iran-related resolutions in session 78?",
    "What did France say about climate change in plenary meetings?",
    "Show me all resolutions about human rights in session 78",
]

app = FastAPI(title="UN Documents SQL UI", description="Text-heavy SQL workbench for the UN database")

# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    logger.info(f"Mounted static files from {STATIC_DIR}")
else:
    logger.error(f"Cannot mount static files: directory {STATIC_DIR} does not exist")

# Authentication setup (feature flag controlled)
ENABLE_AUTH = os.getenv('ENABLE_AUTH', 'true').lower() == 'true'
SHARED_PASSWORD = os.getenv('SHARED_PASSWORD', '')
SESSION_COOKIE_NAME = "ui_session"
SESSION_COOKIE_MAX_AGE = 12 * 60 * 60  # 12 hours

# RAG prompt style configuration
RAG_PROMPT_STYLE = os.getenv('RAG_PROMPT_STYLE', 'analytical')
logger.info(f"📝 RAG prompt style: {RAG_PROMPT_STYLE}")

if ENABLE_AUTH and not SHARED_PASSWORD:
    raise RuntimeError("ENABLE_AUTH is true but SHARED_PASSWORD is not set")


def _session_token() -> Optional[str]:
    password = SHARED_PASSWORD
    if not password:
        return None
    payload = f"un-draft-ui::{password}"
    return hashlib.sha256(payload.encode()).hexdigest()


SESSION_TOKEN = _session_token()


def is_authenticated(request: Request) -> bool:
    if not ENABLE_AUTH:
        return True
    expected = SESSION_TOKEN
    if not expected:
        return False
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return False
    return secrets.compare_digest(token, expected)


def require_auth(request: Request):
    if not ENABLE_AUTH:
        return True
    if is_authenticated(request):
        return True

    path = request.url.path or "/"
    if request.url.query:
        path = f"{path}?{request.url.query}"
    login_url = f"/login?next={quote(path, safe='')}"
    raise HTTPException(
        status_code=status.HTTP_302_FOUND,
        detail="Authentication required",
        headers={"Location": login_url},
    )


def _safe_next_url(next_url: Optional[str]) -> str:
    """Prevent open redirect by only allowing relative paths."""
    if not next_url:
        return "/"
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        return "/"
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    if not path.startswith("/"):
        path = "/"
    return f"{path}{query}"


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


def symbol_to_docs_url(symbol: str, language: str = "en") -> str:
    """
    Convert UN document symbol to documents.un.org API URL for PDF access.
    
    Uses the Official Document System (ODS) API which reliably serves PDFs.
    
    Args:
        symbol: UN document symbol (e.g., A/RES/78/276)
        language: Language code (default: en)
    
    Returns:
        URL to PDF at documents.un.org API
    """
    # Convert RES to lowercase res, keep everything else as-is
    symbol_lower = symbol.replace('/RES/', '/res/')
    # Construct ODS API URL
    return f"https://documents.un.org/api/symbol/access?s={symbol_lower}&l={language}&t=pdf"


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
                    # Fallback: Use ODS URL (reliable for most document types)
                    if doc.symbol:
                        url = symbol_to_docs_url(doc.symbol, language="en")
                if url:
                    symbol_map[normalize_symbol(doc.symbol)] = url
                    id_map[doc.id] = url

        remaining_ids = [doc_id for doc_id in ids if doc_id not in id_map]
        if remaining_ids:
            docs = session.query(Document).filter(Document.id.in_(remaining_ids)).all()
            for doc in docs:
                url = pick_pdf_url(doc.doc_metadata)
                if not url:
                    # Fallback: Use ODS URL (reliable for most document types)
                    if doc.symbol:
                        url = symbol_to_docs_url(doc.symbol, language="en")
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


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    target = _safe_next_url(next)
    if not ENABLE_AUTH or is_authenticated(request):
        return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None,
            "next": target,
        },
    )


@app.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, password: str = Form(...), next: str = Form("/")):
    target = _safe_next_url(next)
    if not ENABLE_AUTH:
        return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)

    if not secrets.compare_digest(password, SHARED_PASSWORD):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Incorrect password",
                "next": target,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = SESSION_TOKEN
    if not token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Authentication not configured")
    response = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


def _logout_response(next_value: str) -> RedirectResponse:
    target = _safe_next_url(next_value)
    response = RedirectResponse(
        f"/login?next={quote(target, safe='')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.post("/logout")
def logout_post(next: str = Form("/")):
    return _logout_response(next)


@app.get("/logout")
def logout_get(next: str = "/"):
    return _logout_response(next)


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
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
            "demo_questions": DEMO_QUESTIONS,
            "rag_answer": None,
        },
    )


@app.post("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
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
                "demo_questions": DEMO_QUESTIONS,
                "rag_answer": None,
            },
            status_code=400,
        )


@app.post("/rag-answer", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def rag_answer_query(
    request: Request,
    natural_language_query: str = Form(None),
    sql_query: str = Form(None),
    result_json: str = Form(None)
):
    """Answer a question using RAG with evidence grounding (HTML response)."""
    demo_mode = request.query_params.get("demo", "false").lower() == "true"
    
    try:
        result = None
        final_sql_query = sql_query
        
        # If natural language query provided, generate and execute SQL
        if natural_language_query:
            if not sql_query:
                final_sql_query = generate_sql(natural_language_query)
                logger.info(f"Generated SQL: {final_sql_query}")
            
            if final_sql_query:
                allowed, message = is_query_allowed(final_sql_query)
                if not allowed:
                    return templates.TemplateResponse(
                        "index.html",
                        {
                            "request": request,
                            "sql_query": final_sql_query,
                            "result": None,
                            "error": f"Query not allowed: {message}",
                            "samples": SAMPLE_QUERIES,
                            "natural_language_query": natural_language_query,
                            "demo_mode": demo_mode,
                            "demo_questions": DEMO_QUESTIONS,
                            "rag_answer": None,
                        },
                        status_code=400,
                    )
                
                result = execute_sql(final_sql_query)
                logger.info(f"SQL executed - Rows: {result['row_count']}")
        
        elif result_json:
            result = json.loads(result_json)
        
        if not result:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "sql_query": sql_query or "",
                    "result": None,
                    "error": "Either natural_language_query or result_json must be provided",
                    "samples": SAMPLE_QUERIES,
                    "natural_language_query": natural_language_query or "",
                    "demo_mode": demo_mode,
                    "demo_questions": DEMO_QUESTIONS,
                    "rag_answer": None,
                },
                status_code=400,
            )
        
        original_question = natural_language_query or "Answer based on these results"
        
        # Call RAG Q&A
        rag_answer = answer_question(
            query_results=result,
            original_question=original_question,
            sql_query=final_sql_query,
            prompt_style=RAG_PROMPT_STYLE
        )
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "sql_query": final_sql_query or sql_query or "",
                "result": result,
                "error": None,
                "samples": SAMPLE_QUERIES,
                "natural_language_query": original_question,
                "demo_mode": demo_mode,
                "demo_questions": DEMO_QUESTIONS,
                "rag_answer": rag_answer,
            },
        )
    
    except json.JSONDecodeError as exc:
        logger.error(f"Invalid JSON: {str(exc)}")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "sql_query": sql_query or "",
                "result": None,
                "error": f"Invalid JSON: {str(exc)}",
                "samples": SAMPLE_QUERIES,
                "natural_language_query": natural_language_query or "",
                "demo_mode": demo_mode,
                "demo_questions": DEMO_QUESTIONS,
                "rag_answer": None,
            },
            status_code=400,
        )
    except Exception as exc:
        logger.error(f"RAG Q&A failed: {str(exc)}", exc_info=True)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "sql_query": sql_query or "",
                "result": None,
                "error": f"Failed to answer question: {str(exc)}",
                "samples": SAMPLE_QUERIES,
                "natural_language_query": natural_language_query or "",
                "demo_mode": demo_mode,
                "demo_questions": DEMO_QUESTIONS,
                "rag_answer": None,
            },
            status_code=500,
        )


@app.post("/api/query", dependencies=[Depends(require_auth)])
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


@app.post("/api/text-to-sql", dependencies=[Depends(require_auth)])
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


@app.post("/text-to-sql", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
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
                "demo_questions": DEMO_QUESTIONS,
                "rag_answer": None,
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
                        "demo_questions": DEMO_QUESTIONS,
                        "rag_answer": None,
                    },
                    status_code=400,
                )
            
            try:
                result = execute_sql(sql_query)
                logger.info(f"SQL executed successfully - Rows returned: {result['row_count']}, Truncated: {result['truncated']}")
                
                # In demo mode, auto-trigger RAG Q&A
                rag_answer = None
                if demo_mode:
                    try:
                        rag_answer = answer_question(
                            query_results=result,
                            original_question=natural_language_query,
                            sql_query=sql_query,
                            prompt_style=RAG_PROMPT_STYLE
                        )
                        logger.info(f"RAG Q&A completed - Sources: {len(rag_answer.get('sources', []))}")
                    except Exception as rag_exc:
                        logger.warning(f"RAG Q&A failed in demo mode: {str(rag_exc)}")
                        # Continue without RAG answer
                
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
                        "demo_questions": DEMO_QUESTIONS,
                        "rag_answer": rag_answer,
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
                        "demo_questions": DEMO_QUESTIONS,
                        "rag_answer": None,
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
                    "demo_questions": DEMO_QUESTIONS,
                    "rag_answer": None,
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
                "demo_questions": DEMO_QUESTIONS,
                "rag_answer": None,
            },
            status_code=500,
        )


@app.post("/api/summarize", dependencies=[Depends(require_auth)])
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


@app.post("/api/rag-answer", dependencies=[Depends(require_auth)])
def api_rag_answer(
    natural_language_query: str = Form(None),
    sql_query: str = Form(None),
    result_json: str = Form(None)
):
    """
    Answer a question using RAG with evidence grounding.
    
    Accepts either:
    - natural_language_query: Generate SQL, execute, then answer
    - sql_query + result_json: Use existing query results to answer
    
    Returns structured answer with citations.
    """
    logger.info(f"RAG Q&A API request - NL: {natural_language_query}, SQL: {sql_query}")
    
    try:
        result = None
        final_sql_query = sql_query
        
        # If natural language query provided, generate and execute SQL
        if natural_language_query:
            if not sql_query:
                # Generate SQL from natural language
                final_sql_query = generate_sql(natural_language_query)
                logger.info(f"Generated SQL: {final_sql_query}")
            
            # Execute SQL if we have a query
            if final_sql_query:
                allowed, message = is_query_allowed(final_sql_query)
                if not allowed:
                    return JSONResponse({
                        "error": f"Query not allowed: {message}",
                        "sql": final_sql_query,
                        "natural_language_query": natural_language_query
                    }, status_code=400)
                
                result = execute_sql(final_sql_query)
                logger.info(f"SQL executed - Rows: {result['row_count']}")
        
        # If result_json provided, parse it
        elif result_json:
            result = json.loads(result_json)
        
        if not result:
            return JSONResponse({
                "error": "Either natural_language_query or result_json must be provided"
            }, status_code=400)
        
        # Determine original question
        original_question = natural_language_query or "Answer based on these results"
        
        # Call RAG Q&A
        rag_response = answer_question(
            query_results=result,
            original_question=original_question,
            sql_query=final_sql_query,
            prompt_style=RAG_PROMPT_STYLE
        )
        
        return {
            "answer": rag_response["answer"],
            "evidence": rag_response["evidence"],
            "sources": rag_response["sources"],
            "original_question": original_question,
            "sql": final_sql_query,
            "row_count": result.get("row_count", 0)
        }
    
    except json.JSONDecodeError as exc:
        logger.error(f"Invalid JSON in result_json: {str(exc)}")
        return JSONResponse({"error": f"Invalid JSON: {str(exc)}"}, status_code=400)
    except Exception as exc:
        logger.error(f"RAG Q&A failed: {str(exc)}", exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)

# Multi-step RAG endpoints

@app.post("/api/multistep-answer", dependencies=[Depends(require_auth)])
def api_multistep_answer(natural_language_query: str = Form(...)):
    """Multi-step RAG with automatic tool selection."""
    from rag.multistep.orchestrator import MultiStepOrchestrator

    logger.info(f"Multi-step query: {natural_language_query}")

    try:
        orchestrator = MultiStepOrchestrator()
        result = orchestrator.answer_multistep(natural_language_query)

        return {
            "answer": result["answer"],
            "evidence": result["evidence"],
            "sources": result["sources"],
            "steps": result["steps"],
            "row_count": len(result.get("evidence", []))
        }
    except Exception as exc:
        logger.error(f"Multi-step query failed: {str(exc)}", exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/multistep-answer", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def multistep_answer_html(request: Request, natural_language_query: str = Form(...)):
    """HTML version of multi-step RAG."""
    from rag.multistep.orchestrator import MultiStepOrchestrator

    demo_mode = request.query_params.get("demo", "false").lower() == "true"

    try:
        orchestrator = MultiStepOrchestrator()
        result = orchestrator.answer_multistep(natural_language_query)

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "natural_language_query": natural_language_query,
                "rag_answer": result,
                "demo_mode": demo_mode,
                "demo_questions": DEMO_QUESTIONS,
                "samples": SAMPLE_QUERIES,
                "sql_query": "", # Multi-step doesn't have a single SQL query
                "result": None,
                "error": None
            },
        )
    except Exception as exc:
        logger.error(f"Multi-step query failed: {str(exc)}", exc_info=True)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": f"Multi-step query failed: {str(exc)}",
                "natural_language_query": natural_language_query,
                "demo_mode": demo_mode,
                "samples": SAMPLE_QUERIES,
                "demo_questions": DEMO_QUESTIONS,
                "rag_answer": None,
                "sql_query": "",
                "result": None,
            },
            status_code=500,
        )
