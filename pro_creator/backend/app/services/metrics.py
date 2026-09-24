from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram
from redis import Redis
from redis.exceptions import RedisError

from app.config import CELERY_BROKER_URL

GROK_RENDER_TOTAL = Counter(
    "procreator_grok_render_total",
    "Grok Imagine render outcomes.",
    ["status"],
)
GROK_RENDER_SECONDS = Histogram(
    "procreator_grok_render_duration_seconds",
    "Grok Imagine end-to-end render duration in seconds.",
)
GROK_RETRY_TOTAL = Counter(
    "procreator_grok_retry_total",
    "Grok Imagine retry attempts.",
    ["phase", "reason"],
)
SOCIAL_PUBLISH_TOTAL = Counter(
    "procreator_social_publish_total",
    "Social publishing outcomes.",
    ["platform", "status"],
)
FACTORY_RUN_TOTAL = Counter(
    "procreator_factory_run_total",
    "Factory Mode run outcomes.",
    ["status"],
)
ORCHESTRATION_JOB_TOTAL = Counter(
    "procreator_orchestration_job_total",
    "Orchestration job terminal outcomes.",
    ["kind", "status"],
)
VIDEO_EXPORT_TOTAL = Counter(
    "procreator_video_export_total",
    "Video export outcomes.",
    ["preset", "status"],
)
STORAGE_FAILURE_TOTAL = Counter(
    "procreator_storage_failure_total",
    "Storage operation failures.",
    ["backend", "operation"],
)
CELERY_QUEUE_DEPTH = Gauge(
    "procreator_celery_queue_depth",
    "Current Celery default queue depth.",
)
CELERY_QUEUE_METRIC_FAILURE_TOTAL = Counter(
    "procreator_celery_queue_metric_failure_total",
    "Failures while reading Celery queue depth.",
)


def refresh_celery_queue_depth() -> None:
    try:
        client = Redis.from_url(
            CELERY_BROKER_URL,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
        CELERY_QUEUE_DEPTH.set(int(client.llen("celery")))
    except (RedisError, OSError, TypeError, ValueError):
        CELERY_QUEUE_METRIC_FAILURE_TOTAL.inc()
