#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${BASE_REF:-origin/main}"
PYTHON_BIN="${PYTHON_BIN:-python}"

if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  echo "Base ref '$BASE_REF' is unavailable. Skipping changed-skill harness feedback."
  exit 0
fi

mapfile -t CHANGED_PATHS < <(git diff --name-only "$BASE_REF"...HEAD || true)

SKILLS=()
for path in "${CHANGED_PATHS[@]}"; do
  if [[ "$path" =~ ^skills/([^.]+)\.md$ ]]; then
    skill="${BASH_REMATCH[1]}"
  elif [[ "$path" =~ ^tests/skill-tests/([^/]+)/ ]]; then
    skill="${BASH_REMATCH[1]}"
  else
    continue
  fi

  if [ -f "skills/${skill}.md" ]; then
    SKILLS+=("$skill")
  fi
done

if [ "${#SKILLS[@]}" -eq 0 ]; then
  echo "No changed built-in skills detected relative to $BASE_REF."
  exit 0
fi

mapfile -t UNIQUE_SKILLS < <(printf '%s\n' "${SKILLS[@]}" | sort -u)

echo "Running changed skill lint and harness checks relative to $BASE_REF:"
printf ' - %s\n' "${UNIQUE_SKILLS[@]}"
for skill in "${UNIQUE_SKILLS[@]}"; do
  "$PYTHON_BIN" cli.py skill lint "skills/${skill}.md"
done
"$PYTHON_BIN" cli.py skill test "${UNIQUE_SKILLS[@]}"
