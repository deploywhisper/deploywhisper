#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

echo "Using Python: $PYTHON_BIN"
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
