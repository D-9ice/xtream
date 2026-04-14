from fastapi.testclient import TestClient

from app.config import PROJECTS_DIR
from app.main import app
import app.services.grok_imagine_engine as grok_imagine_engine
from app.utils.file_manager import read_json_artifact


def _create_project(client: TestClient) -> str:
    response = client.post(
        "/project/create",
        json={"title": "Video Feature Test", "topic": "API validation"},
    )
    assert response.status_code == 200
    return response.json()["project_id"]


def test_video_feature_routes_generate_artifacts() -> None:
    client = TestClient(app)
    project_id = _create_project(client)

    template_res = client.post(f"/video/templates?project_id={project_id}")
    assert template_res.status_code == 200
    assert template_res.json()["status"] == "complete"

    presets_res = client.post(f"/video/export-presets?project_id={project_id}")
    assert presets_res.status_code == 200
    assert presets_res.json()["status"] == "complete"

    screen_res = client.post(f"/video/screen-record?project_id={project_id}")
    assert screen_res.status_code == 200
    assert screen_res.json()["status"] == "complete"

    magic_res = client.post(f"/video/magic-cut?project_id={project_id}")
    assert magic_res.status_code == 200
    assert magic_res.json()["status"] == "complete"

    template_artifact = read_json_artifact(
        PROJECTS_DIR / project_id / "video" / "template_plan.json"
    )
    assert template_artifact.get("selected_template")

    export_artifact = read_json_artifact(
        PROJECTS_DIR / project_id / "video" / "export_presets.json"
    )
    assert export_artifact.get("presets")
    assert export_artifact.get("recommended")

    screen_artifact = read_json_artifact(
        PROJECTS_DIR / project_id / "video" / "screen_record_plan.json"
    )
    assert screen_artifact.get("timeline")

    magic_cut_artifact = read_json_artifact(
        PROJECTS_DIR / project_id / "video" / "magic_cut.json"
    )
    assert magic_cut_artifact.get("project_id") == project_id


def test_export_requires_source_video() -> None:
    client = TestClient(app)
    project_id = _create_project(client)

    response = client.post(
        "/video/export",
        json={"project_id": project_id, "preset": "youtube"},
    )
    assert response.status_code == 400
    assert "No source video found" in response.json()["detail"]


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
    monkeypatch.setattr(
        grok_imagine_engine.storage_client,
        "write_bytes",
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
    monkeypatch.setattr(
        grok_imagine_engine.storage_client,
        "write_bytes",
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
