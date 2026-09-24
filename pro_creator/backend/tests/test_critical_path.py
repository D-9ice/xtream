from uuid import uuid4
import io
import shutil

from PIL import Image

from fastapi.testclient import TestClient
from jose import jwt

from app.config import JWT_ALGORITHM, JWT_SECRET
from app.main import app
from app.routers import video as video_router
from app.routers import script as script_router
from app.routers import image as image_router
from app.routers import voice as voice_router
from app.storage import project_key, storage_client


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_auth_project_pipeline_and_export_flow(monkeypatch, tmp_path) -> None:
    client = TestClient(app)
    image_buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(32, 48, 64)).save(image_buffer, format="PNG")
    png_bytes = image_buffer.getvalue()

    def _fake_generate_script(topic, duration_minutes, tone, genre=None, **_kwargs):
        return {
            "full_script": "Scene 1\nIntent: validation\nNarration:\nTest narration.\nVisuals:\nStudio.",
            "scenes": [{"id": 1, "text": "Scene 1\nIntent: validation\nNarration:\nTest narration.\nVisuals:\nStudio."}],
        }

    def _fake_generate_image(project_id, scene_id, prompt, style):
        key = project_key(project_id, f"images/scene_{scene_id}.png")
        storage_client.write_bytes(key, png_bytes, content_type="image/png")
        return {"image_path": storage_client.public_url(key)}

    def _fake_generate_voice(project_id, scene_id, text, voice_profile=None):
        key = project_key(project_id, f"audio/scene_{scene_id}.mp3")
        storage_client.write_bytes(key, b"mock-audio", content_type="audio/mpeg")
        return {"audio_path": storage_client.public_url(key), "duration_seconds": 2.0}

    monkeypatch.setattr(script_router, "generate_script", _fake_generate_script)
    monkeypatch.setattr(image_router, "generate_image_for_scene", _fake_generate_image)
    monkeypatch.setattr(voice_router, "generate_voice_for_scene", _fake_generate_voice)
    monkeypatch.setattr(video_router, "generate_image_bytes", lambda **_kwargs: (png_bytes, "xai"))

    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"source-video")
    monkeypatch.setattr(
        video_router,
        "_materialize_video",
        lambda _project_id, _temp_path: (
            "project/video/final.mp4",
            source_path,
            {"duration": 2.0, "width": 1920, "height": 1080, "has_audio": True},
        ),
    )

    def _fake_run_ffmpeg(args, **_kwargs):
        from pathlib import Path
        Path(args[-1]).write_bytes(b"export-video")

    monkeypatch.setattr(video_router, "_run_ffmpeg", _fake_run_ffmpeg)
    monkeypatch.setattr(
        video_router,
        "_probe_media",
        lambda _path: {"duration": 2.0, "width": 1920, "height": 1080, "has_audio": True},
    )

    def _fake_render_video(project_id: str) -> dict[str, str]:
        key = project_key(project_id, "video/final.mp4")
        storage_client.write_bytes(key, b"fake-video-bytes", content_type="video/mp4")
        return {"video_path": storage_client.public_url(key)}

    monkeypatch.setattr(video_router, "render_video", _fake_render_video)
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

    thumbnail_res = client.post(
        "/video/thumbnail/generate",
        json={
            "project_id": project_id,
            "title": "Pipeline Thumbnail",
            "subtitle": "Critical path validation",
            "source": "image",
            "scene_id": 1,
            "format": "png",
        },
        headers=headers,
    )
    assert thumbnail_res.status_code == 200
    assert project_id in thumbnail_res.json()["thumbnail_path"]
    assert thumbnail_res.json()["mode_used"] == "classic"
    assert thumbnail_res.json()["source_used"] == "image"

    thumbnail_ai_res = client.post(
        "/video/thumbnail/generate",
        json={
            "project_id": project_id,
            "mode": "ai",
            "title": "AI Thumbnail",
            "subtitle": "Critical path validation",
            "ai_prompt": "Bold social media composition with strong contrast",
            "style": "cinematic",
            "variant_count": 3,
            "format": "png",
        },
        headers=headers,
    )
    assert thumbnail_ai_res.status_code == 200
    assert project_id in thumbnail_ai_res.json()["thumbnail_path"]
    assert thumbnail_ai_res.json()["mode_used"] == "ai"
    assert len(thumbnail_ai_res.json().get("variants", [])) == 3

    first_variant_key = thumbnail_ai_res.json()["variants"][0]["thumbnail_key"]
    set_primary_res = client.post(
        "/video/thumbnail/set-primary",
        json={"project_id": project_id, "thumbnail_key": first_variant_key},
        headers=headers,
    )
    assert set_primary_res.status_code == 200
    assert project_id in set_primary_res.json()["thumbnail_path"]

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
