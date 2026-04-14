import pytest

from app import config


def test_validate_external_service_config_requires_xai_key(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "STRICT_PROVIDER_VALIDATION", False)
    monkeypatch.setattr(config, "AUTH_REQUIRED", True)
    monkeypatch.setattr(config, "OWNER_EMAIL_ALLOWLIST", ["owner@example.com"])
    monkeypatch.setattr(config, "ADMIN_2FA_ENABLED", False)
    monkeypatch.setattr(config, "XAI_API_KEY", "")
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_MODERATE", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_PRO", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_STUDIO", "")

    with pytest.raises(RuntimeError) as exc:
        config.validate_external_service_config()
    assert "XAI_API_KEY is required for the xAI/Grok workflow" in str(exc.value)


def test_validate_external_service_config_stripe_pairing(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "STRICT_PROVIDER_VALIDATION", False)
    monkeypatch.setattr(config, "AUTH_REQUIRED", True)
    monkeypatch.setattr(config, "OWNER_EMAIL_ALLOWLIST", ["owner@example.com"])
    monkeypatch.setattr(config, "ADMIN_2FA_ENABLED", False)
    monkeypatch.setattr(config, "XAI_API_KEY", "xai-test")
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


def test_validate_external_service_config_grok_imagine_requires_xai_key(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "STRICT_PROVIDER_VALIDATION", False)
    monkeypatch.setattr(config, "AUTH_REQUIRED", True)
    monkeypatch.setattr(config, "OWNER_EMAIL_ALLOWLIST", ["owner@example.com"])
    monkeypatch.setattr(config, "ADMIN_2FA_ENABLED", False)
    monkeypatch.setattr(config, "XAI_API_KEY", "")
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_MODERATE", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_PRO", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_STUDIO", "")

    with pytest.raises(RuntimeError) as exc:
        config.validate_external_service_config()
    assert "XAI_API_KEY is required for the xAI/Grok workflow" in str(exc.value)


def test_validate_external_service_config_requires_auth_gate_and_owner_allowlist(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "STRICT_PROVIDER_VALIDATION", False)
    monkeypatch.setattr(config, "AUTH_REQUIRED", False)
    monkeypatch.setattr(config, "OWNER_EMAIL_ALLOWLIST", [])
    monkeypatch.setattr(config, "ADMIN_2FA_ENABLED", False)
    monkeypatch.setattr(config, "XAI_API_KEY", "xai-test")
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_MODERATE", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_PRO", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_STUDIO", "")

    with pytest.raises(RuntimeError) as exc:
        config.validate_external_service_config()
    text = str(exc.value)
    assert "AUTH_REQUIRED must be enabled in production" in text
    assert "OWNER_EMAIL_ALLOWLIST must be set in production" in text


def test_validate_external_service_config_hardens_production_access_controls(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "STRICT_PROVIDER_VALIDATION", False)
    monkeypatch.setattr(config, "AUTH_REQUIRED", True)
    monkeypatch.setattr(config, "OWNER_EMAIL_ALLOWLIST", ["owner@example.com"])
    monkeypatch.setattr(config, "ADMIN_2FA_ENABLED", False)
    monkeypatch.setattr(config, "XAI_API_KEY", "xai-test")
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_MODERATE", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_PRO", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_STUDIO", "")
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["http://localhost:3000", "*"])
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(config, "JWT_SECRET", "short-secret")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "short")
    monkeypatch.setattr(config, "ADMIN_DASHBOARD_PASSWORD", "short")

    with pytest.raises(RuntimeError) as exc:
        config.validate_external_service_config()

    text = str(exc.value)
    assert "ALLOWED_ORIGINS must not include wildcard origins in production" in text
    assert "ALLOWED_ORIGINS must not include local origins in production" in text
    assert "RATE_LIMIT_ENABLED must be true in production" in text
    assert "JWT_SECRET should be at least 32 characters long in production" in text
    assert "ADMIN_PASSWORD should be at least 12 characters long in production" in text
    assert "ADMIN_DASHBOARD_PASSWORD should be at least 12 characters long in production" in text


def test_validate_external_service_config_rejects_default_s3_secrets_in_production(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "STRICT_PROVIDER_VALIDATION", False)
    monkeypatch.setattr(config, "AUTH_REQUIRED", True)
    monkeypatch.setattr(config, "OWNER_EMAIL_ALLOWLIST", ["owner@example.com"])
    monkeypatch.setattr(config, "ADMIN_2FA_ENABLED", False)
    monkeypatch.setattr(config, "XAI_API_KEY", "xai-test")
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_MODERATE", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_PRO", "")
    monkeypatch.setattr(config, "STRIPE_PRICE_ID_STUDIO", "")
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["https://app.example.com"])
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(config, "JWT_SECRET", "x" * 32)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "x" * 12)
    monkeypatch.setattr(config, "ADMIN_DASHBOARD_PASSWORD", "x" * 12)
    monkeypatch.setattr(config, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(config, "S3_ACCESS_KEY", "minioadmin")
    monkeypatch.setattr(config, "S3_SECRET_KEY", "minioadmin")

    with pytest.raises(RuntimeError) as exc:
        config.validate_external_service_config()

    text = str(exc.value)
    assert "S3_ACCESS_KEY must be set to a non-default value for S3 storage." in text
    assert "S3_SECRET_KEY must be set to a non-default value for S3 storage." in text
