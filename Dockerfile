# Etki application image. The container ships no JVM → the code graph uses the `ast`
# adapter (connectors.docker.yaml). Live Joern indexing is a separate step (see docs/RUNBOOK.md).
# For production, pin the base image by digest, e.g. FROM python:3.12-slim@sha256:...
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies (building the package needs the sources + readme)
COPY pyproject.toml uv.lock README.md CLAUDE.md ./
COPY etki ./etki
# uv workspace members (etki-api is a runtime dep; the lockfile references
# packages/* so the members must exist for `uv sync --frozen` to resolve).
COPY packages ./packages
COPY config ./config
COPY samples ./samples
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev

# NON-root user + ownership of the writable directories (security hardening).
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data /app/.etki \
    && chown -R app:app /app
USER app

ENV ETKI_CONNECTORS_PATH=config/connectors.docker.yaml \
    ETKI_DB_URL=sqlite:////app/data/etki.db \
    ETKI_FORCE_CODE_ENGINE=ast
# ↑ No JVM in the container → even if projects.yaml says 'joern', the code graph is built with 'ast'.

EXPOSE 8000

# Container health: /ready checks DB + engines are up (compose probes this too).
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/ready').status==200 else 1)"]

# On start: schema migration (alembic) → then the server. The schema evolves under control.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn etki.api.app:app --host 0.0.0.0 --port 8000"]
