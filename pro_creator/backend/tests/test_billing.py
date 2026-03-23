from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.routers import billing


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
        json={"plan_name": "pro", "status": "active", "credits_delta": 25},
        headers=admin_headers,
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["email"] == email
    assert updated["plan_name"] == "pro"


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
