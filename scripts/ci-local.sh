#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi
RUFF_BIN="${RUFF_BIN:-./.venv/bin/ruff}"
if [ ! -x "$RUFF_BIN" ]; then
  if command -v ruff >/dev/null 2>&1; then
    RUFF_BIN="ruff"
  else
    echo "ruff is required for local CI checks but was not found." >&2
    echo "Install it into the active environment or set RUFF_BIN." >&2
    exit 1
  fi
fi

echo "Using Python: $PYTHON_BIN"
echo "Using Ruff: $RUFF_BIN"
"$RUFF_BIN" check .
"$RUFF_BIN" format --check .
"$PYTHON_BIN" -m pip check
"$PYTHON_BIN" -m compileall \
  api \
  analysis \
  cli \
  llm \
  models \
  parsers \
  services \
  ui \
  app.py \
  api_server.py \
  cli.py \
  config.py \
  logging_config.py
"$PYTHON_BIN" -m unittest discover -q
