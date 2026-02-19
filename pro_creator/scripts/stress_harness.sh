#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

mkdir -p artifacts

echo "Starting compose stack for stress harness..."
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# Force a deterministic stress environment:
# - tenant-scoped rate limits enabled
# - strict external-provider validation disabled (stress can run with local fallbacks)
export RATE_LIMIT_ENABLED="${RATE_LIMIT_ENABLED:-true}"
export RATE_LIMIT_HEAVY_REQUESTS="${RATE_LIMIT_HEAVY_REQUESTS:-6}"
export RATE_LIMIT_WINDOW_SECONDS="${RATE_LIMIT_WINDOW_SECONDS:-60}"
export STRICT_PROVIDER_VALIDATION="${STRICT_PROVIDER_VALIDATION:-false}"

docker compose build backend worker
docker compose up -d redis minio minio-init backend worker

echo "Running tenant-aware stress harness..."
python3 scripts/stress_harness.py

echo "Stress harness passed. Report: artifacts/stress-report.json"
