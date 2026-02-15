#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Starting compose stack..."
# Build only what's required for the smoke test to keep CI fast.
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
SMOKE_MODE="${PC_SMOKE_MODE:-basic}"

if [[ "${SMOKE_MODE}" == "full" ]]; then
  docker compose build backend worker
  docker compose up -d redis minio minio-init backend worker
else
  docker compose build backend
  docker compose up -d redis minio minio-init backend
fi

echo "Running smoke test..."
python3 scripts/integration_smoke.py

echo "Smoke test passed."
