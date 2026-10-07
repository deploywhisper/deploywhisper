#!/usr/bin/env bash
# Install uv 0.11.2 through its official distribution before running this script.
# Edit requirements-runtime.txt / requirements-dev-input.txt, then regenerate.
# Keep runtime declarations in pyproject.toml aligned with requirements-runtime.txt.
# Ordinary .txt inputs keep Dependabot's pip updates from replacing universal locks
# with platform-specific pip-tools output.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "uv 0.11.2 is required to regenerate dependency locks." >&2
  exit 1
fi
if [[ "$(uv --version)" != uv\ 0.11.2* ]]; then
  echo "Use uv 0.11.2 so dependency lock generation stays reproducible." >&2
  exit 1
fi

uv pip compile requirements-runtime.txt \
  --universal --python-version 3.10 --generate-hashes \
  --output-file requirements.txt "$@"
uv pip compile requirements-dev-input.txt \
  --constraint requirements.txt \
  --universal --python-version 3.10 --generate-hashes \
  --output-file requirements-dev.txt "$@"
