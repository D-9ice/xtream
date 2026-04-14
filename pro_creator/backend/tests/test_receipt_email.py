from datetime import datetime, timezone

from app.services import receipt_email


class _FakeSMTP:
    instances: list["_FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: int = 30):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.ehlo_calls = 0
        self.tls_started = 0
        self.login_args = None
        self.sent_messages = []
        self.quit_calls = 0
        _FakeSMTP.instances.append(self)

    def ehlo(self) -> None:
        self.ehlo_calls += 1

    def starttls(self) -> None:
        self.tls_started += 1

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message) -> None:
        self.sent_messages.append(message)

    def quit(self) -> None:
        self.quit_calls += 1


def test_build_purchase_receipt_email_contains_purchase_details(monkeypatch) -> None:
    message = receipt_email.build_purchase_receipt_email(
        recipient_email="customer@example.com",
        plan_name="Pro",
        credits=2000,
        provider="paystack",
        amount=49.0,
        currency="USD",
        reference_id="ref_123",
        purchased_at=datetime(2026, 4, 4, 10, 0, tzinfo=timezone.utc),
    )

    assert message["To"] == "customer@example.com"
    assert message["From"].startswith("Pro Creator <")
    assert message["Subject"] == "Pro Creator receipt for Pro plan"
    body = message.get_body(preferencelist=("plain",)).get_content()
    assert "Paystack / MoMo" in body
    assert "$49.00" in body
    assert "ref_123" in body
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "Payment receipt" in html
    assert "customer@example.com" in html


def test_build_purchase_receipt_email_supports_access_entitlements() -> None:
    message = receipt_email.build_purchase_receipt_email(
        recipient_email="customer@example.com",
        plan_name="Factory Mode One-Time",
        credits=0,
        item_description="Factory Mode one-time access",
        provider="stripe",
        amount=149.0,
        currency="USD",
        reference_id="factory_ref_123",
        purchased_at=datetime(2026, 4, 4, 10, 0, tzinfo=timezone.utc),
    )

    body = message.get_body(preferencelist=("plain",)).get_content()
    assert "Item: Factory Mode one-time access" in body
    assert "Credits:" not in body
    assert "Stripe" in body


def test_send_purchase_receipt_email_uses_smtp(monkeypatch) -> None:
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(receipt_email, "EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(receipt_email, "EMAIL_SMTP_PORT", 587)
    monkeypatch.setattr(receipt_email, "EMAIL_SMTP_USERNAME", "smtp-user")
    monkeypatch.setattr(receipt_email, "EMAIL_SMTP_PASSWORD", "smtp-pass")
    monkeypatch.setattr(receipt_email, "EMAIL_SMTP_USE_TLS", True)
    monkeypatch.setattr(receipt_email, "EMAIL_SMTP_USE_SSL", False)
    monkeypatch.setattr(receipt_email, "EMAIL_FROM_ADDRESS", "noreply@example.com")
    monkeypatch.setattr(receipt_email, "EMAIL_FROM_NAME", "Pro Creator")
    monkeypatch.setattr(receipt_email.smtplib, "SMTP", _FakeSMTP)

    sent = receipt_email.send_purchase_receipt_email(
        recipient_email="customer@example.com",
        plan_name="Pro",
        credits=2000,
        provider="stripe",
        amount=49.0,
        currency="USD",
        reference_id="stripe_ref_123",
    )

    assert sent is True
    assert len(_FakeSMTP.instances) == 1
    smtp = _FakeSMTP.instances[0]
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 587
    assert smtp.tls_started == 1
    assert smtp.login_args == ("smtp-user", "smtp-pass")
    assert smtp.sent_messages
    assert smtp.sent_messages[0]["To"] == "customer@example.com"
    assert smtp.quit_calls == 1
