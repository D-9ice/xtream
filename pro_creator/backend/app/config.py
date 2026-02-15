from pathlib import Path
import json
import os
from functools import lru_cache

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECTS_DIR = BASE_DIR / "projects"
DB_PATH = BASE_DIR / "backend" / "pro_creator.db"

API_TITLE = "Pro Creator API"

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
AWS_SECRETS_ENABLED = os.getenv("AWS_SECRETS_ENABLED", "false").lower() == "true"
AWS_SECRETS_REGION = os.getenv("AWS_SECRETS_REGION", os.getenv("AWS_REGION", "us-east-1"))
AWS_SECRET_PREFIX = os.getenv("AWS_SECRET_PREFIX", "").strip("/")

DEFAULT_TENANT_ID = os.getenv("DEFAULT_TENANT_ID", "default").strip() or "default"


@lru_cache(maxsize=128)
def _read_aws_secret(secret_id: str) -> str:
    import boto3

    client = boto3.client("secretsmanager", region_name=AWS_SECRETS_REGION)
    payload = client.get_secret_value(SecretId=secret_id)
    secret_string = payload.get("SecretString")
    if secret_string:
        return secret_string
    secret_binary = payload.get("SecretBinary")
    if isinstance(secret_binary, bytes):
        return secret_binary.decode("utf-8")
    return ""


def _env_file_or_aws(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value not in {None, ""}:
        return value

    file_path = os.getenv(f"{name}_FILE")
    if file_path:
        try:
            return Path(file_path).read_text().strip()
        except OSError:
            return default

    if AWS_SECRETS_ENABLED:
        secret_id = os.getenv(f"{name}_AWS_SECRET_ID")
        if not secret_id and AWS_SECRET_PREFIX:
            secret_id = f"{AWS_SECRET_PREFIX}/{name.lower()}"
        if secret_id:
            try:
                raw_secret = _read_aws_secret(secret_id)
                secret_key = os.getenv(f"{name}_AWS_SECRET_KEY")
                if secret_key:
                    decoded = json.loads(raw_secret)
                    extracted = decoded.get(secret_key)
                    if isinstance(extracted, str):
                        return extracted
                    return default
                return raw_secret.strip()
            except Exception:
                return default
    return default

ALLOWED_ORIGINS = os.getenv(
	"ALLOWED_ORIGINS",
	"http://localhost:3000,http://127.0.0.1:3000",
).split(",")

# Auth
_auth_required_env = os.getenv("AUTH_REQUIRED")
if _auth_required_env is None:
	AUTH_REQUIRED = ENVIRONMENT == "production"
else:
	AUTH_REQUIRED = _auth_required_env.lower() == "true"
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@procreator.local")
JWT_SECRET = _env_file_or_aws("JWT_SECRET", "dev-secret-change-me")
ADMIN_PASSWORD = _env_file_or_aws("ADMIN_PASSWORD", "ChangeMe123!")
ADMIN_DASHBOARD_PASSWORD = _env_file_or_aws("ADMIN_DASHBOARD_PASSWORD", ADMIN_PASSWORD)
ADMIN_2FA_ENABLED = os.getenv("ADMIN_2FA_ENABLED", "false").lower() == "true"

# Owner / super-admin controls
OWNER_EMAIL_ALLOWLIST = [
    value.strip().lower()
    for value in os.getenv("OWNER_EMAIL_ALLOWLIST", "").split(",")
    if value.strip()
]

# Database
DATABASE_URL = _env_file_or_aws("DATABASE_URL", f"sqlite:///{DB_PATH}")

# Storage
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")  # local | s3
S3_PUBLIC_URL = os.getenv("S3_PUBLIC_URL", "").rstrip("/")
PROJECTS_URL_BASE = os.getenv("PROJECTS_URL_BASE", "").rstrip("/") or (
    S3_PUBLIC_URL if S3_PUBLIC_URL else "http://127.0.0.1:8000/projects"
)

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_ACCESS_KEY = _env_file_or_aws("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = _env_file_or_aws("S3_SECRET_KEY", "minioadmin")
S3_BUCKET = os.getenv("S3_BUCKET", "pro-creator")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_USE_SSL = os.getenv("S3_USE_SSL", "false").lower() == "true"

# Async processing
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
ENABLE_CELERY = os.getenv("ENABLE_CELERY", "false").lower() == "true"

# Voice/TTS
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "xtts")  # xtts | elevenlabs
ELEVENLABS_API_KEY = _env_file_or_aws("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
XTTS_ENDPOINT = os.getenv("XTTS_ENDPOINT", "")

# Multi-provider routing
SCRIPT_PROVIDER = os.getenv("SCRIPT_PROVIDER", "auto").lower()  # auto | openai | template
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "local").lower()  # local | replicate | openai | ...
VOICE_PROVIDER_DEFAULT = os.getenv("VOICE_PROVIDER_DEFAULT", TTS_PROVIDER).lower()

# Script model tiers
OPENAI_API_KEY = _env_file_or_aws("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL_DRAFT = os.getenv("OPENAI_MODEL_DRAFT", "gpt-4o-mini")
OPENAI_MODEL_STANDARD = os.getenv("OPENAI_MODEL_STANDARD", "gpt-4o-mini")
OPENAI_MODEL_PREMIUM = os.getenv("OPENAI_MODEL_PREMIUM", "gpt-4.1")

# Billing / Stripe
STRIPE_SECRET_KEY = _env_file_or_aws("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = _env_file_or_aws("STRIPE_WEBHOOK_SECRET", "")
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "http://localhost:3000/?checkout=success")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "http://localhost:3000/?checkout=cancel")
STRIPE_PRICE_ID_MODERATE = os.getenv("STRIPE_PRICE_ID_MODERATE", "")
STRIPE_PRICE_ID_PRO = os.getenv("STRIPE_PRICE_ID_PRO", "")
STRIPE_PRICE_ID_STUDIO = os.getenv("STRIPE_PRICE_ID_STUDIO", "")

# Credit costs per action
CREDITS_COST_SCRIPT_GENERATE = int(os.getenv("CREDITS_COST_SCRIPT_GENERATE", "6"))
CREDITS_COST_SCRIPT_IMPORT = int(os.getenv("CREDITS_COST_SCRIPT_IMPORT", "2"))
CREDITS_COST_VOICE_GENERATE = int(os.getenv("CREDITS_COST_VOICE_GENERATE", "8"))
CREDITS_COST_IMAGE_GENERATE = int(os.getenv("CREDITS_COST_IMAGE_GENERATE", "7"))
CREDITS_COST_VIDEO_RENDER = int(os.getenv("CREDITS_COST_VIDEO_RENDER", "20"))
CREDITS_COST_VIDEO_EXPORT = int(os.getenv("CREDITS_COST_VIDEO_EXPORT", "4"))

# Lip sync
RHUBARB_PATH = os.getenv("RHUBARB_PATH", "")
RHUBARB_TIMEOUT = int(os.getenv("RHUBARB_TIMEOUT", "30"))
AUTO_LIPSYNC = os.getenv("AUTO_LIPSYNC", "true").lower() == "true"

# Basic API rate limiting
_rate_limit_enabled_env = os.getenv("RATE_LIMIT_ENABLED")
if _rate_limit_enabled_env is None:
    RATE_LIMIT_ENABLED = ENVIRONMENT == "production"
else:
    RATE_LIMIT_ENABLED = _rate_limit_enabled_env.lower() == "true"
RATE_LIMIT_AUTH_REQUESTS = int(os.getenv("RATE_LIMIT_AUTH_REQUESTS", "15"))
RATE_LIMIT_HEAVY_REQUESTS = int(os.getenv("RATE_LIMIT_HEAVY_REQUESTS", "30"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
