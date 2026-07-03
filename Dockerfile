# =============================================================================
# PhotoPicker — CLI container. PhotoPicker is a library first (pyproject.toml)
# and a `photopicker` CLI second. The container gives CI + downstream projects
# a hermetic way to run the CLI without setting up Python locally.
#
# Build:   docker build -t photopicker:local .
# Run:     docker run --rm -v /path/to/photos:/photos photopicker:local \
#            photopicker --profile aries --input /photos --out /photos/out
# =============================================================================

# ---------- builder stage: install PhotoPicker as a wheel -------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Deps for the core install come from pyproject.toml. Copy metadata + package
# first so this layer caches as long as pyproject.toml doesn't change.
COPY pyproject.toml README.md ./
COPY photopicker/ ./photopicker/

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .

# ---------- runtime stage ---------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# libGL is required by opencv-python at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

USER app

# Default: print CLI help. Override in `docker run` with real args.
ENTRYPOINT ["photopicker"]
CMD ["--help"]
