import pytest
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import PROJECTS_DIR
from app.main import app
import app.services.grok_imagine_engine as grok_imagine_engine
import app.routers.video as video_router
from app.utils.file_manager import read_json_artifact, write_json_artifact


def _create_project(client: TestClient) -> str:
    response = client.post(
        "/project/create",
        json={"title": "Video Feature Test", "topic": "API validation"},
    )
    assert response.status_code == 200
    return response.json()["project_id"]


def test_template_route_creates_media_and_export_catalog_is_informational(monkeypatch, tmp_path) -> None:
    client = TestClient(app)
    project_id = _create_project(client)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")

    monkeypatch.setattr(
        video_router,
        "_materialize_video",
        lambda _project_id, _temp_path: (
            "project/video/final.mp4",
            source,
            {"duration": 4.0, "width": 1920, "height": 1080, "has_audio": True},
        ),
    )

    def fake_run_ffmpeg(args, **_kwargs):
        Path(args[-1]).write_bytes(b"template-video")

    monkeypatch.setattr(video_router, "_run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(
        video_router,
        "_probe_media",
        lambda _path: {"duration": 4.0, "width": 1920, "height": 1080, "has_audio": True},
    )

    template_res = client.post(f"/video/templates?project_id={project_id}")
    assert template_res.status_code == 200
    assert template_res.json()["status"] == "complete"

    presets_res = client.post(f"/video/export-presets?project_id={project_id}")
    assert presets_res.status_code == 200
    assert presets_res.json()["status"] == "ready"

    template_artifact = read_json_artifact(
        PROJECTS_DIR / project_id / "video" / "template_plan.json"
    )
    assert template_artifact.get("selected_template")
    assert template_artifact.get("output_path")
    assert template_artifact.get("validated") is True

    export_artifact = read_json_artifact(
        PROJECTS_DIR / project_id / "video" / "export_presets.json"
    )
    assert export_artifact.get("presets")
    assert export_artifact.get("recommended")


def test_screen_record_requires_real_captured_media() -> None:
    client = TestClient(app)
    project_id = _create_project(client)
    response = client.post(f"/video/screen-record?project_id={project_id}")
    assert response.status_code == 400
    assert "captured screen recording" in response.json()["detail"]


def test_screen_record_processes_uploaded_media(monkeypatch) -> None:
    client = TestClient(app)
    project_id = _create_project(client)

    monkeypatch.setattr(
        video_router,
        "_probe_media",
        lambda _path: {"duration": 2.0, "width": 1280, "height": 720, "has_audio": True},
    )

    def fake_run_ffmpeg(args, **_kwargs):
        Path(args[-1]).write_bytes(b"processed-video")

    monkeypatch.setattr(video_router, "_run_ffmpeg", fake_run_ffmpeg)

    response = client.post(
        f"/video/screen-record?project_id={project_id}",
        files={"screen": ("screen.webm", b"captured-screen", "video/webm")},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "complete"
    artifact = read_json_artifact(
        PROJECTS_DIR / project_id / "video" / "screen_record.json"
    )
    assert artifact["webcam_overlay"] is False
    assert artifact["video_path"]


def test_magic_cut_requires_transcript_and_media() -> None:
    client = TestClient(app)
    project_id = _create_project(client)
    response = client.post(f"/video/magic-cut?project_id={project_id}")
    assert response.status_code == 400


def test_export_requires_source_video() -> None:
    client = TestClient(app)
    project_id = _create_project(client)

    response = client.post(
        "/video/export",
        json={"project_id": project_id, "preset": "youtube"},
    )
    assert response.status_code == 400
    assert "No source video found" in response.json()["detail"]


def test_grok_poll_honors_cancellation_before_network(monkeypatch) -> None:
    def unexpected_get(*_args, **_kwargs):
        raise AssertionError("network polling must not run after cancellation")

    monkeypatch.setattr(grok_imagine_engine.requests, "get", unexpected_get)
    with pytest.raises(grok_imagine_engine.RenderCancelled):
        grok_imagine_engine._poll_video_url("request-cancelled", cancel_check=lambda: True)


def test_grok_imagine_segments_chain_last_frame_into_next_segment(
    monkeypatch, tmp_path
) -> None:
    project_id = "grok-chain-test"
    calls: list[bytes | None] = []

    monkeypatch.setattr(grok_imagine_engine, "XAI_API_KEY", "test-key")
    monkeypatch.setattr(grok_imagine_engine.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(grok_imagine_engine, "_load_bundle", lambda _project_id: {"project_id": project_id})
    monkeypatch.setattr(
        grok_imagine_engine,
        "_load_scene_texts",
        lambda _project_id: [(1, "Scene one"), (2, "Scene two")],
    )

    def fake_render_segment(
        *,
        ffmpeg_path,
        project_id,
        bundle,
        scene_text,
        scene_index,
        total_segments,
        temp_path,
        initial_frame_bytes=None,
        cancel_check=None,
    ):
        calls.append(initial_frame_bytes)
        segment_path = temp_path / f"segment_{scene_index}.mp4"
        segment_path.write_bytes(f"segment-{scene_index}".encode("utf-8"))
        next_frame = f"frame-{scene_index}".encode("utf-8")
        return segment_path, next_frame

    def fake_concat_videos(ffmpeg_path, clip_paths, output_path):
        output_path.write_bytes(b"final-video")

    monkeypatch.setattr(grok_imagine_engine, "_render_segment", fake_render_segment)
    monkeypatch.setattr(grok_imagine_engine, "_concat_videos", fake_concat_videos)
    monkeypatch.setattr(grok_imagine_engine, "_validate_video_file", lambda _path: None)
    monkeypatch.setattr(
        grok_imagine_engine.storage_client,
        "write_file",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        grok_imagine_engine.storage_client,
        "write_text",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        grok_imagine_engine.storage_client,
        "public_url",
        lambda key: f"public://{key}",
    )
    monkeypatch.setattr(grok_imagine_engine, "project_key", lambda pid, suffix: f"{pid}/{suffix}")

    result = grok_imagine_engine.render_grok_imagine_video(project_id)

    assert calls == [None, b"frame-1"]
    assert result["video_path"].startswith("public://")


def test_grok_imagine_includes_start_and_end_credits_sequences(
    monkeypatch, tmp_path
) -> None:
    project_id = "grok-credits-test"
    scene_texts: list[str] = []

    monkeypatch.setattr(grok_imagine_engine, "XAI_API_KEY", "test-key")
    monkeypatch.setattr(grok_imagine_engine.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        grok_imagine_engine,
        "_load_bundle",
        lambda _project_id: {
            "project_id": project_id,
            "start_credits": "Cast\nLead Actor",
            "end_credits": "Thanks for watching",
        },
    )
    monkeypatch.setattr(
        grok_imagine_engine,
        "_load_scene_texts",
        lambda _project_id: [(1, "Scene one"), (2, "Scene two")],
    )

    def fake_render_segment(
        *,
        ffmpeg_path,
        project_id,
        bundle,
        scene_text,
        scene_index,
        total_segments,
        temp_path,
        initial_frame_bytes=None,
        cancel_check=None,
    ):
        scene_texts.append(scene_text)
        segment_path = temp_path / f"segment_{scene_index}.mp4"
        segment_path.write_bytes(f"segment-{scene_index}".encode("utf-8"))
        next_frame = f"frame-{scene_index}".encode("utf-8")
        return segment_path, next_frame

    def fake_concat_videos(ffmpeg_path, clip_paths, output_path):
        output_path.write_bytes(b"final-video")

    monkeypatch.setattr(grok_imagine_engine, "_render_segment", fake_render_segment)
    monkeypatch.setattr(grok_imagine_engine, "_concat_videos", fake_concat_videos)
    monkeypatch.setattr(grok_imagine_engine, "_validate_video_file", lambda _path: None)
    monkeypatch.setattr(
        grok_imagine_engine.storage_client,
        "write_file",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        grok_imagine_engine.storage_client,
        "write_text",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        grok_imagine_engine.storage_client,
        "public_url",
        lambda key: f"public://{key}",
    )
    monkeypatch.setattr(grok_imagine_engine, "project_key", lambda pid, suffix: f"{pid}/{suffix}")

    result = grok_imagine_engine.render_grok_imagine_video(project_id)

    assert scene_texts[0].startswith("__CREDITS_START__")
    assert scene_texts[-1].startswith("__CREDITS_END__")
    assert len(scene_texts) == 4
    assert result["video_path"].startswith("public://")


def test_internal_social_vertical_export_alias_is_real_media_output(monkeypatch, tmp_path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")

    monkeypatch.setattr(
        video_router,
        "_materialize_video",
        lambda _project_id, _temp_path: (
            "project/video/final.mp4",
            source,
            {"duration": 4.0, "width": 1920, "height": 1080, "has_audio": True},
        ),
    )

    def fake_run_ffmpeg(args, **_kwargs):
        Path(args[-1]).write_bytes(b"vertical-export")

    monkeypatch.setattr(video_router, "_run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(
        video_router,
        "_probe_media",
        lambda _path: {"duration": 4.0, "width": 1080, "height": 1920, "has_audio": True},
    )
    monkeypatch.setattr(video_router.storage_client, "write_file", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(video_router.storage_client, "write_text", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        video_router.storage_client,
        "public_url",
        lambda key: f"public://{key}",
    )

    response = video_router.export_preset(
        video_router.ExportPresetRequest(project_id="scheduled-project", preset="social-vertical"),
        session=None,
        current_user=None,
    )
    assert response.export_path.endswith("/video/exports/social-vertical.mp4")


def test_multitrack_uses_ducking_and_loudness_normalization(monkeypatch) -> None:
    client = TestClient(app)
    project_id = _create_project(client)
    audio_dir = PROJECTS_DIR / project_id / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "scene_1.wav").write_bytes(b"voice")
    (audio_dir / "music_bed.wav").write_bytes(b"music")

    calls: list[list[str]] = []

    def fake_run_ffmpeg(args, **_kwargs):
        calls.append(list(args))
        Path(args[-1]).write_bytes(b"mixed-audio")

    monkeypatch.setattr(video_router, "_run_ffmpeg", fake_run_ffmpeg)

    response = client.post(f"/video/multitrack?project_id={project_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "complete"
    flattened = " ".join(" ".join(call) for call in calls)
    assert "sidechaincompress" in flattened
    assert "loudnorm" in flattened
