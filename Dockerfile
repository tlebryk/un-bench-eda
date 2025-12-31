# Multi-stage Dockerfile for UN Documents FastAPI Application
# Uses uv for fast, reliable dependency management
# Optimized for Render.com deployment

# Stage 1: Builder - Install dependencies with uv
FROM python:3.13-slim AS builder

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set uv environment variables for production
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

WORKDIR /app

# Install system dependencies for psycopg2 and pdfplumber
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (better caching - these change less often)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

# Copy application code
COPY . /app

# Install the project (runs fast since dependencies already installed)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# Stage 2: Runtime - Minimal production image
FROM python:3.13-slim

WORKDIR /app

# Install runtime dependencies only (no gcc, build tools)
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code (ui/, db/, rag/ modules needed by the app)
COPY ui/ ./ui/
COPY db/ ./db/
COPY rag/ ./rag/

# Create necessary directories for logs
RUN mkdir -p /app/logs /app/rag/logs

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Add venv to PATH so we can run uvicorn directly
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app

# Health check endpoint (used by Render)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:' + str(${PORT:-8000}) + '/healthz').read()" || exit 1

# Render provides $PORT environment variable, default to 8000 for local testing
CMD ["sh", "-c", "uvicorn ui.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
