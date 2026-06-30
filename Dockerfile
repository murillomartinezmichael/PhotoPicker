# =============================================================================
# python.Dockerfile — production-ready Python container (FastAPI / Flask / etc.)
#
# WHY THIS FILE EXISTS
#   Reference Dockerfile for any Python service. Multi-stage build keeps the
#   final image small. Non-root user. Cached layer for deps. Healthcheck wired.
#
# Build:   docker build -f python.Dockerfile -t my-service:local .
# Run:     docker run --rm -p 8000:8000 --env-file .env my-service:local
# =============================================================================

# ---------- builder stage: install deps into a venv -------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# System build deps only (kept out of final image)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy ONLY dep manifests first → this layer caches as long as deps don't change
COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# ---------- runtime stage ---------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Run as non-root
RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

# Bring the venv from builder
COPY --from=builder /opt/venv /opt/venv

# Now copy application code (this layer rebuilds frequently — keep it last)
COPY --chown=app:app src/ ./src/

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
