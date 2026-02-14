#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8000}"

fail() {
  echo "smoke_local: $*" >&2
  exit 1
}

echo "smoke_local: checking backend health..."
curl -fsS "${API_BASE}/health" >/dev/null || fail "backend not healthy at ${API_BASE}"

echo "smoke_local: checking auth gate status..."
curl -fsS "${API_BASE}/auth/gate/status" >/dev/null || fail "auth gate status failed"

echo "smoke_local: creating project..."
project_json="$(curl -fsS -X POST "${API_BASE}/project/create" \
  -H "Content-Type: application/json" \
  -d '{"title":"Smoke Test","topic":"Local hardening smoke test"}')"

project_id="$(
  python3 - <<'PY'
import json,sys
data=json.loads(sys.stdin.read())
print(data.get("project_id",""))
PY
<<<"${project_json}"
)"

[[ -n "${project_id}" ]] || fail "failed to parse project_id"
echo "smoke_local: created project_id=${project_id}"

echo "smoke_local: listing projects..."
curl -fsS "${API_BASE}/project/" | grep -q "${project_id}" || fail "created project not found in list"

echo "smoke_local: deleting project..."
curl -fsS -X DELETE "${API_BASE}/project/${project_id}" >/dev/null || fail "failed to delete project"

echo "smoke_local: ok"

