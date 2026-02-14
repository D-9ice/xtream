from fastapi.testclient import TestClient

from app.main import app


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
