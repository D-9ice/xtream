from fastapi.testclient import TestClient
from uuid import uuid4

from app import auth as auth_module
from app.main import app


def test_auth_token_tenant_claim_enforced(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr(auth_module, "AUTH_REQUIRED", True)
    tenant_a = f"tenant-a-{uuid4().hex[:8]}"
    tenant_b = f"tenant-b-{uuid4().hex[:8]}"
    token = auth_module.create_access_token("admin@procreator.local", "admin", tenant_id=tenant_a)

    ok = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": tenant_a,
        },
    )
    assert ok.status_code == 200

    mismatch = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": tenant_b,
        },
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["detail"] == "Token tenant does not match request tenant"


def test_billing_balance_isolation_by_tenant() -> None:
    client = TestClient(app)
    tenant_a = f"tenant-a-{uuid4().hex[:8]}"
    tenant_b = f"tenant-b-{uuid4().hex[:8]}"

    tenant_a_before = client.get("/billing/me", headers={"X-Tenant-ID": tenant_a})
    assert tenant_a_before.status_code == 200
    start_a = tenant_a_before.json()["credits_balance"]

    consume = client.post(
        "/billing/consume",
        json={"amount": 7, "reason": "tenant-a-usage"},
        headers={"X-Tenant-ID": tenant_a},
    )
    assert consume.status_code == 200
    assert consume.json()["credits_balance"] == max(0, start_a - 7)

    tenant_b = client.get("/billing/me", headers={"X-Tenant-ID": tenant_b})
    assert tenant_b.status_code == 200
    # tenant-b should remain on its own untouched balance.
    assert tenant_b.json()["credits_balance"] == 1000
