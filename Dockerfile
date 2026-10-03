# syntax=docker/dockerfile:1.7
# Collections 360: Python images. Targets: api | jobs | test.
#   docker build --target api  -t c360-api  .
#   docker build --target jobs -t c360-jobs .

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

# ---- base: uv + runtime env, non-root user ---------------------------------------------------
FROM ${PYTHON_IMAGE} AS py-base
COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    HF_HOME=/app/.cache/models \
    FASTEMBED_CACHE_PATH=/app/.cache/models
RUN useradd --create-home --uid 1000 app && mkdir -p /app && chown app:app /app
WORKDIR /app

# ---- api deps: core + ml + rag + llm (no dbt/Splink) ------------------------------------------
FROM py-base AS api-deps
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra ml --extra rag --extra llm

# ---- jobs deps: api deps + pipeline (dbt-duckdb, Splink); causal (EconML) opt-in -------------
FROM api-deps AS jobs-deps
ARG JOBS_EXTRAS="--extra pipeline"
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra ml --extra rag --extra llm ${JOBS_EXTRAS}

# Writable dirs that named volumes mount over (a new volume inherits this ownership).
FROM py-base AS dirs
RUN mkdir -p /app/data /app/reports /app/models/ptp_break/artefacts /app/.cache/models \
 && chown -R app:app /app

# ---- api ---------------------------------------------------------------------------------
FROM api-deps AS api
COPY --from=dirs --chown=app:app /app /app
COPY --chown=app:app . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra ml --extra rag --extra llm
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# ---- jobs (run-to-completion batch: `jobs nightly`, `jobs profile`, ...) ---------------------
FROM jobs-deps AS jobs
ARG JOBS_EXTRAS="--extra pipeline"
COPY --from=dirs --chown=app:app /app /app
COPY --chown=app:app . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra ml --extra rag --extra llm ${JOBS_EXTRAS} \
 && install -m 0755 docker/jobs-entrypoint.sh /usr/local/bin/jobs
USER app
ENTRYPOINT ["jobs"]
CMD ["help"]

# ---- test (jobs image + dev group: pytest, ruff) ------------------------------------------
FROM jobs AS test
USER root
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra ml --extra rag --extra llm --extra pipeline
USER app
ENTRYPOINT []
CMD ["pytest"]
