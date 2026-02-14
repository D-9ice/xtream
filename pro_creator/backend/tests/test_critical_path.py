from uuid import uuid4
import shutil

from fastapi.testclient import TestClient
from jose import jwt

from app.config import JWT_ALGORITHM, JWT_SECRET
from app.main import app


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_auth_project_pipeline_and_export_flow() -> None:
    client = TestClient(app)
    email = f"test-{uuid4().hex[:10]}@example.com"
    password = "TestPass123!"

    create_user_res = client.post(
        "/auth/users",
        json={"email": email, "password": password, "role": "admin"},
    )
    assert create_user_res.status_code == 200

    bad_login = client.post(
        "/auth/login",
        data={"username": email, "password": "wrong-pass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert bad_login.status_code == 401

    login_res = client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = _auth_headers(token)
    claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert claims["sub"] == email
    assert claims["role"] == "admin"

    me_res = client.get("/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert "email" in me_res.json()

    project_res = client.post(
        "/project/create",
        json={"title": "Pipeline Test", "topic": "Critical path validation"},
        headers=headers,
    )
    assert project_res.status_code == 200
    project_id = project_res.json()["project_id"]

    script_res = client.post(
        "/script/generate",
        json={
            "project_id": project_id,
            "topic": "Critical path validation",
            "duration_minutes": 1,
            "tone": "neutral",
        },
        headers=headers,
    )
    assert script_res.status_code == 200
    assert len(script_res.json()["scenes"]) >= 1

    image_res = client.post(
        "/image/generate",
        json={"project_id": project_id, "prompt": "Studio scene", "style": "cinematic"},
        headers=headers,
    )
    assert image_res.status_code == 200
    assert project_id in image_res.json()["image_path"]

    voice_res = client.post(
        "/voice/generate",
        json={
            "project_id": project_id,
            "text": "Narration for critical pipeline test",
            "voice_profile": "default",
        },
        headers=headers,
    )
    assert voice_res.status_code == 200
    assert project_id in voice_res.json()["audio_path"]

    video_res = client.post(
        "/video/render",
        json={"project_id": project_id},
        headers=headers,
    )
    if shutil.which("ffmpeg"):
        assert video_res.status_code == 200
        assert project_id in video_res.json()["video_path"]

        export_res = client.post(
            "/video/export",
            json={"project_id": project_id, "preset": "youtube"},
            headers=headers,
        )
        assert export_res.status_code == 200
        assert project_id in export_res.json()["export_path"]
    else:
        assert video_res.status_code == 400
        assert "ffmpeg is required" in video_res.json()["detail"]

        export_res = client.post(
            "/video/export",
            json={"project_id": project_id, "preset": "youtube"},
            headers=headers,
        )
        assert export_res.status_code == 400

    status_res = client.get(f"/video/export/status/{project_id}?presets=youtube", headers=headers)
    assert status_res.status_code == 200
    exports = status_res.json()["exports"]
    assert len(exports) == 1
    assert exports[0]["preset"] == "youtube"
    if shutil.which("ffmpeg"):
        assert exports[0]["status"] == "complete"
    else:
        assert exports[0]["status"] == "queued"
