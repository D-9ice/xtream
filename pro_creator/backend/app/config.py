from pathlib import Path
import json
import os
from functools import lru_cache

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECTS_DIR = BASE_DIR / "projects"
DB_PATH = BASE_DIR / "backend" / "pro_creator.db"

API_TITLE = "Pro Creator Pro API"

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
AWS_SECRETS_ENABLED = os.getenv("AWS_SECRETS_ENABLED", "false").lower() == "true"
AWS_SECRETS_REGION = os.getenv("AWS_SECRETS_REGION", os.getenv("AWS_REGION", "us-east-1"))
AWS_SECRET_PREFIX = os.getenv("AWS_SECRET_PREFIX", "").strip("/")

DEFAULT_TENANT_ID = os.getenv("DEFAULT_TENANT_ID", "default").strip() or "default"
TENANT_HEADER_NAME = os.getenv("TENANT_HEADER_NAME", "X-Tenant-ID").strip() or "X-Tenant-ID"


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
ADMIN_BOOTSTRAP_SYNC = os.getenv("ADMIN_BOOTSTRAP_SYNC", "false").lower() == "true"
ADMIN_DASHBOARD_PASSWORD = _env_file_or_aws("ADMIN_DASHBOARD_PASSWORD", ADMIN_PASSWORD)
ADMIN_2FA_ENABLED = os.getenv("ADMIN_2FA_ENABLED", "false").lower() == "true"
ADMIN_2FA_TOTP_SECRET = _env_file_or_aws("ADMIN_2FA_TOTP_SECRET", "").strip()

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
FACTORY_MODE_ENABLED = os.getenv(
    "FACTORY_MODE_ENABLED",
    os.getenv("NEXT_PUBLIC_FACTORY_MODE_ENABLED", "false"),
).lower() == "true"

# xAI / Grok is the authoritative production generation stack.
# xAI / Grok
XAI_API_KEY = _env_file_or_aws("XAI_API_KEY", "").strip()
XAI_BASE_URL = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")
XAI_TEXT_MODEL = os.getenv("XAI_TEXT_MODEL", "grok-4.20-beta-latest-non-reasoning").strip()
XAI_IMAGE_MODEL = os.getenv("XAI_IMAGE_MODEL", "grok-imagine-image").strip()
XAI_VIDEO_MODEL = os.getenv("XAI_VIDEO_MODEL", "grok-imagine-video").strip()
XAI_TTS_VOICE_ID = os.getenv("XAI_TTS_VOICE_ID", "eve").strip()
XAI_TTS_MODEL = XAI_TTS_VOICE_ID
XAI_STT_MODEL = os.getenv("XAI_STT_MODEL", "grok-voice-transcribe-2.0").strip()
GROK_IMAGINE_TARGET_SEGMENT_SECONDS = max(10, int(os.getenv("GROK_IMAGINE_TARGET_SEGMENT_SECONDS", "15")))
GROK_IMAGINE_INITIAL_CHUNK_SECONDS = max(1, min(15, int(os.getenv("GROK_IMAGINE_INITIAL_CHUNK_SECONDS", "15"))))
GROK_IMAGINE_EXTENSION_CHUNK_SECONDS = max(1, min(10, int(os.getenv("GROK_IMAGINE_EXTENSION_CHUNK_SECONDS", "10"))))
GROK_IMAGINE_ASPECT_RATIO = os.getenv("GROK_IMAGINE_ASPECT_RATIO", "16:9").strip()
GROK_IMAGINE_RESOLUTION = os.getenv("GROK_IMAGINE_RESOLUTION", "720p").strip()
GROK_IMAGINE_POLL_TIMEOUT_SECONDS = max(
    60,
    int(os.getenv("GROK_IMAGINE_POLL_TIMEOUT_SECONDS", "1800")),
)
GROK_IMAGINE_POLL_INTERVAL_SECONDS = max(
    1,
    int(os.getenv("GROK_IMAGINE_POLL_INTERVAL_SECONDS", "5")),
)
GROK_IMAGINE_MAX_CLIP_BYTES = max(
    50 * 1024 * 1024,
    int(os.getenv("GROK_IMAGINE_MAX_CLIP_BYTES", str(2 * 1024 * 1024 * 1024))),
)

FFMPEG_SCENE_RENDER_TIMEOUT_SECONDS = max(
    30,
    int(os.getenv("FFMPEG_SCENE_RENDER_TIMEOUT_SECONDS", "180")),
)
FFMPEG_CONCAT_TIMEOUT_SECONDS = max(
    30,
    int(os.getenv("FFMPEG_CONCAT_TIMEOUT_SECONDS", "300")),
)

VIDEO_IMPORT_MAX_BYTES = max(
    50 * 1024 * 1024,
    int(os.getenv("VIDEO_IMPORT_MAX_BYTES", str(2 * 1024 * 1024 * 1024))),
)
VIDEO_IMPORT_CONNECT_TIMEOUT_SECONDS = max(
    1,
    int(os.getenv("VIDEO_IMPORT_CONNECT_TIMEOUT_SECONDS", "10")),
)
VIDEO_IMPORT_READ_TIMEOUT_SECONDS = max(
    5,
    int(os.getenv("VIDEO_IMPORT_READ_TIMEOUT_SECONDS", "60")),
)
VIDEO_IMPORT_MAX_REDIRECTS = max(
    0,
    min(10, int(os.getenv("VIDEO_IMPORT_MAX_REDIRECTS", "5"))),
)

# Billing / Stripe / Paystack
STRIPE_SECRET_KEY = _env_file_or_aws("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = _env_file_or_aws("STRIPE_WEBHOOK_SECRET", "")
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "http://localhost:3000/?checkout=success")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "http://localhost:3000/?checkout=cancel")
STRIPE_PRICE_ID_MODERATE = os.getenv("STRIPE_PRICE_ID_MODERATE", "")
STRIPE_PRICE_ID_PRO = os.getenv("STRIPE_PRICE_ID_PRO", "")
STRIPE_PRICE_ID_STUDIO = os.getenv("STRIPE_PRICE_ID_STUDIO", "")
FACTORY_MODE_SUBSCRIPTION_PRICE_USD = max(0, int(os.getenv("FACTORY_MODE_SUBSCRIPTION_PRICE_USD", "39")))
FACTORY_MODE_SUBSCRIPTION_STRIPE_PRICE_ID = os.getenv("FACTORY_MODE_SUBSCRIPTION_STRIPE_PRICE_ID", "")
FACTORY_MODE_SUBSCRIPTION_PERIOD_DAYS = max(1, int(os.getenv("FACTORY_MODE_SUBSCRIPTION_PERIOD_DAYS", "30")))
PAYSTACK_SECRET_KEY = _env_file_or_aws("PAYSTACK_SECRET_KEY", "")
PAYSTACK_CALLBACK_URL = os.getenv(
    "PAYSTACK_CALLBACK_URL",
    "http://localhost:3000/?checkout=success&provider=paystack",
)
PAYSTACK_CURRENCY = os.getenv("PAYSTACK_CURRENCY", "GHS").strip().upper() or "GHS"

# Social publishing OAuth
SOCIAL_OAUTH_FRONTEND_ORIGIN = os.getenv(
    "SOCIAL_OAUTH_FRONTEND_ORIGIN",
    "http://localhost:3000",
).strip().rstrip("/")
SOCIAL_OAUTH_BACKEND_ORIGIN = os.getenv(
    "SOCIAL_OAUTH_BACKEND_ORIGIN",
    "http://localhost:8000",
).strip().rstrip("/")

SOCIAL_YOUTUBE_CLIENT_ID = _env_file_or_aws("SOCIAL_YOUTUBE_CLIENT_ID", "")
SOCIAL_YOUTUBE_CLIENT_SECRET = _env_file_or_aws("SOCIAL_YOUTUBE_CLIENT_SECRET", "")

SOCIAL_META_APP_ID = _env_file_or_aws("SOCIAL_META_APP_ID", "")
SOCIAL_META_APP_SECRET = _env_file_or_aws("SOCIAL_META_APP_SECRET", "")
SOCIAL_META_GRAPH_VERSION = os.getenv("SOCIAL_META_GRAPH_VERSION", "v21.0").strip() or "v21.0"

SOCIAL_X_API_KEY = _env_file_or_aws("SOCIAL_X_API_KEY", "")
SOCIAL_X_API_SECRET = _env_file_or_aws("SOCIAL_X_API_SECRET", "")

SOCIAL_TIKTOK_CLIENT_KEY = _env_file_or_aws("SOCIAL_TIKTOK_CLIENT_KEY", "")
SOCIAL_TIKTOK_CLIENT_SECRET = _env_file_or_aws("SOCIAL_TIKTOK_CLIENT_SECRET", "")

# Email receipts / notifications
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Pro Creator Pro").strip() or "Pro Creator Pro"
EMAIL_FROM_ADDRESS = os.getenv("EMAIL_FROM_ADDRESS", ADMIN_EMAIL).strip() or ADMIN_EMAIL
EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", "").strip()
EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "").strip()
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_SMTP_USERNAME = os.getenv("EMAIL_SMTP_USERNAME", "").strip()
EMAIL_SMTP_PASSWORD = _env_file_or_aws("EMAIL_SMTP_PASSWORD", "")
EMAIL_SMTP_USE_TLS = os.getenv("EMAIL_SMTP_USE_TLS", "true").lower() == "true"
EMAIL_SMTP_USE_SSL = os.getenv("EMAIL_SMTP_USE_SSL", "false").lower() == "true"

# Credit costs per action
CREDITS_COST_SCRIPT_GENERATE = int(os.getenv("CREDITS_COST_SCRIPT_GENERATE", "6"))
CREDITS_COST_SCRIPT_IMPORT = int(os.getenv("CREDITS_COST_SCRIPT_IMPORT", "2"))
CREDITS_COST_VOICE_GENERATE = int(os.getenv("CREDITS_COST_VOICE_GENERATE", "8"))
CREDITS_COST_IMAGE_GENERATE = int(os.getenv("CREDITS_COST_IMAGE_GENERATE", "7"))
CREDITS_COST_VIDEO_RENDER = int(os.getenv("CREDITS_COST_VIDEO_RENDER", "20"))
CREDITS_COST_VIDEO_EXPORT = int(os.getenv("CREDITS_COST_VIDEO_EXPORT", "4"))
CREDITS_COST_THUMBNAIL_GENERATE = int(os.getenv("CREDITS_COST_THUMBNAIL_GENERATE", "3"))
CREDITS_COST_THUMBNAIL_AI_GENERATE = int(os.getenv("CREDITS_COST_THUMBNAIL_AI_GENERATE", "6"))

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
RATE_LIMIT_ANALYTICS_REQUESTS = int(os.getenv("RATE_LIMIT_ANALYTICS_REQUESTS", "120"))
RATE_LIMIT_ANALYTICS_MAX_BODY_BYTES = int(os.getenv("RATE_LIMIT_ANALYTICS_MAX_BODY_BYTES", "8192"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
PROVIDER_RETRY_ATTEMPTS = max(1, int(os.getenv("PROVIDER_RETRY_ATTEMPTS", "2")))
PROVIDER_RETRY_BACKOFF_SECONDS = float(os.getenv("PROVIDER_RETRY_BACKOFF_SECONDS", "0.25"))

# Validation behavior
STRICT_PROVIDER_VALIDATION = os.getenv("STRICT_PROVIDER_VALIDATION", "false").lower() == "true"


def validate_external_service_config() -> None:
    """
    Fail fast for known-invalid provider/billing combinations.
    Strict by default in production, optional in non-production via STRICT_PROVIDER_VALIDATION=true.
    """
    if not (ENVIRONMENT == "production" or STRICT_PROVIDER_VALIDATION):
        return

    errors: list[str] = []

    if not XAI_API_KEY.strip():
        errors.append("XAI_API_KEY is required for the xAI/Grok workflow.")

    if not AUTH_REQUIRED:
        errors.append("AUTH_REQUIRED must be enabled in production.")

    if not OWNER_EMAIL_ALLOWLIST:
        errors.append("OWNER_EMAIL_ALLOWLIST must be set in production.")
    elif ADMIN_EMAIL.strip().lower() not in OWNER_EMAIL_ALLOWLIST:
        errors.append("ADMIN_EMAIL must be included in OWNER_EMAIL_ALLOWLIST in production.")

    normalized_origins = [origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()]
    if not normalized_origins:
        errors.append("ALLOWED_ORIGINS must contain at least one origin in production.")
    if "*" in normalized_origins:
        errors.append("ALLOWED_ORIGINS must not include wildcard origins in production.")
    if any("localhost" in origin or "127.0.0.1" in origin for origin in normalized_origins):
        errors.append("ALLOWED_ORIGINS must not include local origins in production.")

    if not RATE_LIMIT_ENABLED:
        errors.append("RATE_LIMIT_ENABLED must be true in production.")
    if RATE_LIMIT_ANALYTICS_REQUESTS < 1:
        errors.append("RATE_LIMIT_ANALYTICS_REQUESTS must be at least 1.")
    if RATE_LIMIT_ANALYTICS_MAX_BODY_BYTES < 1024:
        errors.append("RATE_LIMIT_ANALYTICS_MAX_BODY_BYTES must be at least 1024.")

    if len(JWT_SECRET.strip()) < 32:
        errors.append("JWT_SECRET should be at least 32 characters long in production.")

    if len(ADMIN_PASSWORD.strip()) < 12:
        errors.append("ADMIN_PASSWORD should be at least 12 characters long in production.")

    if len(ADMIN_DASHBOARD_PASSWORD.strip()) < 12:
        errors.append("ADMIN_DASHBOARD_PASSWORD should be at least 12 characters long in production.")

    if ADMIN_2FA_ENABLED and not ADMIN_2FA_TOTP_SECRET:
        errors.append("ADMIN_2FA_TOTP_SECRET is required when ADMIN_2FA_ENABLED is true.")

    if STORAGE_BACKEND == "s3":
        if S3_ACCESS_KEY.strip() in {"", "minioadmin"}:
            errors.append("S3_ACCESS_KEY must be set to a non-default value for S3 storage.")
        if S3_SECRET_KEY.strip() in {"", "minioadmin"}:
            errors.append("S3_SECRET_KEY must be set to a non-default value for S3 storage.")

    any_stripe_price = any(
        [
            STRIPE_PRICE_ID_MODERATE.strip(),
            STRIPE_PRICE_ID_PRO.strip(),
            STRIPE_PRICE_ID_STUDIO.strip(),
            FACTORY_MODE_SUBSCRIPTION_STRIPE_PRICE_ID.strip(),
        ]
    )
    if any_stripe_price and not STRIPE_SECRET_KEY.strip():
        errors.append(
            "Stripe price IDs are configured but STRIPE_SECRET_KEY is missing."
        )
    if any_stripe_price and not STRIPE_WEBHOOK_SECRET.strip():
        errors.append(
            "Stripe price IDs are configured but STRIPE_WEBHOOK_SECRET is missing."
        )

    if errors:
        detail = "\n- ".join(["Invalid external service configuration:", *errors])
        raise RuntimeError(detail)
