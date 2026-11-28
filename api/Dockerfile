# The API image for Cloud Run. Build from the repository root, which holds the shared catalog:
#   docker build -f api/Dockerfile -t ritis-api .

FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv
WORKDIR /app
# The interpreter of the image, bytecode compiled at build time, the package copied in whole.
ENV UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY api/src ./src
COPY api/README.md ./
RUN uv sync --locked --no-dev --no-editable

FROM python:3.13-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin api
COPY --from=build /app/.venv /app/.venv
COPY shared/catalog.json /app/shared/catalog.json
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    RITIS_CATALOG_PATH=/app/shared/catalog.json
USER api
# Cloud Run sets PORT.
CMD ["sh", "-c", "exec uvicorn ritis_api.main:build_app --factory --host 0.0.0.0 --port ${PORT:-8080}"]
