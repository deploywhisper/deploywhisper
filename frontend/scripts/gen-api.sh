#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
FRONTEND_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
OPENAPI_URL=${OPENAPI_URL:-http://localhost:8080/api/v1/openapi.json}
OUTPUT_FILE="${FRONTEND_DIR}/src/api/schema.d.ts"

mkdir -p "$(dirname "${OUTPUT_FILE}")"

npx openapi-typescript "${OPENAPI_URL}" -o "${OUTPUT_FILE}"
