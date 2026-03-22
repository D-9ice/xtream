from fastapi.testclient import TestClient

from app.main import app
from app.routers import billing


def test_billing_me_and_consume_flow() -> None:
    client = TestClient(app)

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
    client = TestClient(app)

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


def test_admin_access_verify_with_totp(monkeypatch) -> None:
    client = TestClient(app)
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
    client = TestClient(app)
    monkeypatch.setattr(billing, "ENVIRONMENT", "production")

    response = client.post("/billing/purchase/mock", json={"plan_id": "pro"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Mock credit purchase is disabled in production"
