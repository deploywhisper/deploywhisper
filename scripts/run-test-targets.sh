#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"

if [ "$#" -eq 0 ]; then
  echo "No test targets were provided."
  exit 1
fi

for target in "$@"; do
  echo "Running unittest discovery for $target"
  "$PYTHON_BIN" -m unittest discover -s "$target" -q
done
