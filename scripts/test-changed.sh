#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${BASE_REF:-origin/main}"
PYTHON_BIN="${PYTHON_BIN:-python}"

if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  echo "Base ref '$BASE_REF' is unavailable. Skipping changed-test fast feedback."
  exit 0
fi

mapfile -t CHANGED_TESTS < <(git diff --name-only "$BASE_REF"...HEAD | grep -E '^tests/.+\.py$' || true)

if [ "${#CHANGED_TESTS[@]}" -eq 0 ]; then
  echo "No changed test files detected relative to $BASE_REF."
  exit 0
fi

MODULES=()
for path in "${CHANGED_TESTS[@]}"; do
  module="${path%.py}"
  module="${module//\//.}"
  MODULES+=("$module")
done

echo "Running changed tests relative to $BASE_REF:"
printf ' - %s\n' "${MODULES[@]}"
"$PYTHON_BIN" -m unittest -q "${MODULES[@]}"
