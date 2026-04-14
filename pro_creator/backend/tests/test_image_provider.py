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


def test_resolve_image_provider_auto_uses_xai_when_key_present(monkeypatch):
    assert provider_routing.resolve_image_provider() == "xai"


def test_generate_xai_image_reads_b64_payload(monkeypatch):
    png_bytes = b"\x89PNG\r\n\x1a\nfake"
    encoded = base64.b64encode(png_bytes).decode("ascii")

    monkeypatch.setattr(image_engine, "XAI_API_KEY", "xai-test")
    monkeypatch.setattr(image_engine, "XAI_BASE_URL", "https://api.x.ai/v1")
    monkeypatch.setattr(image_engine, "XAI_IMAGE_MODEL", "grok-imagine-image")

    def _fake_post(url, headers=None, json=None, timeout=0):
        assert url.endswith("/images/generations")
        assert headers["Authorization"].startswith("Bearer ")
        assert json["model"] == "grok-imagine-image"
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

    out = image_engine._generate_xai_image("Studio portrait", "cinematic")
    assert out == png_bytes
