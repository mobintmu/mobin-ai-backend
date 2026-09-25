FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM python:3.12-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim
RUN useradd --system --uid 10001 --home /app app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY app ./app
COPY alembic ./alembic
COPY scripts ./scripts
COPY knowledge ./knowledge
COPY alembic.ini ./
ENV PATH=/app/.venv/bin:$PATH PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--limit-concurrency", "50", "--timeout-graceful-shutdown", "30"]
