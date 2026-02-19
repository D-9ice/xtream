import pytest

from app import config


def test_validate_external_service_config_openai_required(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "STRICT_PROVIDER_VALIDATION", False)
    monkeypatch.setattr(config, "SCRIPT_PROVIDER", "openai")
    monkeypatch.setattr(config, "IMAGE_PROVIDER", "local")
    monkeypatch.setattr(config, "TTS_PROVIDER", "xtts")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_MODERATE", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_PRO", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_STUDIO", "")

    with pytest.raises(RuntimeError) as exc:
        config.validate_external_service_config()
    assert "SCRIPT_PROVIDER=openai requires OPENAI_API_KEY" in str(exc.value)


def test_validate_external_service_config_stripe_pairing(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "STRICT_PROVIDER_VALIDATION", False)
    monkeypatch.setattr(config, "SCRIPT_PROVIDER", "auto")
    monkeypatch.setattr(config, "IMAGE_PROVIDER", "local")
    monkeypatch.setattr(config, "TTS_PROVIDER", "xtts")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_MODERATE", "price_test")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_PRO", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_STUDIO", "")

    with pytest.raises(RuntimeError) as exc:
        config.validate_external_service_config()
    text = str(exc.value)
    assert "STRIPE_SECRET_KEY is missing" in text
    assert "STRIPE_WEBHOOK_SECRET is missing" in text
