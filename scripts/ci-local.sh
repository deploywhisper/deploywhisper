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
BANDIT_BIN="${BANDIT_BIN:-./.venv/bin/bandit}"
if [ ! -x "$BANDIT_BIN" ]; then
  if command -v bandit >/dev/null 2>&1; then
    BANDIT_BIN="bandit"
  else
    BANDIT_BIN=""
  fi
fi

echo "Using Python: $PYTHON_BIN"
echo "Using Ruff: $RUFF_BIN"
if [ -n "$BANDIT_BIN" ]; then
  echo "Using Bandit: $BANDIT_BIN"
else
  echo "Bandit not found; skipping local security scan. Install bandit or set BANDIT_BIN for full CI parity." >&2
fi
"$RUFF_BIN" check .
"$RUFF_BIN" format --check .
"$PYTHON_BIN" -m pip check
if [ -n "$BANDIT_BIN" ]; then
  "$BANDIT_BIN" \
    -r api/ analysis/ services/ parsers/ llm/ models/ cli/ ui/ evidence/ \
    -f json \
    -o bandit-report.json \
    --severity-level medium \
    --confidence-level medium \
    -x tests/ \
    2>&1 | tee bandit.log || true
  "$BANDIT_BIN" \
    -r api/ analysis/ services/ parsers/ llm/ models/ cli/ ui/ evidence/ \
    --severity-level high \
    --confidence-level high \
    -x tests/
fi
"$PYTHON_BIN" -m compileall \
  api \
  analysis \
  cli \
  evidence \
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
"$PYTHON_BIN" cli.py skill test
"$PYTHON_BIN" -m unittest discover -q

if [ "${RUN_UI_A11Y:-0}" = "1" ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required for RUN_UI_A11Y=1 but was not found." >&2
    exit 1
  fi
  if [ ! -d node_modules ]; then
    echo "node_modules is missing; run 'npm install' before RUN_UI_A11Y=1." >&2
    exit 1
  fi
  npm run test:ui-review
  if [ "$(uname -s)" = "Darwin" ]; then
    npm run test:ui-review:voiceover
  else
    echo "Skipping VoiceOver lane because this host is not macOS." >&2
  fi
fi
