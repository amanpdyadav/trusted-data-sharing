# PETs Transformer web app, for a VPS behind Traefik (see docker-compose.yml and docs/DEPLOY.md).

# ---------------------------------------------------------------- 1. build the web app (frontend/ -> package static)
FROM node:20-alpine AS ui
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# vite writes to ../src/pets_transformer/web/static
RUN mkdir -p ../src/pets_transformer/web/static && npm run build

# ---------------------------------------------------------------- 2. runtime
FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 1000 app && useradd --system --uid 1000 --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app

# dependencies first, so code edits do not reinstall them
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY --from=ui /build/src/pets_transformer/web/static/ ./src/pets_transformer/web/static/
RUN pip install ".[web]" && rm -rf build

# configuration that ships with the code (receivers and code lists)
COPY scenarios/ ./scenarios/
COPY codelists/ ./codelists/
# committed evaluation results seed the results volume on first start
COPY results/ ./results/

# writable state lives in volumes; create the mount points owned by the app user so new named volumes inherit it
RUN mkdir -p /app/out /data/package && chown -R app:app /app/out /app/results

ENV PETS_OUT_DIR=/app/out \
    PETS_RESULTS_DIR=/app/results \
    PETS_PACKAGE_ROOT=/data/package \
    PETS_SCENARIO_DIRS=/app/scenarios \
    PETS_CODELIST_DIR=/app/codelists \
    PETS_LLM_ENABLED=false

USER app
EXPOSE 8765
VOLUME ["/app/out", "/app/results"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/', timeout=4).status == 200 else 1)"

# `pets-transformer web` only binds 127.0.0.1 by design. In the container we bind all interfaces of the
# container itself; no port is published, so it is reachable only through Traefik on the docker network.
# One worker: sessions are files on disk, and a single process keeps writes to them ordered.
CMD ["uvicorn", "pets_transformer.web.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8765", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--log-level", "info"]
