from fastapi.testclient import TestClient

from app.config import PROJECTS_DIR
from app.main import app
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
