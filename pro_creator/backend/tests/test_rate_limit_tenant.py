from fastapi.testclient import TestClient

from app import main
from app.main import app


def test_heavy_rate_limit_is_tenant_scoped(monkeypatch):
    client = TestClient(app)

    monkeypatch.setattr(main, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(main, "RATE_LIMIT_HEAVY_REQUESTS", 2)
    monkeypatch.setattr(main, "RATE_LIMIT_WINDOW_SECONDS", 60)
    with main._rate_limit_lock:
        main._rate_limit_store.clear()

    status, project_a = _create_project(client, "tenant-a")
    assert status == 200
    status, project_b = _create_project(client, "tenant-b")
    assert status == 200

    statuses_a = [
        _generate_script(client, "tenant-a", project_a["project_id"])
        for _ in range(3)
    ]
    statuses_b = [
        _generate_script(client, "tenant-b", project_b["project_id"])
        for _ in range(2)
    ]

    assert statuses_a[:2] == [200, 200]
    assert statuses_a[2] == 429
    assert statuses_b == [200, 200]


def _create_project(client: TestClient, tenant_id: str):
    response = client.post(
        "/project/create",
        json={"title": f"{tenant_id} project", "topic": "rate limit test"},
        headers={"X-Tenant-ID": tenant_id},
    )
    return response.status_code, response.json()


def _generate_script(client: TestClient, tenant_id: str, project_id: str) -> int:
    response = client.post(
        "/script/generate",
        json={
            "project_id": project_id,
            "topic": "tenant rate limit",
            "duration_minutes": 0.25,
            "tone": "neutral",
        },
        headers={"X-Tenant-ID": tenant_id},
    )
    return response.status_code
