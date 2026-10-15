FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS builder

WORKDIR /build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends binutils \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv "${VIRTUAL_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

COPY requirements.txt .
RUN python -m pip install --require-hashes --only-binary=:all: --no-compile -r requirements.txt \
    && python -c "import pathlib, shutil, site; site_packages=[pathlib.Path(path) for path in site.getsitepackages()]; patterns=('pip','pip-*','wheel','wheel-*'); [shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True) for base in site_packages for pattern in patterns for path in base.glob(pattern)]; [shutil.rmtree(path, ignore_errors=True) for base in site_packages for path in base.rglob('__pycache__')]; [shutil.rmtree(path, ignore_errors=True) for base in site_packages for name in ('tests','test','docs','examples') for path in base.rglob(name) if path.is_dir()]" \
    && rm -f "${VIRTUAL_ENV}"/bin/pip "${VIRTUAL_ENV}"/bin/pip3 "${VIRTUAL_ENV}"/bin/pip3.11

# Stripping native binaries is optional; dependency installation above must fail closed.
RUN find "${VIRTUAL_ENV}" -type f \( -name '*.so' -o -name '*.so.*' \) -exec strip --strip-unneeded {} + 2>/dev/null || true


FROM node:26-alpine@sha256:143494b1da2945f061539253adc65e4f1569ddf07da2d384c022c791a9d90a4a AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build            # outputs /frontend/dist


FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS runtime

ARG BUILD_VERSION=1.4.0
ARG BUILD_SHA=unknown

LABEL org.opencontainers.image.version="${BUILD_VERSION}" \
    org.opencontainers.image.revision="${BUILD_SHA}"

WORKDIR /app

ENV APP_VERSION="${BUILD_VERSION}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

RUN groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /app --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data /app/skills/custom \
    && chown -R appuser:appuser /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=frontend --chown=appuser:appuser /frontend/dist ./frontend/dist
COPY --chown=appuser:appuser app.py config.py logging_config.py alembic.ini ./
COPY --chown=appuser:appuser api ./api
COPY --chown=appuser:appuser analysis ./analysis
COPY --chown=appuser:appuser evidence ./evidence
COPY --chown=appuser:appuser integrations ./integrations
COPY --chown=appuser:appuser infra_automation ./infra_automation
COPY --chown=appuser:appuser llm ./llm
COPY --chown=appuser:appuser migrations ./migrations
COPY --chown=appuser:appuser models ./models
COPY --chown=appuser:appuser parsers ./parsers
COPY --chown=appuser:appuser services ./services
COPY --chown=appuser:appuser skills ./skills

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "from urllib.request import urlopen; import sys; sys.exit(0 if urlopen('http://127.0.0.1:8080/api/v1/health').status == 200 else 1)"

CMD ["python", "app.py"]
