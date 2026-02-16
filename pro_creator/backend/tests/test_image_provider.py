import base64

from app.services import image_engine, provider_routing


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_resolve_image_provider_auto_uses_openai_when_key_present(monkeypatch):
    monkeypatch.setattr(provider_routing, "IMAGE_PROVIDER", "auto")
    monkeypatch.setattr(provider_routing, "OPENAI_API_KEY", "sk-test")
    assert provider_routing.resolve_image_provider() == "openai"


def test_generate_openai_image_reads_b64_payload(monkeypatch):
    png_bytes = b"\x89PNG\r\n\x1a\nfake"
    encoded = base64.b64encode(png_bytes).decode("ascii")

    monkeypatch.setattr(image_engine, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(image_engine, "OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(image_engine, "OPENAI_IMAGE_MODEL", "gpt-image-1")
    monkeypatch.setattr(image_engine, "OPENAI_IMAGE_SIZE", "1536x1024")
    monkeypatch.setattr(image_engine, "OPENAI_IMAGE_QUALITY", "high")

    def _fake_post(url, headers=None, json=None, timeout=0):
        assert url.endswith("/images/generations")
        assert headers["Authorization"].startswith("Bearer ")
        assert json["model"] == "gpt-image-1"
        return _FakeResponse(
            200,
            {
                "data": [
                    {
                        "b64_json": encoded,
                    }
                ]
            },
        )

    monkeypatch.setattr(image_engine.requests, "post", _fake_post)

    out = image_engine._generate_openai_image("Studio portrait", "cinematic")
    assert out == png_bytes
