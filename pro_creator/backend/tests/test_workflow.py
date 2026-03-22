from fastapi.testclient import TestClient

from app.main import app


def test_guided_workflow_gates_script_characters_and_production() -> None:
    client = TestClient(app)

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Guided Workflow Test",
            "idea_prompt": "A mystery unfolds in a small town.",
            "genre": "Mystery",
            "target_duration_minutes": 3,
        },
    )
    assert create_res.status_code == 200
    project = create_res.json()
    project_id = project["project_id"]
    assert project["workflow_state"] == "draft"

    blocked_prod = client.post(f"/workflow/projects/{project_id}/start-production")
    assert blocked_prod.status_code == 400
    assert "Script approval required" in blocked_prod.json()["detail"]

    blocked_character = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Too Early Character",
            "role_type": "main",
            "description": "Should not be creatable before script approval",
            "select_after_create": True,
        },
    )
    assert blocked_character.status_code == 400
    assert "Script approval required" in blocked_character.json()["detail"]

    script_res = client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Guided Workflow Test",
            "idea_prompt": "A mystery unfolds in a small town.",
            "genre": "Mystery",
            "target_duration_minutes": 3,
            "tone": "cinematic",
        },
    )
    assert script_res.status_code == 200
    assert script_res.json()["workflow_state"] == "script_generated"
    assert script_res.json()["script_draft"]

    chars_locked_res = client.get(f"/workflow/projects/{project_id}/production-summary")
    assert chars_locked_res.status_code == 200
    assert chars_locked_res.json()["script_ready"] is False
    assert chars_locked_res.json()["characters_ready"] is False

    approve_script_res = client.post(f"/workflow/projects/{project_id}/approve-script")
    assert approve_script_res.status_code == 200
    assert approve_script_res.json()["workflow_state"] == "script_approved"
    assert approve_script_res.json()["script_approved"]

    create_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Lead Detective",
            "role_type": "main",
            "description": "Observant, calm, coat-wearing detective",
            "personality_traits": ["observant", "calm"],
            "voice_profile": "default",
            "select_after_create": True,
        },
    )
    assert create_character_res.status_code == 200
    selected_ids = create_character_res.json()["selected_character_ids"]
    assert len(selected_ids) == 1

    approve_characters_res = client.post(
        f"/workflow/projects/{project_id}/approve-characters",
        json={"selected_character_ids": selected_ids},
    )
    assert approve_characters_res.status_code == 200
    assert approve_characters_res.json()["approved_character_ids"] == selected_ids

    summary_res = client.get(f"/workflow/projects/{project_id}/production-summary")
    assert summary_res.status_code == 200
    assert summary_res.json()["script_ready"] is True
    assert summary_res.json()["characters_ready"] is True
    assert summary_res.json()["estimated_credits"] >= 1

    library_res = client.get("/workflow/library")
    assert library_res.status_code == 200
    assert any(
        character["name"] == "Lead Detective"
        for character in library_res.json()["characters"]
    )
