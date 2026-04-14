from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def community_client() -> TestClient:
    return TestClient(app, headers={"X-Tenant-ID": f"community-{uuid4().hex[:12]}"})


def test_community_posts_create_and_list() -> None:
    client = community_client()

    create_res = client.post(
        "/community/posts",
        json={
            "subject": "Feature idea",
            "message": "Let's add a creator showcase and lightweight discussion board.",
        },
    )
    assert create_res.status_code == 200
    created = create_res.json()
    assert created["subject"] == "Feature idea"
    assert created["message"].startswith("Let's add")
    assert created["author_email"]
    assert created["applause_count"] == 0

    applaud_res = client.post(f"/community/posts/{created['post_id']}/applaud")
    assert applaud_res.status_code == 200
    applauded = applaud_res.json()
    assert applauded["applause_count"] == 1

    list_res = client.get("/community/posts")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) == 1
    assert items[0]["post_id"] == created["post_id"]
    assert items[0]["applause_count"] == 1
