import hashlib
import hmac
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import engine
from app.services import app_settings
from app.main import app
from app.routers import billing
from app.models import CreditLedgerEntry, HiddenReceipt, User


def billing_client() -> TestClient:
    return TestClient(app, headers={"X-Tenant-ID": f"billing-{uuid4().hex[:12]}"})


def test_billing_me_and_consume_flow() -> None:
    client = billing_client()

    me_res = client.get("/billing/me")
    assert me_res.status_code == 200
    payload = me_res.json()
    assert payload["credits_balance"] >= 0
    start_balance = payload["credits_balance"]

    consume_res = client.post("/billing/consume", json={"amount": 10, "reason": "test"})
    assert consume_res.status_code == 200
    consumed = consume_res.json()
    assert consumed["credits_balance"] == max(0, start_balance - 10)


def test_credit_plans_expose_stripe_and_paystack_checkout_providers(monkeypatch) -> None:
    client = billing_client()
    monkeypatch.setattr(billing, "STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setattr(billing, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(billing, "STRIPE_PRICE_ID_MODERATE", "price_moderate")
    monkeypatch.setattr(billing, "STRIPE_PRICE_ID_PRO", "price_pro")
    monkeypatch.setattr(billing, "STRIPE_PRICE_ID_STUDIO", "price_studio")
    monkeypatch.setattr(billing, "FACTORY_MODE_ONE_TIME_STRIPE_PRICE_ID", "price_factory_one_time")
    monkeypatch.setattr(billing, "FACTORY_MODE_SUBSCRIPTION_STRIPE_PRICE_ID", "price_factory_subscription")
    monkeypatch.setattr(billing, "PAYSTACK_SECRET_KEY", "psk_test")
    monkeypatch.setattr(app_settings, "STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setattr(app_settings, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(app_settings, "FACTORY_MODE_ONE_TIME_STRIPE_PRICE_ID", "price_factory_one_time")
    monkeypatch.setattr(app_settings, "FACTORY_MODE_SUBSCRIPTION_STRIPE_PRICE_ID", "price_factory_subscription")
    monkeypatch.setattr(app_settings, "PAYSTACK_SECRET_KEY", "psk_test")

    plans_res = client.get("/billing/plans")
    assert plans_res.status_code == 200
    plans = plans_res.json()["plans"]
    assert plans
    assert plans[0]["checkout_enabled"] is True
    assert sorted(plans[0]["checkout_providers"]) == ["paystack", "stripe"]
    factory_plan_ids = {plan["id"] for plan in plans if plan["kind"] == "factory_access"}
    assert factory_plan_ids == {"factory_one_time", "factory_subscription"}
    factory_subscription = next(plan for plan in plans if plan["id"] == "factory_subscription")
    assert factory_subscription["access_mode"] == "subscription"
    assert factory_subscription["access_days"] == 30
    factory_one_time = next(plan for plan in plans if plan["id"] == "factory_one_time")
    assert sorted(factory_one_time["checkout_providers"]) == ["paystack", "stripe"]


def test_paystack_checkout_and_webhook_grant_credits(monkeypatch) -> None:
    client = TestClient(app, headers={"X-Tenant-ID": "billing-default"})
    reference = f"ps_ref_{uuid4().hex[:12]}"
    monkeypatch.setattr(billing, "PAYSTACK_SECRET_KEY", "psk_test_secret")
    monkeypatch.setattr(billing, "PAYSTACK_CURRENCY", "GHS")
    monkeypatch.setattr(billing, "PAYSTACK_CALLBACK_URL", "http://localhost:3000/?checkout=success&provider=paystack")
    monkeypatch.setattr(app_settings, "PAYSTACK_SECRET_KEY", "psk_test_secret")

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_request(method, url, headers=None, json=None, timeout=None, params=None, data=None):
        if method == "POST" and url.endswith("/transaction/initialize"):
            return _FakeResponse(
                {
                    "status": True,
                    "data": {
                        "authorization_url": "https://paystack.test/checkout",
                        "reference": reference,
                        "access_code": "ps_access_123",
                    },
                }
            )
        if method == "GET" and url.endswith(f"/transaction/verify/{reference}"):
            return _FakeResponse(
                {
                    "status": True,
                    "data": {
                        "status": "success",
                        "amount": 4900,
                        "currency": "GHS",
                        "reference": reference,
                        "metadata": {
                            "plan_id": "pro",
                            "user_email": "admin@procreator.local",
                            "tenant_id": "billing-default",
                        },
                    },
                }
            )
        raise AssertionError(f"Unexpected Paystack request: {method} {url}")

    monkeypatch.setattr(billing.requests, "request", fake_request)
    receipt_calls: list[dict[str, object]] = []

    def fake_send_purchase_receipt_email(**kwargs):
        receipt_calls.append(kwargs)
        return True

    monkeypatch.setattr(billing, "send_purchase_receipt_email", fake_send_purchase_receipt_email)

    checkout_res = client.post(
        "/billing/purchase/checkout",
        json={"plan_id": "pro", "provider": "paystack"},
    )
    assert checkout_res.status_code == 200
    checkout_payload = checkout_res.json()
    assert checkout_payload["provider"] == "paystack"
    assert checkout_payload["checkout_url"] == "https://paystack.test/checkout"
    assert checkout_payload["session_id"] == reference

    event_body = json.dumps(
        {
            "event": "charge.success",
            "data": {
                "reference": reference,
                "metadata": {
                    "plan_id": "pro",
                    "user_email": "admin@procreator.local",
                    "tenant_id": "billing-default",
                },
            },
        }
    ).encode("utf-8")
    signature = hmac.new(b"psk_test_secret", event_body, hashlib.sha512).hexdigest()

    before_res = client.get("/billing/me")
    before_balance = before_res.json()["credits_balance"]

    webhook_res = client.post(
        "/billing/paystack/webhook",
        content=event_body,
        headers={"x-paystack-signature": signature},
    )
    assert webhook_res.status_code == 200
    assert webhook_res.json()["granted"] is True

    after_res = client.get("/billing/me")
    assert after_res.json()["credits_balance"] == before_balance + 2000

    receipts_res = client.get("/billing/receipts")
    assert receipts_res.status_code == 200
    receipts = receipts_res.json()["items"]
    assert receipts
    latest = receipts[0]
    assert latest["provider"] == "paystack"
    assert latest["plan_id"] == "pro"
    assert latest["amount"] == 2000
    assert latest["reference_id"] == reference
    assert receipt_calls
    assert receipt_calls[0]["provider"] == "paystack"
    assert receipt_calls[0]["currency"] == "GHS"
    assert receipt_calls[0]["reference_id"] == reference


def test_factory_one_time_checkout_and_webhook_grants_access(monkeypatch) -> None:
    client = TestClient(app, headers={"X-Tenant-ID": "billing-factory-one-time"})
    reference = f"stripe_factory_one_{uuid4().hex[:12]}"
    session_id = f"cs_factory_one_{uuid4().hex[:12]}"
    monkeypatch.setattr(billing, "STRIPE_SECRET_KEY", "sk_test_secret")
    monkeypatch.setattr(billing, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    monkeypatch.setattr(billing, "FACTORY_MODE_ONE_TIME_STRIPE_PRICE_ID", "price_factory_one")
    monkeypatch.setattr(app_settings, "STRIPE_SECRET_KEY", "sk_test_secret")
    monkeypatch.setattr(app_settings, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    monkeypatch.setattr(app_settings, "FACTORY_MODE_ONE_TIME_STRIPE_PRICE_ID", "price_factory_one")

    class _FakeStripeCheckoutSession:
        created_payloads: list[dict[str, object]] = []

        @staticmethod
        def create(**kwargs):
            _FakeStripeCheckoutSession.created_payloads.append(kwargs)
            return type("StripeSession", (), {"id": session_id, "url": "https://stripe.test/checkout"})()

    class _FakeStripeWebhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            return {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": session_id,
                        "payment_status": "paid",
                        "customer": "cus_factory_one",
                        "payment_intent": "pi_factory_one",
                        "metadata": {
                            "plan_id": "factory_one_time",
                            "plan_kind": "factory_access",
                            "access_mode": "one_time",
                            "user_email": "admin@procreator.local",
                            "tenant_id": "billing-factory-one-time",
                        },
                    }
                },
            }

    class _FakeStripe:
        api_key = None
        checkout = type("CheckoutNamespace", (), {"Session": _FakeStripeCheckoutSession})
        Webhook = _FakeStripeWebhook

    monkeypatch.setattr(billing, "stripe", _FakeStripe())
    receipt_calls: list[dict[str, object]] = []

    def fake_send_purchase_receipt_email(**kwargs):
        receipt_calls.append(kwargs)
        return True

    monkeypatch.setattr(billing, "send_purchase_receipt_email", fake_send_purchase_receipt_email)

    checkout_res = client.post(
        "/billing/purchase/checkout",
        json={"plan_id": "factory_one_time", "provider": "stripe"},
    )
    assert checkout_res.status_code == 200
    checkout_payload = checkout_res.json()
    assert checkout_payload["provider"] == "stripe"
    assert checkout_payload["checkout_url"] == "https://stripe.test/checkout"
    assert checkout_payload["session_id"] == session_id
    assert _FakeStripeCheckoutSession.created_payloads[0]["mode"] == "payment"

    event_body = json.dumps({}).encode("utf-8")
    webhook_res = client.post(
        "/billing/stripe/webhook",
        content=event_body,
        headers={"stripe-signature": "sig"},
    )
    assert webhook_res.status_code == 200
    assert webhook_res.json()["granted"] is True

    me_res = client.get("/billing/me")
    me_payload = me_res.json()
    assert me_payload["owner_mode_enabled"] is False
    assert me_payload["factory_mode_status"] == "active"
    assert me_payload["factory_mode_access"] == "one_time"
    assert me_payload["factory_mode_purchased_at"] is not None
    assert receipt_calls[0]["item_description"] == "Factory Mode one-time access"

    receipts_res = client.get("/billing/receipts")
    receipts = receipts_res.json()["items"]
    latest = receipts[0]
    assert latest["plan_kind"] == "factory_access"
    assert latest["access_mode"] == "one_time"
    assert latest["purchase_label"] == "Factory Mode One-Time"


def test_factory_subscription_checkout_and_webhook_grants_access(monkeypatch) -> None:
    client = TestClient(app, headers={"X-Tenant-ID": "billing-factory-subscription"})
    reference = f"ps_factory_sub_{uuid4().hex[:12]}"
    monkeypatch.setattr(billing, "PAYSTACK_SECRET_KEY", "psk_test_secret")
    monkeypatch.setattr(billing, "PAYSTACK_CURRENCY", "GHS")
    monkeypatch.setattr(billing, "PAYSTACK_CALLBACK_URL", "http://localhost:3000/?checkout=success&provider=paystack")
    monkeypatch.setattr(app_settings, "PAYSTACK_SECRET_KEY", "psk_test_secret")
    monkeypatch.setattr(app_settings, "FACTORY_MODE_SUBSCRIPTION_STRIPE_PRICE_ID", "price_factory_subscription")

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_request(method, url, headers=None, json=None, timeout=None, params=None, data=None):
        if method == "POST" and url.endswith("/transaction/initialize"):
            assert json["metadata"]["plan_kind"] == "factory_access"
            assert json["metadata"]["access_mode"] == "subscription"
            return _FakeResponse(
                {
                    "status": True,
                    "data": {
                        "authorization_url": "https://paystack.test/factory-checkout",
                        "reference": reference,
                        "access_code": "ps_access_factory",
                    },
                }
            )
        if method == "GET" and url.endswith(f"/transaction/verify/{reference}"):
            return _FakeResponse(
                {
                    "status": True,
                    "data": {
                        "status": "success",
                        "amount": 3900,
                        "currency": "GHS",
                        "reference": reference,
                        "metadata": {
                            "plan_id": "factory_subscription",
                            "plan_kind": "factory_access",
                            "access_mode": "subscription",
                            "user_email": "admin@procreator.local",
                            "tenant_id": "billing-factory-subscription",
                        },
                    },
                }
            )
        raise AssertionError(f"Unexpected Paystack request: {method} {url}")

    monkeypatch.setattr(billing.requests, "request", fake_request)
    receipt_calls: list[dict[str, object]] = []

    def fake_send_purchase_receipt_email(**kwargs):
        receipt_calls.append(kwargs)
        return True

    monkeypatch.setattr(billing, "send_purchase_receipt_email", fake_send_purchase_receipt_email)

    checkout_res = client.post(
        "/billing/purchase/checkout",
        json={"plan_id": "factory_subscription", "provider": "paystack"},
    )
    assert checkout_res.status_code == 200
    checkout_payload = checkout_res.json()
    assert checkout_payload["provider"] == "paystack"
    assert checkout_payload["checkout_url"] == "https://paystack.test/factory-checkout"
    assert checkout_payload["session_id"] == reference

    event_body = json.dumps(
        {
            "event": "charge.success",
            "data": {
                "reference": reference,
                "metadata": {
                    "plan_id": "factory_subscription",
                    "plan_kind": "factory_access",
                    "access_mode": "subscription",
                    "user_email": "admin@procreator.local",
                    "tenant_id": "billing-factory-subscription",
                },
            },
        }
    ).encode("utf-8")
    signature = hmac.new(b"psk_test_secret", event_body, hashlib.sha512).hexdigest()

    webhook_res = client.post(
        "/billing/paystack/webhook",
        content=event_body,
        headers={"x-paystack-signature": signature},
    )
    assert webhook_res.status_code == 200
    assert webhook_res.json()["granted"] is True

    me_res = client.get("/billing/me")
    me_payload = me_res.json()
    assert me_payload["owner_mode_enabled"] is False
    assert me_payload["factory_mode_status"] == "active"
    assert me_payload["factory_mode_access"] == "subscription"
    assert me_payload["factory_mode_renewal_date"] is not None
    assert receipt_calls[0]["item_description"] == "Factory Mode subscription access for 30 days"

    receipts_res = client.get("/billing/receipts")
    receipts = receipts_res.json()["items"]
    latest = receipts[0]
    assert latest["plan_kind"] == "factory_access"
    assert latest["access_mode"] == "subscription"
    assert latest["purchase_label"] == "Factory Mode Subscription"


def test_admin_subscription_list_and_update() -> None:
    client = billing_client()

    status_res = client.get("/billing/admin/2fa/status")
    assert status_res.status_code == 200
    status_payload = status_res.json()
    assert status_payload["enabled"] is False

    verify_res = client.post(
        "/billing/admin/access/verify",
        json={"password": "ChangeMe123!"},
    )
    assert verify_res.status_code == 200
    admin_token = verify_res.json()["access_token"]
    admin_headers = {"X-Admin-Access-Token": admin_token}

    list_res = client.get("/billing/admin/users", headers=admin_headers)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert items
    email = items[0]["email"]

    update_res = client.post(
        f"/billing/admin/users/{email}/update",
        json={
            "plan_name": "pro",
            "status": "active",
            "credits_delta": 25,
            "factory_mode_access": "subscription",
            "factory_mode_renewal_date": "2026-05-01T10:30:00",
        },
        headers=admin_headers,
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["email"] == email
    assert updated["plan_name"] == "pro"
    assert updated["factory_mode_status"] == "active"
    assert updated["factory_mode_access"] == "subscription"
    assert updated["factory_mode_renewal_date"] is not None

    revoke_res = client.post(
        f"/billing/admin/users/{email}/update",
        json={"factory_mode_access": "none"},
        headers=admin_headers,
    )
    assert revoke_res.status_code == 200
    revoked = revoke_res.json()
    assert revoked["factory_mode_status"] == "inactive"
    assert revoked["factory_mode_access"] == "none"


def test_admin_moderation_and_test_purchase_cleanup() -> None:
    client = billing_client()

    status_res = client.get("/billing/admin/2fa/status")
    assert status_res.status_code == 200

    verify_res = client.post(
        "/billing/admin/access/verify",
        json={"password": "ChangeMe123!"},
    )
    assert verify_res.status_code == 200
    admin_headers = {"X-Admin-Access-Token": verify_res.json()["access_token"]}

    username = f"test-abuser-{uuid4().hex[:8]}@example.com"
    create_res = client.post(
        "/auth/users",
        json={"email": username, "password": "Password123!", "role": "user"},
    )
    assert create_res.status_code == 200

    suspend_res = client.post(
        f"/billing/admin/users/{username}/update",
        json={"status": "suspended"},
        headers=admin_headers,
    )
    assert suspend_res.status_code == 200

    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == username)).first()
        assert user is not None
        assert user.is_active is False

    delete_res = client.delete(f"/billing/admin/users/{username}", headers=admin_headers)
    assert delete_res.status_code == 200
    assert delete_res.json()["deleted"] is True

    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == username)).first()
        assert user is None

    purge_a = f"test-purge-{uuid4().hex[:8]}@example.com"
    purge_b = f"test-purge-{uuid4().hex[:8]}@example.com"
    for email in (purge_a, purge_b):
        create_res = client.post(
            "/auth/users",
            json={"email": email, "password": "Password123!", "role": "user"},
        )
        assert create_res.status_code == 200

    purge_res = client.delete(
        "/billing/admin/users/actions/purge-test-purchases",
        headers=admin_headers,
    )
    assert purge_res.status_code == 200
    purge_payload = purge_res.json()
    assert purge_payload["deleted_count"] >= 2
    assert purge_a in purge_payload["deleted_emails"]
    assert purge_b in purge_payload["deleted_emails"]


def test_admin_pricing_settings_are_editable() -> None:
    client = billing_client()
    tenant_headers = {"X-Tenant-ID": f"pricing-admin-{uuid4().hex[:8]}"}

    verify_res = client.post(
        "/billing/admin/access/verify",
        json={"password": "ChangeMe123!"},
        headers=tenant_headers,
    )
    assert verify_res.status_code == 200
    admin_headers = {
        **tenant_headers,
        "X-Admin-Access-Token": verify_res.json()["access_token"],
    }

    get_res = client.get("/billing/admin/pricing", headers=admin_headers)
    assert get_res.status_code == 200
    payload = get_res.json()
    assert payload["owner_mode_enabled"] is False
    assert payload["receipts_live_mode"] is False
    assert payload["character_slot_addon_size"] == 5
    assert any(plan["id"] == "pro" for plan in payload["plans"])

    update_res = client.patch(
        "/billing/admin/pricing",
        json={
            "moderate_credits": 700,
            "moderate_price_usd": 17,
            "moderate_base_character_slots": 6,
            "moderate_stripe_price_id": "price_moderate_admin",
            "pro_credits": 2400,
            "pro_price_usd": 59,
            "pro_base_character_slots": 12,
            "pro_stripe_price_id": "price_pro_admin",
            "studio_credits": 7200,
            "studio_price_usd": 129,
            "studio_base_character_slots": 18,
            "studio_stripe_price_id": "price_studio_admin",
            "factory_one_time_price_usd": 159,
            "factory_one_time_stripe_price_id": "price_factory_one_time_admin",
            "factory_subscription_price_usd": 45,
            "factory_subscription_stripe_price_id": "price_factory_subscription_admin",
            "owner_mode_enabled": True,
            "receipts_live_mode": True,
            "free_base_character_slots": 2,
            "character_slot_addon_size": 5,
            "character_slot_addon_cost_credits": 80,
        },
        headers=admin_headers,
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    pro_plan = next(plan for plan in updated["plans"] if plan["id"] == "pro")
    assert pro_plan["credits"] == 2400
    assert pro_plan["price_usd"] == 59
    assert pro_plan["base_character_slots"] == 12
    factory_one_time_plan = next(plan for plan in updated["plans"] if plan["id"] == "factory_one_time")
    assert factory_one_time_plan["price_usd"] == 159
    assert factory_one_time_plan["stripe_price_id"] == "price_factory_one_time_admin"
    factory_subscription_plan = next(plan for plan in updated["plans"] if plan["id"] == "factory_subscription")
    assert factory_subscription_plan["price_usd"] == 45
    assert factory_subscription_plan["stripe_price_id"] == "price_factory_subscription_admin"
    assert updated["owner_mode_enabled"] is True
    assert updated["receipts_live_mode"] is True
    assert updated["free_base_character_slots"] == 2
    assert updated["character_slot_addon_cost_credits"] == 80

    restore_res = client.patch(
        "/billing/admin/pricing",
        json={
            "moderate_credits": 500,
            "moderate_price_usd": 15,
            "moderate_base_character_slots": 5,
            "moderate_stripe_price_id": "",
            "pro_credits": 2000,
            "pro_price_usd": 49,
            "pro_base_character_slots": 10,
            "pro_stripe_price_id": "",
            "studio_credits": 6000,
            "studio_price_usd": 119,
            "studio_base_character_slots": 15,
            "studio_stripe_price_id": "",
            "factory_one_time_price_usd": 149,
            "factory_one_time_stripe_price_id": "",
            "factory_subscription_price_usd": 39,
            "factory_subscription_stripe_price_id": "",
            "owner_mode_enabled": False,
            "receipts_live_mode": False,
            "free_base_character_slots": 100,
            "character_slot_addon_size": 5,
            "character_slot_addon_cost_credits": 50,
        },
        headers=admin_headers,
    )
    assert restore_res.status_code == 200


def test_purchase_character_slot_pack_consumes_credits_and_grants_slots() -> None:
    client = billing_client()
    tenant_headers = {"X-Tenant-ID": f"slot-purchase-{uuid4().hex[:8]}"}

    me_res = client.get("/billing/me", headers=tenant_headers)
    assert me_res.status_code == 200
    start = me_res.json()

    purchase_res = client.post(
        "/billing/character-slots/purchase",
        json={"pack_count": 2},
        headers=tenant_headers,
    )
    assert purchase_res.status_code == 200
    updated = purchase_res.json()
    pack_cost = start["character_slots"]["addon_pack_cost_credits"]
    pack_size = start["character_slots"]["addon_pack_size"]

    assert updated["credits_balance"] == start["credits_balance"] - (pack_cost * 2)
    assert updated["extra_character_slots"] == start["extra_character_slots"] + (pack_size * 2)
    assert updated["character_slots"]["extra_slots"] == pack_size * 2
    assert updated["character_slots"]["total_slots"] == start["character_slots"]["total_slots"] + (pack_size * 2)


def test_admin_access_verify_with_totp(monkeypatch) -> None:
    client = billing_client()
    monkeypatch.setattr(billing, "ADMIN_2FA_ENABLED", True)
    monkeypatch.setattr(billing, "ADMIN_2FA_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    monkeypatch.setattr(billing, "ADMIN_DASHBOARD_PASSWORD", "ChangeMe123!")

    current_ts = 1_800_000_000
    code = billing._totp_code(
        billing._normalize_totp_secret("JBSWY3DPEHPK3PXP"),
        current_ts,
    )

    class _FixedDatetime:
        @staticmethod
        def now(_tz=None):
            import datetime as _dt

            return _dt.datetime.fromtimestamp(current_ts, tz=_dt.timezone.utc)

    monkeypatch.setattr(billing, "datetime", _FixedDatetime)

    missing_otp_res = client.post(
        "/billing/admin/access/verify",
        json={"password": "ChangeMe123!"},
    )
    assert missing_otp_res.status_code == 400

    bad_otp_res = client.post(
        "/billing/admin/access/verify",
        json={"password": "ChangeMe123!", "otp_code": "000000"},
    )
    assert bad_otp_res.status_code == 401

    ok_res = client.post(
        "/billing/admin/access/verify",
        json={"password": "ChangeMe123!", "otp_code": code},
    )
    assert ok_res.status_code == 200
    assert ok_res.json()["access_token"]


def test_mock_purchase_blocked_in_production(monkeypatch) -> None:
    client = billing_client()
    monkeypatch.setattr(billing, "ENVIRONMENT", "production")

    response = client.post("/billing/purchase/mock", json={"plan_id": "pro"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Mock credit purchase is disabled in production"


def test_receipt_delete_purges_own_ledger_entry_in_test_mode() -> None:
    client = billing_client()

    first_purchase_res = client.post("/billing/purchase/mock", json={"plan_id": "pro"})
    assert first_purchase_res.status_code == 200
    second_purchase_res = client.post("/billing/purchase/mock", json={"plan_id": "studio"})
    assert second_purchase_res.status_code == 200

    receipts_res = client.get("/billing/receipts")
    assert receipts_res.status_code == 200
    receipts = receipts_res.json()["items"]
    assert len(receipts) >= 2
    receipt_id = receipts[0]["receipt_id"]
    assert receipt_id
    untouched_receipt_id = receipts[1]["receipt_id"]
    assert untouched_receipt_id and untouched_receipt_id != receipt_id

    delete_res = client.delete(f"/billing/receipts/{receipt_id}")
    assert delete_res.status_code == 200
    assert delete_res.json() == {
        "deleted": True,
        "receipt_id": receipt_id,
        "deleted_permanently": True,
    }

    remaining_res = client.get("/billing/receipts")
    assert remaining_res.status_code == 200
    remaining = remaining_res.json()["items"]
    assert all(item["receipt_id"] != receipt_id for item in remaining)
    assert any(item["receipt_id"] == untouched_receipt_id for item in remaining)

    with Session(engine) as session:
        entry = session.exec(select(CreditLedgerEntry).where(CreditLedgerEntry.id == receipt_id)).first()
    assert entry is None

    with Session(engine) as session:
        hidden = session.exec(select(HiddenReceipt).where(HiddenReceipt.ledger_entry_id == receipt_id)).all()
    assert hidden == []


def test_receipt_delete_keeps_audit_copy_in_live_mode() -> None:
    client = billing_client()

    try:
        with Session(engine) as session:
            settings = app_settings.get_or_create_settings(session)
            settings.billing_receipts_live_mode = True
            session.add(settings)
            session.commit()
            session.refresh(settings)

        first_purchase_res = client.post("/billing/purchase/mock", json={"plan_id": "pro"})
        assert first_purchase_res.status_code == 200
        second_purchase_res = client.post("/billing/purchase/mock", json={"plan_id": "studio"})
        assert second_purchase_res.status_code == 200

        receipts_res = client.get("/billing/receipts")
        assert receipts_res.status_code == 200
        receipts = receipts_res.json()["items"]
        assert len(receipts) >= 2
        receipt_id = receipts[0]["receipt_id"]
        assert receipt_id
        untouched_receipt_id = receipts[1]["receipt_id"]
        assert untouched_receipt_id and untouched_receipt_id != receipt_id

        delete_res = client.delete(f"/billing/receipts/{receipt_id}")
        assert delete_res.status_code == 200
        assert delete_res.json() == {
            "deleted": True,
            "receipt_id": receipt_id,
            "deleted_permanently": False,
        }

        remaining_res = client.get("/billing/receipts")
        assert remaining_res.status_code == 200
        remaining = remaining_res.json()["items"]
        assert all(item["receipt_id"] != receipt_id for item in remaining)
        assert any(item["receipt_id"] == untouched_receipt_id for item in remaining)

        with Session(engine) as session:
            entry = session.exec(select(CreditLedgerEntry).where(CreditLedgerEntry.id == receipt_id)).first()
        assert entry is not None

        with Session(engine) as session:
            hidden = session.exec(select(HiddenReceipt).where(HiddenReceipt.ledger_entry_id == receipt_id)).all()
        assert hidden
    finally:
        with Session(engine) as session:
            settings = app_settings.get_or_create_settings(session)
            settings.billing_receipts_live_mode = False
            session.add(settings)
            session.commit()
            session.refresh(settings)


def test_transaction_records_can_be_cleared_in_test_mode() -> None:
    client = TestClient(app, headers={"X-Tenant-ID": "billing-clear-test"})

    client.post("/billing/purchase/mock", json={"plan_id": "moderate"})
    client.post("/billing/purchase/mock", json={"plan_id": "studio"})
    client.post("/billing/consume", json={"amount": 5, "reason": "manual spend"})

    records_res = client.get("/billing/records")
    assert records_res.status_code == 200
    assert records_res.json()["items"]

    clear_res = client.delete("/billing/records")
    assert clear_res.status_code == 200
    payload = clear_res.json()
    assert payload["deleted"] is True
    assert payload["deleted_count"] > 0

    cleared_records_res = client.get("/billing/records")
    assert cleared_records_res.status_code == 200
    assert cleared_records_res.json()["items"] == []

    receipts_res = client.get("/billing/receipts")
    assert receipts_res.status_code == 200
    assert receipts_res.json()["items"] == []

    with Session(engine) as session:
        entries = session.exec(select(CreditLedgerEntry).where(CreditLedgerEntry.tenant_id == "billing-clear-test")).all()
    assert entries == []


def test_transaction_records_include_full_ledger_history() -> None:
    client = billing_client()

    purchase_res = client.post("/billing/purchase/mock", json={"plan_id": "pro"})
    assert purchase_res.status_code == 200
    consume_res = client.post("/billing/consume", json={"amount": 5, "reason": "manual spend"})
    assert consume_res.status_code == 200

    records_res = client.get("/billing/records")
    assert records_res.status_code == 200
    records = records_res.json()["items"]
    assert records
    kinds = {item["kind"] for item in records}
    assert "grant" in kinds or "consume" in kinds
    assert any(item["action"] == "manual_consume" for item in records)
