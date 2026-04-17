FROM python:3.11-slim AS builder

WORKDIR /build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv

RUN python -m venv "${VIRTUAL_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

COPY requirements.txt .
RUN pip install --no-compile -r requirements.txt \
    && python -c "import pathlib, shutil, site; site_packages=[pathlib.Path(path) for path in site.getsitepackages()]; patterns=('pip','pip-*','wheel','wheel-*'); [shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True) for base in site_packages for pattern in patterns for path in base.glob(pattern)]; [shutil.rmtree(path, ignore_errors=True) for base in site_packages for path in base.rglob('__pycache__')]" \
    && rm -f "${VIRTUAL_ENV}"/bin/pip "${VIRTUAL_ENV}"/bin/pip3 "${VIRTUAL_ENV}"/bin/pip3.11


FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

RUN groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /app --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data /app/skills/custom \
    && chown -R appuser:appuser /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appuser app.py config.py logging_config.py ./
COPY --chown=appuser:appuser api ./api
COPY --chown=appuser:appuser analysis ./analysis
COPY --chown=appuser:appuser llm ./llm
COPY --chown=appuser:appuser models ./models
COPY --chown=appuser:appuser parsers ./parsers
COPY --chown=appuser:appuser services ./services
COPY --chown=appuser:appuser skills ./skills
COPY --chown=appuser:appuser ui ./ui

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "from urllib.request import urlopen; import sys; sys.exit(0 if urlopen('http://127.0.0.1:8080/api/v1/health').status == 200 else 1)"

CMD ["python", "app.py"]
