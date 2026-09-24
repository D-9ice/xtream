import requests

from app.services import social_publish


class _Response:
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_publish_fingerprint_is_stable_and_connection_scoped() -> None:
    one = social_publish._publish_fingerprint(
        tenant_id="default",
        user_id=1,
        project_id="p1",
        connection_id="c1",
        message="hello",
    )
    two = social_publish._publish_fingerprint(
        tenant_id="default",
        user_id=1,
        project_id="p1",
        connection_id="c1",
        message="hello",
    )
    other = social_publish._publish_fingerprint(
        tenant_id="default",
        user_id=1,
        project_id="p1",
        connection_id="c2",
        message="hello",
    )
    assert one == two
    assert one != other


def test_publish_timeout_is_marked_uncertain() -> None:
    assert social_publish._publish_failure_status(requests.Timeout("timeout")) == "uncertain"
    assert social_publish._publish_failure_status(requests.ConnectionError("down")) == "uncertain"


def test_publish_4xx_is_definite_failure_and_5xx_is_uncertain() -> None:
    response_400 = _Response(400)
    error_400 = requests.HTTPError("bad request")
    error_400.response = response_400
    response_503 = _Response(503)
    error_503 = requests.HTTPError("unavailable")
    error_503.response = response_503

    assert social_publish._publish_failure_status(error_400) == "failed"
    assert social_publish._publish_failure_status(error_503) == "uncertain"


def test_publish_429_is_safe_retryable() -> None:
    response = _Response(429)
    response.headers = {"Retry-After": "2"}
    error = requests.HTTPError("rate limited")
    error.response = response
    assert social_publish._rate_limit_retry_delay(error, 1) == 2.0


def test_publish_5xx_is_not_blindly_retried() -> None:
    response = _Response(503)
    response.headers = {}
    error = requests.HTTPError("unavailable")
    error.response = response
    assert social_publish._rate_limit_retry_delay(error, 1) is None


def test_publish_timeout_is_not_blindly_retried() -> None:
    assert social_publish._rate_limit_retry_delay(requests.Timeout("timeout"), 1) is None
