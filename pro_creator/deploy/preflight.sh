#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.production"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} not found."
  exit 1
fi

echo "Running production preflight checks..."

required_plain_vars=(
  DOMAIN_NAME
  LETSENCRYPT_EMAIL
  ADMIN_EMAIL
  ALLOWED_ORIGINS
  OWNER_EMAIL_ALLOWLIST
  FACTORY_MODE_ENABLED
  POSTGRES_DB
  POSTGRES_USER
  S3_BUCKET
  S3_REGION
  S3_ENDPOINT
  S3_USE_SSL
  S3_PUBLIC_URL
  XAI_BASE_URL
  XAI_TEXT_MODEL
  XAI_IMAGE_MODEL
  XAI_VIDEO_MODEL
  XAI_TTS_VOICE_ID
  GROK_IMAGINE_TARGET_SEGMENT_SECONDS
  GROK_IMAGINE_INITIAL_CHUNK_SECONDS
  GROK_IMAGINE_EXTENSION_CHUNK_SECONDS
  GROK_IMAGINE_ASPECT_RATIO
  GROK_IMAGINE_RESOLUTION
)

required_secret_vars=(
  JWT_SECRET
  ADMIN_PASSWORD
  ADMIN_DASHBOARD_PASSWORD
  POSTGRES_PASSWORD
  DATABASE_URL
  S3_ACCESS_KEY
  S3_SECRET_KEY
  XAI_API_KEY
)

resolve_host_path() {
  # Map common container paths back to host paths for preflight checks.
  # Production compose mounts ./deploy into the container at /app/deploy.
  local path="$1"
  if [[ "${path}" == /app/* ]]; then
    echo "${ROOT_DIR}/${path#/app/}"
    return 0
  fi
  if [[ "${path}" == ./* || "${path}" != /* ]]; then
    echo "${ROOT_DIR}/${path#./}"
    return 0
  fi
  echo "${path}"
}

get_env_value() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -n 1 || true)"
  echo "${line#*=}"
}

is_set_nonempty() {
  local value="$1"
  [[ -n "${value// }" ]]
}

for var in "${required_plain_vars[@]}"; do
  if ! grep -q "^${var}=" "${ENV_FILE}"; then
    echo "ERROR: Missing required variable ${var} in .env.production"
    exit 1
  fi
done

for var in "${required_secret_vars[@]}"; do
  value="$(get_env_value "${var}")"
  file_value="$(get_env_value "${var}_FILE")"
  aws_secret_id_value="$(get_env_value "${var}_AWS_SECRET_ID")"
  aws_prefix="$(get_env_value "AWS_SECRET_PREFIX")"
  aws_enabled="$(get_env_value "AWS_SECRETS_ENABLED")"
  has_aws_source="false"
  if is_set_nonempty "${aws_secret_id_value}"; then
    has_aws_source="true"
  elif [[ "${aws_enabled}" == "true" ]] && is_set_nonempty "${aws_prefix}"; then
    has_aws_source="true"
  fi
  if ! is_set_nonempty "${value}" && ! is_set_nonempty "${file_value}" && [[ "${has_aws_source}" != "true" ]]; then
    echo "ERROR: Missing ${var} (set ${var}, ${var}_FILE, or ${var}_AWS_SECRET_ID) in .env.production"
    exit 1
  fi
  if is_set_nonempty "${file_value}" && [[ ! -f "${ROOT_DIR}/${file_value}" ]] && [[ ! -f "${file_value}" ]]; then
    echo "ERROR: ${var}_FILE path does not exist: ${file_value}"
    exit 1
  fi
done

if grep -Eq "^AWS_SECRETS_ENABLED=true$" "${ENV_FILE}"; then
  if ! grep -q "^AWS_SECRETS_REGION=" "${ENV_FILE}"; then
    echo "ERROR: AWS_SECRETS_ENABLED=true requires AWS_SECRETS_REGION"
    exit 1
  fi
fi

allowed_origins="$(get_env_value "ALLOWED_ORIGINS")"
if [[ "${allowed_origins}" == *"*"* || "${allowed_origins}" == *"localhost"* || "${allowed_origins}" == *"127.0.0.1"* ]]; then
  echo "ERROR: ALLOWED_ORIGINS must contain only explicit production frontend origins."
  exit 1
fi

s3_endpoint="$(get_env_value "S3_ENDPOINT")"
s3_use_ssl="$(get_env_value "S3_USE_SSL")"
if [[ "${s3_endpoint}" == http://* && "${s3_use_ssl}" == "true" ]]; then
  echo "ERROR: S3_USE_SSL=true conflicts with an http:// S3_ENDPOINT."
  exit 1
fi
if [[ "${s3_endpoint}" == https://* && "${s3_use_ssl}" == "false" ]]; then
  echo "ERROR: S3_USE_SSL=false conflicts with an https:// S3_ENDPOINT."
  exit 1
fi

unsafe_patterns=(
  "JWT_SECRET=change-me"
  "ADMIN_PASSWORD=ChangeMe123!"
  "ADMIN_DASHBOARD_PASSWORD=ChangeMe123!"
  "POSTGRES_PASSWORD=change-me-db-password"
  "DATABASE_URL=.*change-me-db-password"
  "S3_ACCESS_KEY=do-access-key"
  "S3_SECRET_KEY=do-secret-key"
  "GRAFANA_ADMIN_PASSWORD=change-me-grafana"
)

for pattern in "${unsafe_patterns[@]}"; do
  if grep -Eq "${pattern}" "${ENV_FILE}"; then
    echo "ERROR: Unsafe default found in .env.production matching pattern: ${pattern}"
    exit 1
  fi
done

# Enforce lipsync dependency (Rhubarb must be installed and reachable).
auto_lipsync="$(get_env_value "AUTO_LIPSYNC")"
if [[ -z "${auto_lipsync}" ]]; then
  auto_lipsync="true"
fi
if [[ "${auto_lipsync}" == "true" ]]; then
  rhubarb_path="$(get_env_value "RHUBARB_PATH")"
  if ! is_set_nonempty "${rhubarb_path}"; then
    echo "ERROR: AUTO_LIPSYNC=true requires RHUBARB_PATH in .env.production"
    exit 1
  fi
  rhubarb_host_path="$(resolve_host_path "${rhubarb_path}")"
  if [[ ! -f "${rhubarb_host_path}" ]]; then
    echo "ERROR: RHUBARB_PATH does not exist on host: ${rhubarb_host_path}"
    exit 1
  fi
  if [[ ! -x "${rhubarb_host_path}" ]]; then
    echo "ERROR: RHUBARB_PATH is not executable on host: ${rhubarb_host_path}"
    exit 1
  fi
  if ! "${rhubarb_host_path}" --version >/dev/null 2>&1; then
    echo "ERROR: RHUBARB_PATH is present but failed to execute --version: ${rhubarb_host_path}"
    exit 1
  fi
fi

echo "Validating compose configuration..."
cd "${ROOT_DIR}"
docker compose --env-file "${ENV_FILE}" -f docker-compose.yml -f deploy/docker-compose.prod.yml config >/dev/null

if grep -Eq "^OBSERVABILITY_ENABLED=true$" "${ENV_FILE}"; then
  grafana_password="$(get_env_value "GRAFANA_ADMIN_PASSWORD")"
  if ! is_set_nonempty "${grafana_password}"; then
    echo "ERROR: OBSERVABILITY_ENABLED=true requires GRAFANA_ADMIN_PASSWORD"
    exit 1
  fi
  docker compose --env-file "${ENV_FILE}" -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile observability config >/dev/null
fi

echo "Preflight checks passed."
