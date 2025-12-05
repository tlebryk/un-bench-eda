"""Simple FastAPI-based SQL UI for exploring the UN documents database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from db.config import engine
from text_to_sql import generate_sql

APP_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

MAX_ROWS = 500
MAX_DISPLAY_CHARS = 600
ALLOWED_PREFIXES = ("select", "with", "explain")

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
    for row in rows[:MAX_ROWS]:
        row_dict = {}
        for column in columns:
            row_dict[column] = format_value(row._mapping[column])
        formatted_rows.append(row_dict)

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
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "sql_query": SAMPLE_QUERIES[0],
            "result": None,
            "error": None,
            "samples": SAMPLE_QUERIES,
        },
    )


@app.post("/", response_class=HTMLResponse)
def run_query(request: Request, sql_query: str = Form(...)):
    sql_query = sql_query.strip()
    allowed, message = is_query_allowed(sql_query)

    if not allowed:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "sql_query": sql_query,
                "result": None,
                "error": message,
                "samples": SAMPLE_QUERIES,
            },
            status_code=400,
        )

    try:
        result = execute_sql(sql_query)
        context = {
            "request": request,
            "sql_query": sql_query,
            "result": result,
            "error": None,
            "samples": SAMPLE_QUERIES,
        }
        return templates.TemplateResponse("index.html", context)
    except SQLAlchemyError as exc:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "sql_query": sql_query,
                "result": None,
                "error": str(exc),
                "samples": SAMPLE_QUERIES,
            },
            status_code=400,
        )


@app.post("/api/query")
def api_query(sql_query: str = Form(...)):
    """Programmatic access point for automation."""
    sql_query = sql_query.strip()
    allowed, message = is_query_allowed(sql_query)
    if not allowed:
        return JSONResponse({"error": message}, status_code=400)

    try:
        result = execute_sql(sql_query)
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
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/text-to-sql")
def api_text_to_sql(natural_language_query: str = Form(...), execute: bool = Form(False)):
    """Convert natural language to SQL, optionally execute it."""
    try:
        sql_query = generate_sql(natural_language_query)
        
        if execute:
            allowed, message = is_query_allowed(sql_query)
            if not allowed:
                return JSONResponse({"error": f"Generated query not allowed: {message}", "sql": sql_query}, status_code=400)
            
            try:
                result = execute_sql(sql_query)
                json_rows = []
                for row in result["rows"]:
                    json_rows.append({col: cell["full"] for col, cell in row.items()})
                
                return {
                    "sql": sql_query,
                    "columns": result["columns"],
                    "row_count": result["row_count"],
                    "truncated": result["truncated"],
                    "rows": json_rows,
                }
            except SQLAlchemyError as exc:
                return JSONResponse({"error": f"SQL execution failed: {str(exc)}", "sql": sql_query}, status_code=400)
        else:
            return {"sql": sql_query}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/text-to-sql", response_class=HTMLResponse)
def text_to_sql_query(request: Request, natural_language_query: str = Form(...), execute: bool = Form(False)):
    """Convert natural language to SQL and optionally execute it."""
    try:
        sql_query = generate_sql(natural_language_query)
        
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
                    },
                    status_code=400,
                )
            
            try:
                result = execute_sql(sql_query)
                return templates.TemplateResponse(
                    "index.html",
                    {
                        "request": request,
                        "sql_query": sql_query,
                        "result": result,
                        "error": None,
                        "samples": SAMPLE_QUERIES,
                        "natural_language_query": natural_language_query,
                    },
                )
            except SQLAlchemyError as exc:
                return templates.TemplateResponse(
                    "index.html",
                    {
                        "request": request,
                        "sql_query": sql_query,
                        "result": None,
                        "error": f"SQL execution failed: {str(exc)}",
                        "samples": SAMPLE_QUERIES,
                        "natural_language_query": natural_language_query,
                    },
                    status_code=400,
                )
        else:
            # Just show the generated SQL
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "sql_query": sql_query,
                    "result": None,
                    "error": None,
                    "samples": SAMPLE_QUERIES,
                    "natural_language_query": natural_language_query,
                },
            )
    except Exception as exc:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "sql_query": "",
                "result": None,
                "error": f"Failed to generate SQL: {str(exc)}",
                "samples": SAMPLE_QUERIES,
                "natural_language_query": natural_language_query,
            },
            status_code=500,
        )
