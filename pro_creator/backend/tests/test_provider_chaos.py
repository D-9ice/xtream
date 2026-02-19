import base64

import requests

from app.services import image_engine, script_engine, voice_engine


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, content: bytes = b"", headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.headers = headers or {}
        self.text = str(self._payload)
        self.ok = status_code < 400

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_script_openai_timeout_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(script_engine, "SCRIPT_PROVIDER", "auto")
    monkeypatch.setattr(script_engine, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(script_engine, "PROVIDER_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(script_engine, "PROVIDER_RETRY_BACKOFF_SECONDS", 0.0)

    def _always_timeout(*args, **kwargs):
        raise requests.Timeout("simulated timeout")

    monkeypatch.setattr(script_engine.requests, "post", _always_timeout)
    out = script_engine.generate_script("Title: Test Prompt: create something", 1, "neutral")
    assert isinstance(out.get("full_script"), str)
    assert out.get("scenes")


def test_image_openai_retries_then_succeeds(monkeypatch):
    png_bytes = b"\x89PNG\r\n\x1a\nchaos"
    encoded = base64.b64encode(png_bytes).decode("ascii")
    calls = {"count": 0}

    monkeypatch.setattr(image_engine, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(image_engine, "OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(image_engine, "PROVIDER_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(image_engine, "PROVIDER_RETRY_BACKOFF_SECONDS", 0.0)

    def _flaky_post(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise requests.Timeout("transient timeout")
        return _FakeResponse(200, payload={"data": [{"b64_json": encoded}]})

    monkeypatch.setattr(image_engine.requests, "post", _flaky_post)
    image, provider = image_engine.generate_image_bytes(
        prompt="cinematic city",
        style="cinematic",
        scene_id=1,
        provider="openai",
    )
    assert provider == "openai"
    assert image == png_bytes
    assert calls["count"] >= 2


def test_voice_elevenlabs_timeout_uses_tone_fallback(monkeypatch):
    monkeypatch.setattr(voice_engine, "ELEVENLABS_API_KEY", "key")
    monkeypatch.setattr(voice_engine, "ELEVENLABS_VOICE_ID", "voice")
    monkeypatch.setattr(voice_engine, "PROVIDER_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(voice_engine, "PROVIDER_RETRY_BACKOFF_SECONDS", 0.0)

    def _always_timeout(*args, **kwargs):
        raise requests.Timeout("simulated timeout")

    monkeypatch.setattr(voice_engine.requests, "post", _always_timeout)
    audio = voice_engine._generate_with_elevenlabs("hello world", "voice")
    assert isinstance(audio, (bytes, bytearray))
    assert len(audio) > 100
