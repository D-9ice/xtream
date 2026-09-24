import requests
from fastapi.testclient import TestClient

from app.main import app
from app.routers import voice as voice_router
from app.services import voice_engine


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


def test_custom_voice_creation_returns_real_voice_id(monkeypatch) -> None:
    monkeypatch.setattr(voice_engine, "XAI_API_KEY", "xai-test")
    captured: dict[str, object] = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["files"] = kwargs.get("files")
        captured["data"] = kwargs.get("data")
        return _Response(200, {"voice_id": "voice_123"})

    monkeypatch.setattr(voice_engine.requests, "post", fake_post)
    result = voice_engine.clone_voice_profile(
        "Narrator",
        b"wav-bytes",
        filename="reference.wav",
        content_type="audio/wav",
    )
    assert result == {"provider": "xai", "voice_id": "voice_123"}
    assert str(captured["url"]).endswith("/custom-voices")
    assert captured["data"] == {"name": "Narrator"}


def test_custom_voice_provider_failure_is_explicit(monkeypatch) -> None:
    monkeypatch.setattr(voice_engine, "XAI_API_KEY", "xai-test")

    def fake_post(*_args, **_kwargs):
        return _Response(403, text="custom voices unavailable")

    monkeypatch.setattr(voice_engine.requests, "post", fake_post)

    try:
        voice_engine.clone_voice_profile("Narrator", b"wav-bytes")
    except RuntimeError as exc:
        assert "xAI custom voice creation failed" in str(exc)
    else:
        raise AssertionError("provider failure must not be reported as a successful clone")


def test_custom_voice_upload_limit_is_enforced(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr(voice_router, "VOICE_CLONE_MAX_BYTES", 4)
    response = client.post(
        "/voice/clone",
        data={"project_id": "voice-limit-test", "profile_name": "Narrator"},
        files={"sample": ("reference.wav", b"12345", "audio/wav")},
    )
    assert response.status_code == 413
