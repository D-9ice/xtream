from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import time

from redis import Redis
from redis.exceptions import RedisError

from app.config import RATE_LIMIT_WINDOW_SECONDS, REDIS_URL
from app.utils.logger import get_logger

logger = get_logger(__name__)

_client: Redis | None = None
_client_lock = Lock()
_local_lock = Lock()
_local_store: dict[str, deque[float]] = defaultdict(deque)

_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


def _redis_client() -> Redis:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = Redis.from_url(
                    REDIS_URL,
                    socket_connect_timeout=1.5,
                    socket_timeout=1.5,
                    health_check_interval=30,
                )
    return _client


def _local_rate_limit_hit(key: str, limit: int) -> bool:
    now = time()
    floor = now - RATE_LIMIT_WINDOW_SECONDS
    with _local_lock:
        bucket = _local_store[key]
        while bucket and bucket[0] < floor:
            bucket.popleft()
        if len(bucket) >= limit:
            return True
        bucket.append(now)
    return False


def rate_limit_hit(key: str, limit: int) -> bool:
    """Return True when the shared limit is exceeded.

    Redis is authoritative in normal operation. If Redis is temporarily
    unavailable, a process-local bounded fallback keeps protection active
    instead of failing requests open or taking the API down.
    """
    redis_key = f"procreator:ratelimit:{key}"
    try:
        current = int(
            _redis_client().eval(
                _RATE_LIMIT_SCRIPT,
                1,
                redis_key,
                RATE_LIMIT_WINDOW_SECONDS,
            )
        )
        return current > limit
    except (RedisError, OSError, ValueError, TypeError) as exc:
        logger.warning("Redis rate limiter unavailable; using local fallback: %s", exc)
        return _local_rate_limit_hit(key, limit)
