from redis.exceptions import RedisError

import app.services.rate_limit as rate_limit


class _FakeRedis:
    def __init__(self):
        self.values = {}

    def eval(self, _script, _key_count, key, _window):
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]


class _FailingRedis:
    def eval(self, *_args, **_kwargs):
        raise RedisError("down")


def test_rate_limit_uses_shared_counter(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(rate_limit, "_redis_client", lambda: fake)
    assert rate_limit.rate_limit_hit("tenant:ip", 2) is False
    assert rate_limit.rate_limit_hit("tenant:ip", 2) is False
    assert rate_limit.rate_limit_hit("tenant:ip", 2) is True


def test_rate_limit_falls_back_locally_when_redis_is_unavailable(monkeypatch) -> None:
    rate_limit._local_store.clear()
    monkeypatch.setattr(rate_limit, "_redis_client", lambda: _FailingRedis())
    assert rate_limit.rate_limit_hit("fallback", 1) is False
    assert rate_limit.rate_limit_hit("fallback", 1) is True
