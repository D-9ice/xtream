import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import engine
from app.config import PROJECTS_DIR
from app.main import app
from app.models import CharacterProfile, OrchestrationJob, Project, ProjectCharacterPackage, ProjectScriptVersion, User, UserFeedback
import app.routers.workflow as workflow_router
from app.storage import project_key, storage_client
from app.tenant import reset_current_tenant_id, set_current_tenant_id
import app.services.workflow_service as workflow_service
from app.services.workflow_service import (
    WORKFLOW_TRANSITIONS,
    latest_character_package,
    resolve_approved_production_package,
    transition_project_state,
    validate_workflow_transition,
)


def workflow_client() -> TestClient:
    return TestClient(app, headers={"X-Tenant-ID": f"workflow-{uuid4().hex[:12]}"})


def test_guided_workflow_gates_script_characters_and_production() -> None:
    client = workflow_client()

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
    assert summary_res.json()["workflow_state"] == "production_ready"
    assert summary_res.json()["script_ready"] is True
    assert summary_res.json()["characters_ready"] is True
    assert summary_res.json()["estimated_credits"] >= 1

    library_res = client.get("/workflow/library")
    assert library_res.status_code == 200
    assert any(
        character["name"] == "Lead Detective"
        for character in library_res.json()["characters"]
    )


def test_workflow_library_drops_blank_character_slots() -> None:
    tenant_id = f"blank-character-cleanup-{uuid4().hex[:8]}"
    client = TestClient(app, headers={"X-Tenant-ID": tenant_id})

    with Session(engine) as session:
        session.add(
            CharacterProfile(
                tenant_id=tenant_id,
                name="",
                role_type="main",
                description="",
                visual_prompt_base="",
                negative_prompt_base="",
                consistency_seed="blank-seed",
                identity_hash="blank-hash",
            )
        )
        session.add(
            CharacterProfile(
                tenant_id=tenant_id,
                name="Valid Character",
                role_type="supporting",
                description="Keeps the library list intact.",
                visual_prompt_base="",
                negative_prompt_base="",
                consistency_seed="valid-seed",
                identity_hash="valid-hash",
            )
        )
        session.commit()

    library_res = client.get("/workflow/library")
    assert library_res.status_code == 200
    characters = library_res.json()["characters"]
    assert [character["name"] for character in characters] == ["Valid Character"]

    with Session(engine) as session:
        remaining = session.exec(
            select(CharacterProfile).where(CharacterProfile.tenant_id == tenant_id)
        ).all()
        assert [profile.name for profile in remaining] == ["Valid Character"]


def test_workflow_auto_create_runs_full_pipeline_from_title_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = workflow_client()

    monkeypatch.setattr(
        workflow_service,
        "generate_script",
        lambda topic, duration_minutes, tone, script_provider=None, model_name=None, genre=None: {
            "full_script": "Scene 1: A skyline rescue begins.\nScene 2: The rescue lands safely.",
            "scenes": [
                {"id": 1, "text": "Scene 1: A skyline rescue begins."},
                {"id": 2, "text": "Scene 2: The rescue lands safely."},
            ],
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_image_bytes",
        lambda **_kwargs: (b"fake-image", "image/png"),
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_image_for_scene",
        lambda project_id, scene_id, prompt, style: {
            "image_path": f"/tmp/{project_id}-{scene_id}.png"
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_voice_for_scene",
        lambda project_id, scene_id, text, voice_profile="default": {
            "audio_path": f"/tmp/{project_id}-{scene_id}.wav"
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "render_video",
        lambda project_id: {"video_path": f"https://example.test/{project_id}.mp4"},
    )

    auto_res = client.post(
        "/workflow/auto-create",
        json={"title": "Skyline Rescue", "duration_minutes": 45, "genre": "Adventure"},
    )
    assert auto_res.status_code == 200
    payload = auto_res.json()

    assert payload["project"]["title"] == "Skyline Rescue"
    assert payload["project"]["genre"] == "Adventure"
    assert payload["project"]["topic"] == "Skyline Rescue\n\nGenre: Adventure"
    assert payload["project"]["workflow_state"] == "video_completed"
    assert payload["project"]["target_duration_minutes"] == 45
    assert payload["project"]["script_approved"] is not None
    assert payload["project"]["character_package_approved"] is True
    assert len(payload["project"]["selected_character_ids"]) >= 1
    assert payload["status"]["workflow_state"] == "video_completed"
    assert payload["status"]["queue_status"] == "complete"
    assert payload["requested_duration_minutes"] == 45
    assert payload["applied_duration_minutes"] == 45
    assert payload["max_affordable_duration_minutes"] >= 45
    assert payload["estimated_credits"] >= 1
    assert payload["video_path"] == payload["project"]["final_video_url"]

    status_res = client.get(f"/workflow/projects/{payload['project']['project_id']}/production-status")
    assert status_res.status_code == 200
    assert status_res.json()["workflow_state"] == "video_completed"


def test_workflow_auto_create_uses_custom_cast_and_credits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = workflow_client()
    generate_character_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        workflow_service,
        "generate_script",
        lambda topic, duration_minutes, tone, script_provider=None, model_name=None, genre=None: {
            "full_script": "Scene 1: The studio lights rise.\nScene 2: Credits roll into the finale.",
            "scenes": [
                {"id": 1, "text": "Scene 1: The studio lights rise."},
                {"id": 2, "text": "Scene 2: Credits roll into the finale."},
            ],
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_image_bytes",
        lambda **_kwargs: (b"fake-image", "image/png"),
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_image_for_scene",
        lambda project_id, scene_id, prompt, style: {
            "image_path": f"/tmp/{project_id}-{scene_id}.png"
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_voice_for_scene",
        lambda project_id, scene_id, text, voice_profile="default": {
            "audio_path": f"/tmp/{project_id}-{scene_id}.wav"
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "render_video",
        lambda project_id: {"video_path": f"https://example.test/{project_id}-custom.mp4"},
    )

    def fail_generate_character_profile(**kwargs):
        generate_character_calls.append(kwargs)
        raise AssertionError("AI character generation should be skipped when custom characters are supplied")

    monkeypatch.setattr(workflow_service, "generate_character_profile", fail_generate_character_profile)

    auto_res = client.post(
        "/workflow/auto-create",
        json={
            "title": "Studio Premiere",
            "duration_minutes": 30,
            "genre": "Drama",
            "short_description": "A compact studio-style launch piece.",
            "start_credits": "Starring\nLead Actor\nDirected by X'tream",
            "end_credits": "Thanks for watching\nProduced by X'tream",
            "custom_characters": [
                {
                    "name": "Ava Nova",
                    "role_type": "main",
                    "description": "Confident producer leading the feature launch.",
                }
            ],
        },
    )
    assert auto_res.status_code == 200
    payload = auto_res.json()

    assert payload["project"]["title"] == "Studio Premiere"
    assert payload["project"]["short_description"] == "A compact studio-style launch piece."
    assert payload["project"]["start_credits"] == "Starring\nLead Actor\nDirected by X'tream"
    assert payload["project"]["end_credits"] == "Thanks for watching\nProduced by X'tream"
    assert payload["project"]["workflow_state"] == "video_completed"
    assert payload["project"]["final_video_url"] == payload["video_path"]
    assert len(payload["project"]["selected_character_ids"]) == 1
    assert generate_character_calls == []


def test_auto_create_project_allows_real_events_without_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflow_service,
        "generate_script",
        lambda topic, duration_minutes, tone, script_provider=None, model_name=None, genre=None: {
            "full_script": "Scene 1: Narration leads the archive cut.",
            "scenes": [
                {"id": 1, "text": "Scene 1: Narration leads the archive cut."},
            ],
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_image_bytes",
        lambda **_kwargs: (b"fake-image", "image/png"),
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_image_for_scene",
        lambda project_id, scene_id, prompt, style: {
            "image_path": f"/tmp/{project_id}-{scene_id}.png"
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_voice_for_scene",
        lambda project_id, scene_id, text, voice_profile="default": {
            "audio_path": f"/tmp/{project_id}-{scene_id}.wav"
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "render_video",
        lambda project_id: {"video_path": f"https://example.test/{project_id}.mp4"},
    )

    with Session(engine) as session:
        user = User(email=f"real-events-{uuid4().hex[:8]}@example.com", hashed_password="hashed", role="admin")
        session.add(user)
        session.commit()
        session.refresh(user)

        result = workflow_service.auto_create_project(
            session=session,
            current_user=user,
            title="Archive Minute",
            duration_minutes=5,
            genre="Real Events",
            short_description="A factual cut about a documented public event.",
        )
        assert result.project.genre == "Real Events"
        assert result.project.workflow_state == "video_completed"
        assert result.project.character_package_approved is True
        assert result.project.selected_character_ids == []


def test_auto_create_project_rejects_factory_only_series_genre_outside_factory_mode() -> None:
    with pytest.raises(ValueError, match="Factory Mode only"):
        workflow_service.auto_create_project(
            session=None,  # type: ignore[arg-type]
            current_user=None,  # type: ignore[arg-type]
            title="Episode One",
            duration_minutes=10,
            genre="Series Video Maker (Factory Mode Only)",
        )


def test_owner_mode_allows_locked_genres_in_auto_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workflow_service, "has_owner_mode_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        workflow_service,
        "generate_script",
        lambda topic, duration_minutes, tone, script_provider=None, model_name=None, genre=None: {
            "full_script": "Scene 1: Owner mode unlocks the gate.",
            "scenes": [
                {"id": 1, "text": "Scene 1: Owner mode unlocks the gate."},
            ],
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_image_bytes",
        lambda **_kwargs: (b"fake-image", "image/png"),
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_image_for_scene",
        lambda project_id, scene_id, prompt, style: {
            "image_path": f"/tmp/{project_id}-{scene_id}.png"
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_voice_for_scene",
        lambda project_id, scene_id, text, voice_profile="default": {
            "audio_path": f"/tmp/{project_id}-{scene_id}.wav"
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "render_video",
        lambda project_id: {"video_path": f"https://example.test/{project_id}.mp4"},
    )

    with Session(engine) as session:
        user = User(email=f"owner-{uuid4().hex[:8]}@example.com", hashed_password="hashed", role="admin")
        session.add(user)
        session.commit()
        session.refresh(user)

        real_events_result = workflow_service.auto_create_project(
            session=session,
            current_user=user,
            title="Archive Minute",
            duration_minutes=5,
            genre="Real Events",
        )
        assert real_events_result.project.genre == "Real Events"
        assert real_events_result.project.workflow_state == "video_completed"

        series_result = workflow_service.auto_create_project(
            session=session,
            current_user=user,
            title="Episode One",
            duration_minutes=5,
            genre="Series Video Maker (Factory Mode Only)",
        )
        assert series_result.project.genre == "Series Video Maker (Factory Mode Only)"
        assert series_result.project.workflow_state == "video_completed"


def test_factory_mode_runs_titles_and_publishes_each_project(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class _FakeSubscription:
        credits_balance = 1000

    class _FakeProject:
        def __init__(self, project_id: str, title: str) -> None:
            self.project_id = project_id
            self.title = title
            self.final_video_url = f"https://example.test/{project_id}.mp4"

    class _FakeAutoCreateResponse:
        def __init__(self, project_id: str, title: str) -> None:
            self.project = _FakeProject(project_id, title)
            self.video_path = self.project.final_video_url

    monkeypatch.setattr(workflow_service, "FACTORY_MODE_ENABLED", True)
    monkeypatch.setattr(
        workflow_service,
        "has_factory_mode_access",
        lambda _subscription, **_kwargs: True,
    )
    monkeypatch.setattr(workflow_service, "get_or_create_subscription", lambda _session, _user: _FakeSubscription())

    def fake_auto_create_project(**kwargs):
        calls.append(
            {
                "kind": "auto_create",
                "title": kwargs["title"],
                "genre": kwargs.get("genre"),
                "allow_factory_mode_genre": kwargs.get("allow_factory_mode_genre"),
            }
        )
        return _FakeAutoCreateResponse(f"factory-{len(calls)}", kwargs["title"])

    def fake_publish_to_all_connections(**kwargs):
        calls.append({"kind": "publish", "project_id": kwargs["project_id"], "message": kwargs["message"]})
        return [type("Job", (), {"job_id": f"pub-{len(calls)}"})()]

    monkeypatch.setattr(workflow_service, "auto_create_project", fake_auto_create_project)
    monkeypatch.setattr(workflow_service, "publish_to_all_connections", fake_publish_to_all_connections)

    with Session(engine) as session:
        user = User(email=f"factory-{uuid4().hex[:8]}@example.com", hashed_password="hashed", role="admin")
        session.add(user)
        session.commit()
        session.refresh(user)

        job = OrchestrationJob(
            tenant_id="default",
            project_id="factory-mode",
            kind="factory_mode",
            payload=json.dumps(
                {
                    "user_id": user.id,
                    "titles": ["First Title", "Second Title"],
                    "duration_minutes": 10,
                    "genre": "Series Video Maker (Factory Mode Only)",
                }
            ),
        )
        result = workflow_service.execute_factory_mode_job(session=session, job=job)

    assert result["processed_titles"] == 2
    assert [item["kind"] for item in calls] == ["auto_create", "publish", "auto_create", "publish"]
    assert [item["title"] for item in calls if item["kind"] == "auto_create"] == ["First Title", "Second Title"]
    assert [
        item["genre"]
        for item in calls
        if item["kind"] == "auto_create"
    ] == ["Series Video Maker (Factory Mode Only)", "Series Video Maker (Factory Mode Only)"]
    assert [
        item["allow_factory_mode_genre"]
        for item in calls
        if item["kind"] == "auto_create"
    ] == [True, True]
    assert [item["project_id"] for item in calls if item["kind"] == "publish"] == ["factory-1", "factory-3"]


def test_workflow_feedback_submission_persists_and_emails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = workflow_client()
    calls: list[dict[str, object]] = []

    def capture_feedback_email(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(workflow_router, "send_feedback_email", capture_feedback_email)

    response = client.post(
        "/workflow/feedback",
        json={
            "subject": "Feature suggestion",
            "message": "Please add a faster publish preview and more timeline controls.",
            "page": "publish",
            "project_id": "project-1",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["subject"] == "Feature suggestion"
    assert payload["page"] == "publish"
    assert payload["project_id"] == "project-1"
    assert payload["email_sent"] is True

    assert calls
    assert calls[0]["subject"] == "Feature suggestion"
    assert calls[0]["page"] == "publish"
    assert calls[0]["project_id"] == "project-1"

    with Session(engine) as session:
        feedback = session.exec(
            select(UserFeedback).where(UserFeedback.feedback_id == payload["feedback_id"])
        ).first()
        assert feedback is not None
        assert feedback.subject == "Feature suggestion"
        assert feedback.message.startswith("Please add a faster publish preview")
        assert feedback.email_sent is True


def test_character_library_limit_blocks_create_generate_and_upload() -> None:
    client = workflow_client()
    tenant_headers = {"X-Tenant-ID": f"character-limit-{uuid4().hex[:8]}"}

    verify_res = client.post(
        "/billing/admin/access/verify",
        json={"password": "ChangeMe123!"},
        headers=tenant_headers,
    )
    assert verify_res.status_code == 200
    admin_headers = {
        **tenant_headers,
        "X-Admin-Access-Token": verify_res.json()["access_token"],
    }

    update_pricing_res = client.patch(
        "/billing/admin/pricing",
        json={
            "moderate_credits": 500,
            "moderate_price_usd": 15,
            "moderate_base_character_slots": 5,
            "moderate_stripe_price_id": "",
            "pro_credits": 2000,
            "pro_price_usd": 49,
            "pro_base_character_slots": 10,
            "pro_stripe_price_id": "",
            "studio_credits": 6000,
            "studio_price_usd": 119,
            "studio_base_character_slots": 15,
            "studio_stripe_price_id": "",
            "factory_one_time_price_usd": 149,
            "factory_one_time_stripe_price_id": "",
            "factory_subscription_price_usd": 39,
            "factory_subscription_stripe_price_id": "",
            "owner_mode_enabled": False,
            "receipts_live_mode": False,
            "free_base_character_slots": 1,
            "character_slot_addon_size": 5,
            "character_slot_addon_cost_credits": 50,
        },
        headers=admin_headers,
    )
    assert update_pricing_res.status_code == 200

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Character Limit Test",
            "idea_prompt": "A compact cast production.",
            "genre": "Drama",
            "target_duration_minutes": 2,
        },
        headers=tenant_headers,
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["project_id"]

    client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Character Limit Test",
            "idea_prompt": "A compact cast production.",
            "genre": "Drama",
            "target_duration_minutes": 2,
            "tone": "cinematic",
        },
        headers=tenant_headers,
    )
    client.post(f"/workflow/projects/{project_id}/approve-script", headers=tenant_headers)

    first_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Only Slot",
            "role_type": "main",
            "description": "The only saved character allowed right now.",
            "select_after_create": True,
        },
        headers=tenant_headers,
    )
    assert first_character_res.status_code == 200

    blocked_manual = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Second Slot",
            "role_type": "supporting",
            "description": "Should be blocked by quota.",
            "select_after_create": True,
        },
        headers=tenant_headers,
    )
    assert blocked_manual.status_code == 402
    assert "Character library is full" in blocked_manual.json()["detail"]

    blocked_generate = client.post(
        f"/workflow/projects/{project_id}/characters/generate",
        json={
            "name": "Generated Slot",
            "role_type": "supporting",
            "description": "Should be blocked before generation starts.",
            "select_after_create": True,
        },
        headers=tenant_headers,
    )
    assert blocked_generate.status_code == 402
    assert "Character library is full" in blocked_generate.json()["detail"]

    blocked_upload = client.post(
        f"/workflow/projects/{project_id}/characters/upload",
        data={
            "name": "Uploaded Slot",
            "role_type": "supporting",
            "description": "Should be blocked before upload is saved.",
            "select_after_create": "true",
        },
        files={"reference": ("blocked.png", b"fake-image", "image/png")},
        headers=tenant_headers,
    )
    assert blocked_upload.status_code == 402
    assert "Character library is full" in blocked_upload.json()["detail"]

    restore_pricing_res = client.patch(
        "/billing/admin/pricing",
        json={
            "moderate_credits": 500,
            "moderate_price_usd": 15,
            "moderate_base_character_slots": 5,
            "moderate_stripe_price_id": "",
            "pro_credits": 2000,
            "pro_price_usd": 49,
            "pro_base_character_slots": 10,
            "pro_stripe_price_id": "",
            "studio_credits": 6000,
            "studio_price_usd": 119,
            "studio_base_character_slots": 15,
            "studio_stripe_price_id": "",
            "factory_one_time_price_usd": 149,
            "factory_one_time_stripe_price_id": "",
            "factory_subscription_price_usd": 39,
            "factory_subscription_stripe_price_id": "",
            "owner_mode_enabled": False,
            "receipts_live_mode": False,
            "free_base_character_slots": 100,
            "character_slot_addon_size": 5,
            "character_slot_addon_cost_credits": 50,
        },
        headers=admin_headers,
    )
    assert restore_pricing_res.status_code == 200


def test_workflow_production_queues_then_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    client = workflow_client()

    monkeypatch.setattr(
        workflow_service,
        "generate_image_for_scene",
        lambda project_id, scene_id, prompt, style: {"image_path": f"/tmp/{project_id}-{scene_id}.png"},
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_voice_for_scene",
        lambda project_id, scene_id, text, voice_profile="default": {
            "audio_path": f"/tmp/{project_id}-{scene_id}.wav"
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "render_video",
        lambda project_id: {"video_path": f"https://example.test/{project_id}.mp4"},
    )

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Queued Production Test",
            "idea_prompt": "A hero learns patience.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
        },
    )
    project_id = create_res.json()["project_id"]

    client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Queued Production Test",
            "idea_prompt": "A hero learns patience.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
            "tone": "cinematic",
        },
    )
    client.post(f"/workflow/projects/{project_id}/approve-script")
    create_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Hero",
            "role_type": "main",
            "description": "Determined and kind",
            "select_after_create": True,
        },
    )
    selected_ids = create_character_res.json()["selected_character_ids"]
    client.post(
        f"/workflow/projects/{project_id}/approve-characters",
        json={"selected_character_ids": selected_ids},
    )

    start_res = client.post(f"/workflow/projects/{project_id}/start-production")
    assert start_res.status_code == 200
    start_payload = start_res.json()
    assert start_payload["project"]["workflow_state"] == "production_queued"
    assert start_payload["video_path"] is None
    assert start_payload["status"]["queue_status"] == "queued"
    assert start_payload["status"]["can_retry"] is False
    assert start_payload["status"]["production_job_id"]

    process_res = client.post("/orchestration/queue/process?limit=1")
    assert process_res.status_code == 200
    assert process_res.json()["processed"] == 1

    status_res = client.get(f"/workflow/projects/{project_id}/production-status")
    assert status_res.status_code == 200
    status_payload = status_res.json()
    assert status_payload["workflow_state"] == "video_completed"
    assert status_payload["queue_status"] == "complete"
    assert status_payload["final_video_url"] == f"https://example.test/{project_id}.mp4"
    assert status_payload["can_retry"] is False

    bundle_artifact = json.loads(
        storage_client.read_text(project_key(project_id, "workflow/approved_production_bundle.json"))
    )
    dna_artifact = json.loads(
        storage_client.read_text(project_key(project_id, "workflow/character_dna_snapshot.json"))
    )
    voice_profile_artifact = json.loads(
        storage_client.read_text(project_key(project_id, "voice_profiles/characters.json"))
    )

    assert bundle_artifact["project_id"] == project_id
    assert selected_ids[0] in bundle_artifact["identity_rules"]
    assert selected_ids[0] in bundle_artifact["reference_bundles"]
    assert selected_ids[0] in bundle_artifact["voice_profiles"]
    assert selected_ids[0] in dna_artifact["identity_rules"]
    assert selected_ids[0] in dna_artifact["reference_bundles"]
    assert selected_ids[0] in dna_artifact["prompts"]
    assert voice_profile_artifact[0]["character_id"] == selected_ids[0]


def test_workflow_production_injects_character_identity_into_scene_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = workflow_client()
    captured: dict[str, object] = {}

    def capture_image(project_id: str, scene_id: int, prompt: str, style: str) -> dict[str, str]:
        captured["image_prompt"] = prompt
        captured["image_scene_id"] = scene_id
        return {"image_path": f"/tmp/{project_id}-{scene_id}.png"}

    def capture_voice(
        project_id: str,
        scene_id: int,
        text: str,
        voice_profile: str = "default",
    ) -> dict[str, str]:
        captured["voice_text"] = text
        captured["voice_profile"] = voice_profile
        captured["voice_scene_id"] = scene_id
        return {"audio_path": f"/tmp/{project_id}-{scene_id}.wav"}

    monkeypatch.setattr(workflow_service, "generate_image_for_scene", capture_image)
    monkeypatch.setattr(workflow_service, "generate_voice_for_scene", capture_voice)
    monkeypatch.setattr(
        workflow_service,
        "render_video",
        lambda project_id: {"video_path": f"https://example.test/{project_id}-identity.mp4"},
    )

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Identity Injection Test",
            "idea_prompt": "Hero restores a broken machine.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
        },
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["project_id"]

    client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Identity Injection Test",
            "idea_prompt": "Hero restores a broken machine.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
            "tone": "cinematic",
        },
    )
    update_res = client.patch(
        f"/workflow/projects/{project_id}/script",
        json={"script": "Hero: We restore the machine before sunrise.", "update_scenes": True},
    )
    assert update_res.status_code == 200
    client.post(f"/workflow/projects/{project_id}/approve-script")
    create_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Hero",
            "role_type": "main",
            "description": "Determined inventor with a bright red jacket",
            "voice_profile": "heroic",
            "reference_image_urls": [
                "https://example.test/hero-ref-1.png",
                "https://example.test/hero-ref-2.png",
            ],
            "select_after_create": True,
        },
    )
    assert create_character_res.status_code == 200
    selected_ids = create_character_res.json()["selected_character_ids"]
    client.post(
        f"/workflow/projects/{project_id}/approve-characters",
        json={"selected_character_ids": selected_ids},
    )

    start_res = client.post(f"/workflow/projects/{project_id}/start-production")
    assert start_res.status_code == 200
    process_res = client.post("/orchestration/queue/process?limit=1")
    assert process_res.status_code == 200
    assert process_res.json()["processed"] == 1

    assert captured["voice_profile"] == "heroic"
    assert captured["voice_text"] == "Hero: We restore the machine before sunrise."
    assert "Approved cast: Hero:" in str(captured["image_prompt"])
    assert "Identity locks: Hero seed" in str(captured["image_prompt"])
    assert "lock identity" in str(captured["image_prompt"])
    assert "hero-ref-1.png" in str(captured["image_prompt"])

    scene_plan = json.loads(
        storage_client.read_text(project_key(project_id, "workflow/scene_identity_plan.json"))
    )
    assert scene_plan[0]["scene_id"] == 1
    assert scene_plan[0]["matched_character_ids"] == selected_ids
    assert scene_plan[0]["voice_profile"] == "heroic"
    assert scene_plan[0]["identity_snapshots"][0]["character_id"] == selected_ids[0]
    assert scene_plan[0]["identity_snapshots"][0]["voice_profile"] == "heroic"


def test_workflow_production_preserves_identity_snapshot_across_scenes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = workflow_client()
    captured_images: list[dict[str, object]] = []
    captured_voices: list[dict[str, object]] = []

    def capture_image(project_id: str, scene_id: int, prompt: str, style: str) -> dict[str, str]:
        captured_images.append({"scene_id": scene_id, "prompt": prompt})
        return {"image_path": f"/tmp/{project_id}-{scene_id}.png"}

    def capture_voice(
        project_id: str,
        scene_id: int,
        text: str,
        voice_profile: str = "default",
    ) -> dict[str, str]:
        captured_voices.append(
            {
                "scene_id": scene_id,
                "text": text,
                "voice_profile": voice_profile,
            }
        )
        return {"audio_path": f"/tmp/{project_id}-{scene_id}.wav"}

    monkeypatch.setattr(workflow_service, "generate_image_for_scene", capture_image)
    monkeypatch.setattr(workflow_service, "generate_voice_for_scene", capture_voice)
    monkeypatch.setattr(
        workflow_service,
        "render_video",
        lambda project_id: {"video_path": f"https://example.test/{project_id}-multi-scene.mp4"},
    )

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Identity Continuity Test",
            "idea_prompt": "Hero appears in two connected scenes.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
        },
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["project_id"]

    client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Identity Continuity Test",
            "idea_prompt": "Hero appears in two connected scenes.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
            "tone": "cinematic",
        },
    )
    update_res = client.patch(
        f"/workflow/projects/{project_id}/script",
        json={
            "script": "\n".join(
                [
                    "Hero: We begin the repair before dawn.",
                    "Hero: Now we finish the same repair at sunrise.",
                ]
            ),
            "update_scenes": True,
        },
    )
    assert update_res.status_code == 200
    client.post(f"/workflow/projects/{project_id}/approve-script")
    create_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Hero",
            "role_type": "main",
            "description": "Determined inventor with a bright red jacket",
            "voice_profile": "heroic",
            "reference_image_urls": [
                "https://example.test/hero-ref-1.png",
                "https://example.test/hero-ref-2.png",
            ],
            "select_after_create": True,
        },
    )
    assert create_character_res.status_code == 200
    selected_ids = create_character_res.json()["selected_character_ids"]
    client.post(
        f"/workflow/projects/{project_id}/approve-characters",
        json={"selected_character_ids": selected_ids},
    )

    start_res = client.post(f"/workflow/projects/{project_id}/start-production")
    assert start_res.status_code == 200
    process_res = client.post("/orchestration/queue/process?limit=1")
    assert process_res.status_code == 200
    assert process_res.json()["processed"] == 1

    assert [entry["scene_id"] for entry in captured_images] == [1, 2]
    assert [entry["scene_id"] for entry in captured_voices] == [1, 2]
    assert all(entry["voice_profile"] == "heroic" for entry in captured_voices)
    assert all("Identity locks: Hero seed" in str(entry["prompt"]) for entry in captured_images)
    assert all("Hero hash" in str(entry["prompt"]) for entry in captured_images)
    assert all("hero-ref-1.png" in str(entry["prompt"]) for entry in captured_images)

    scene_plan = json.loads(
        storage_client.read_text(project_key(project_id, "workflow/scene_identity_plan.json"))
    )
    assert [entry["scene_id"] for entry in scene_plan] == [1, 2]
    assert scene_plan[0]["matched_character_ids"] == selected_ids
    assert scene_plan[1]["matched_character_ids"] == selected_ids
    assert scene_plan[0]["voice_profile"] == "heroic"
    assert scene_plan[1]["voice_profile"] == "heroic"

    first_identity = scene_plan[0]["identity_snapshots"][0]
    second_identity = scene_plan[1]["identity_snapshots"][0]
    assert first_identity["character_id"] == selected_ids[0]
    assert second_identity["character_id"] == selected_ids[0]
    assert first_identity["identity_hash"] == second_identity["identity_hash"]
    assert first_identity["consistency_seed"] == second_identity["consistency_seed"]
    assert first_identity["voice_profile"] == second_identity["voice_profile"] == "heroic"
    assert first_identity["lock_identity"] is True
    assert second_identity["lock_identity"] is True


def test_workflow_production_retry_requeues_failed_job(monkeypatch: pytest.MonkeyPatch) -> None:
    client = workflow_client()

    monkeypatch.setattr(
        workflow_service,
        "generate_image_for_scene",
        lambda project_id, scene_id, prompt, style: {"image_path": f"/tmp/{project_id}-{scene_id}.png"},
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_voice_for_scene",
        lambda project_id, scene_id, text, voice_profile="default": {
            "audio_path": f"/tmp/{project_id}-{scene_id}.wav"
        },
    )

    render_state = {"attempt": 0}

    def flaky_render(project_id: str) -> dict[str, str]:
        render_state["attempt"] += 1
        if render_state["attempt"] == 1:
            raise RuntimeError("render failed once")
        return {"video_path": f"https://example.test/{project_id}-retry.mp4"}

    monkeypatch.setattr(workflow_service, "render_video", flaky_render)

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Retry Production Test",
            "idea_prompt": "A robot rebuilds a garden.",
            "genre": "Family",
            "target_duration_minutes": 2,
        },
    )
    project_id = create_res.json()["project_id"]

    client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Retry Production Test",
            "idea_prompt": "A robot rebuilds a garden.",
            "genre": "Family",
            "target_duration_minutes": 2,
            "tone": "gentle",
        },
    )
    client.post(f"/workflow/projects/{project_id}/approve-script")
    create_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Garden Robot",
            "role_type": "main",
            "description": "Helpful and optimistic",
            "select_after_create": True,
        },
    )
    selected_ids = create_character_res.json()["selected_character_ids"]
    client.post(
        f"/workflow/projects/{project_id}/approve-characters",
        json={"selected_character_ids": selected_ids},
    )

    start_res = client.post(f"/workflow/projects/{project_id}/start-production")
    assert start_res.status_code == 200

    process_res = client.post("/orchestration/queue/process?limit=1")
    assert process_res.status_code == 200
    assert process_res.json()["failed"]

    failed_status_res = client.get(f"/workflow/projects/{project_id}/production-status")
    assert failed_status_res.status_code == 200
    failed_status = failed_status_res.json()
    assert failed_status["workflow_state"] == "production_failed"
    assert failed_status["queue_status"] == "failed"
    assert "render failed once" in failed_status["last_error"]
    assert failed_status["can_retry"] is True

    retry_res = client.post(f"/workflow/projects/{project_id}/retry-production")
    assert retry_res.status_code == 200
    retry_status = retry_res.json()
    assert retry_status["workflow_state"] == "production_queued"
    assert retry_status["queue_status"] == "queued"
    assert retry_status["queue_attempts"] == 0
    assert retry_status["last_error"] is None
    assert retry_status["can_retry"] is False

    process_retry_res = client.post("/orchestration/queue/process?limit=1")
    assert process_retry_res.status_code == 200

    completed_status_res = client.get(f"/workflow/projects/{project_id}/production-status")
    assert completed_status_res.status_code == 200
    completed_status = completed_status_res.json()
    assert completed_status["workflow_state"] == "video_completed"
    assert completed_status["queue_status"] == "complete"
    assert completed_status["final_video_url"] == f"https://example.test/{project_id}-retry.mp4"
    assert completed_status["can_retry"] is False


def test_workflow_production_grok_mode_skips_scene_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    client = workflow_client()

    monkeypatch.setattr(workflow_service, "XAI_API_KEY", "xai-test")
    monkeypatch.setattr(workflow_service, "resolve_video_provider", lambda: "grok_imagine")
    monkeypatch.setattr(
        workflow_service,
        "render_video",
        lambda project_id: {
            "video_path": f"https://example.test/{project_id}-grok.mp4"
        },
    )

    def _unexpected(*_args, **_kwargs):
        raise AssertionError("legacy image/voice generation should be skipped in Grok mode")

    monkeypatch.setattr(workflow_service, "generate_image_for_scene", _unexpected)
    monkeypatch.setattr(workflow_service, "generate_voice_for_scene", _unexpected)

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Grok Mode Test",
            "idea_prompt": "A hero speaks while the scene continues seamlessly.",
            "genre": "Sci-Fi",
            "target_duration_minutes": 2,
        },
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["project_id"]

    client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Grok Mode Test",
            "idea_prompt": "A hero speaks while the scene continues seamlessly.",
            "genre": "Sci-Fi",
            "target_duration_minutes": 2,
            "tone": "cinematic",
        },
    )
    client.post(f"/workflow/projects/{project_id}/approve-script")
    create_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Hero",
            "role_type": "main",
            "description": "Brave lead character",
            "select_after_create": True,
        },
    )
    selected_ids = create_character_res.json()["selected_character_ids"]
    client.post(
        f"/workflow/projects/{project_id}/approve-characters",
        json={"selected_character_ids": selected_ids},
    )

    start_res = client.post(f"/workflow/projects/{project_id}/start-production")
    assert start_res.status_code == 200

    process_res = client.post("/orchestration/queue/process?limit=1")
    assert process_res.status_code == 200
    assert process_res.json()["failed"] == []

    status_res = client.get(f"/workflow/projects/{project_id}/production-status")
    assert status_res.status_code == 200
    status = status_res.json()
    assert status["workflow_state"] == "video_completed"
    assert status["final_video_url"] == f"https://example.test/{project_id}-grok.mp4"


def test_workflow_character_creation_preserves_canonical_image_and_identity_lock() -> None:
    client = workflow_client()

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Character DNA Surface Test",
            "idea_prompt": "A lead character needs an approved visual identity.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
        },
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["project_id"]

    client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Character DNA Surface Test",
            "idea_prompt": "A lead character needs an approved visual identity.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
            "tone": "cinematic",
        },
    )
    approve_script_res = client.post(f"/workflow/projects/{project_id}/approve-script")
    assert approve_script_res.status_code == 200

    create_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Guide",
            "role_type": "main",
            "description": "Steady mentor in a silver coat",
            "voice_profile": "mentor",
            "reference_image_urls": [
                "https://example.test/guide-ref-1.png",
                "https://example.test/guide-ref-2.png",
            ],
            "canonical_image_url": "https://example.test/guide-canonical.png",
            "lock_identity": False,
            "select_after_create": True,
        },
    )
    assert create_character_res.status_code == 200

    created_character = create_character_res.json()["selected"][0]
    assert created_character["name"] == "Guide"
    assert created_character["canonical_image_url"] == "https://example.test/guide-canonical.png"
    assert created_character["lock_identity"] is False
    assert "https://example.test/guide-canonical.png" in created_character["reference_image_urls"]
    assert created_character["voice_profile"] == "mentor"


def test_workflow_transition_validator_rejects_invalid_jumps() -> None:
    with pytest.raises(ValueError, match="draft -> production_running"):
        validate_workflow_transition("draft", "production_running")

    project = Project(
        project_id="project-transition-test",
        title="Transition Test",
        topic="Transition Test",
        workflow_state="script_generated",
    )

    transition_project_state(project, "script_approved")
    assert project.workflow_state == "script_approved"

    with pytest.raises(ValueError, match="script_approved -> production_running"):
        transition_project_state(project, "production_running")


def test_workflow_transition_supports_ready_handoff() -> None:
    project = Project(
        project_id="project-ready-test",
        title="Ready Test",
        topic="Ready Test",
        workflow_state="characters_approved",
    )

    transition_project_state(project, "production_ready")
    assert project.workflow_state == "production_ready"


def test_workflow_transition_matrix_matches_declared_rules() -> None:
    states = set(WORKFLOW_TRANSITIONS.keys())
    for next_states in WORKFLOW_TRANSITIONS.values():
        states.update(next_states)

    for current_state in states:
        allowed = WORKFLOW_TRANSITIONS.get(current_state, set())
        for next_state in states:
            if current_state == next_state:
                validate_workflow_transition(current_state, next_state)
                continue
            if next_state in allowed:
                validate_workflow_transition(current_state, next_state)
            else:
                with pytest.raises(
                    ValueError,
                    match=f"{current_state} -> {next_state}",
                ):
                    validate_workflow_transition(current_state, next_state)


def test_regenerating_script_clears_downstream_approvals() -> None:
    client = workflow_client()

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Reset Approval Test",
            "idea_prompt": "A lighthouse guide helps travelers.",
            "genre": "Drama",
            "target_duration_minutes": 3,
        },
    )
    project_id = create_res.json()["project_id"]

    client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Reset Approval Test",
            "idea_prompt": "A lighthouse guide helps travelers.",
            "genre": "Drama",
            "target_duration_minutes": 3,
            "tone": "warm",
        },
    )
    client.post(f"/workflow/projects/{project_id}/approve-script")
    create_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Guide",
            "role_type": "main",
            "description": "Steady and compassionate",
            "select_after_create": True,
        },
    )
    selected_ids = create_character_res.json()["selected_character_ids"]
    client.post(
        f"/workflow/projects/{project_id}/approve-characters",
        json={"selected_character_ids": selected_ids},
    )

    regen_res = client.post(
        f"/workflow/projects/{project_id}/regenerate-script",
        json={
            "title": "Reset Approval Test",
            "idea_prompt": "A lighthouse guide helps travelers through a storm.",
            "genre": "Drama",
            "target_duration_minutes": 3,
            "tone": "warm",
        },
    )
    assert regen_res.status_code == 200
    regen_project = regen_res.json()
    assert regen_project["workflow_state"] == "script_generated"
    assert regen_project["script_approved"] is None
    assert regen_project["character_package_approved"] is False
    assert regen_project["production_job_id"] is None
    assert regen_project["final_video_url"] is None

    blocked_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Too Soon Again",
            "role_type": "supporting",
            "description": "Still blocked until re-approval",
            "select_after_create": True,
        },
    )
    assert blocked_character_res.status_code == 400
    assert "Script approval required" in blocked_character_res.json()["detail"]


def test_editing_script_clears_character_approval_and_returns_to_review_stage() -> None:
    client = workflow_client()

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Edit Script Reset Test",
            "idea_prompt": "A baker learns patience.",
            "genre": "Family",
            "target_duration_minutes": 2,
        },
    )
    project_id = create_res.json()["project_id"]

    script_res = client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Edit Script Reset Test",
            "idea_prompt": "A baker learns patience.",
            "genre": "Family",
            "target_duration_minutes": 2,
            "tone": "gentle",
        },
    )
    client.post(f"/workflow/projects/{project_id}/approve-script")
    create_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Baker",
            "role_type": "main",
            "description": "Focused and kind",
            "select_after_create": True,
        },
    )
    selected_ids = create_character_res.json()["selected_character_ids"]
    client.post(
        f"/workflow/projects/{project_id}/approve-characters",
        json={"selected_character_ids": selected_ids},
    )

    update_res = client.patch(
        f"/workflow/projects/{project_id}/script",
        json={
            "script": f'{script_res.json()["script_draft"]}\nScene 99: A new ending.',
            "update_scenes": True,
        },
    )
    assert update_res.status_code == 200
    updated_project = update_res.json()
    assert updated_project["workflow_state"] == "script_generated"
    assert updated_project["script_approved"] is None
    assert updated_project["character_package_approved"] is False

    summary_res = client.get(f"/workflow/projects/{project_id}/production-summary")
    assert summary_res.status_code == 200
    assert summary_res.json()["script_ready"] is False
    assert summary_res.json()["characters_ready"] is False


def test_changing_character_selection_clears_character_approval() -> None:
    client = workflow_client()

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Character Reset Test",
            "idea_prompt": "A team repairs a bridge.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
        },
    )
    project_id = create_res.json()["project_id"]

    client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Character Reset Test",
            "idea_prompt": "A team repairs a bridge.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
            "tone": "cinematic",
        },
    )
    client.post(f"/workflow/projects/{project_id}/approve-script")
    char_one = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Builder",
            "role_type": "main",
            "description": "Confident and practical",
            "select_after_create": True,
        },
    ).json()["selected_character_ids"][0]
    char_two_create = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Engineer",
            "role_type": "supporting",
            "description": "Precise and inventive",
            "select_after_create": False,
        },
    )
    assert char_two_create.status_code == 200
    char_two = next(
        character["character_id"]
        for character in char_two_create.json()["library"]
        if character["name"] == "Engineer"
    )
    client.post(
        f"/workflow/projects/{project_id}/approve-characters",
        json={"selected_character_ids": [char_one]},
    )

    select_res = client.post(
        f"/workflow/projects/{project_id}/characters/select",
        json={"selected_character_ids": [char_one, char_two]},
    )
    assert select_res.status_code == 200

    project_res = client.get(f"/workflow/projects/{project_id}")
    assert project_res.status_code == 200
    project_payload = project_res.json()
    assert project_payload["workflow_state"] == "characters_in_progress"
    assert project_payload["character_package_approved"] is False
    assert project_payload["selected_character_ids"] == [char_one, char_two]


def test_approved_character_snapshot_survives_later_character_edits() -> None:
    client = workflow_client()

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Snapshot Integrity Test",
            "idea_prompt": "A pilot teaches a student to fly.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
        },
    )
    project_id = create_res.json()["project_id"]

    client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Snapshot Integrity Test",
            "idea_prompt": "A pilot teaches a student to fly.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
            "tone": "cinematic",
        },
    )
    client.post(f"/workflow/projects/{project_id}/approve-script")
    create_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Pilot",
            "role_type": "main",
            "description": "Calm and experienced",
            "select_after_create": True,
        },
    )
    selected_ids = create_character_res.json()["selected_character_ids"]
    client.post(
        f"/workflow/projects/{project_id}/approve-characters",
        json={"selected_character_ids": selected_ids},
    )

    tenant_token = set_current_tenant_id(client.headers["X-Tenant-ID"])
    try:
        with Session(engine) as session:
            package = latest_character_package(session, project_id)
            assert package is not None
            original_bundle = resolve_approved_production_package(session, project_id)
            profile = session.exec(
                select(CharacterProfile).where(CharacterProfile.character_id == selected_ids[0])
            ).first()
            assert profile is not None
            profile.name = "Changed Pilot"
            profile.description = "A different description"
            session.add(profile)
            session.commit()

            preserved_bundle = resolve_approved_production_package(session, project_id)
            snapshot = preserved_bundle["characters"][0]
            assert snapshot["character_id"] == selected_ids[0]
            assert snapshot["name"] == original_bundle["characters"][0]["name"]
            assert snapshot["description"] == original_bundle["characters"][0]["description"]
            assert snapshot["name"] != "Changed Pilot"

            stored_package = session.exec(
                select(ProjectCharacterPackage).where(ProjectCharacterPackage.project_id == project_id)
            ).first()
            assert stored_package is not None
            assert stored_package.package_snapshot_json == package.package_snapshot_json
            assert selected_ids[0] in preserved_bundle["identity_rules"]
            assert selected_ids[0] in preserved_bundle["reference_bundles"]
            assert selected_ids[0] in preserved_bundle["voice_profiles"]
            assert preserved_bundle["voice_profiles"][selected_ids[0]]["voice_profile"] == "default"
    finally:
        reset_current_tenant_id(tenant_token)


def test_resolve_approved_production_package_returns_full_identity_bundle() -> None:
    client = workflow_client()

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Resolver Payload Test",
            "idea_prompt": "A captain trains a new crew.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
        },
    )
    project_id = create_res.json()["project_id"]

    client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Resolver Payload Test",
            "idea_prompt": "A captain trains a new crew.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
            "tone": "cinematic",
        },
    )
    client.post(f"/workflow/projects/{project_id}/approve-script")
    create_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Captain",
            "role_type": "main",
            "description": "Experienced, steady, and strategic",
            "voice_profile": "narrator",
            "reference_image_url": "https://example.test/captain-ref.png",
            "reference_image_urls": [
                "https://example.test/captain-ref.png",
                "https://example.test/captain-ref-2.png",
            ],
            "select_after_create": True,
        },
    )
    assert create_character_res.status_code == 200
    selected_ids = create_character_res.json()["selected_character_ids"]
    captain = next(
        character
        for character in create_character_res.json()["selected"]
        if character["character_id"] == selected_ids[0]
    )
    assert captain["reference_image_urls"] == [
        "https://example.test/captain-ref.png",
        "https://example.test/captain-ref-2.png",
    ]
    client.post(
        f"/workflow/projects/{project_id}/approve-characters",
        json={"selected_character_ids": selected_ids},
    )

    tenant_token = set_current_tenant_id(client.headers["X-Tenant-ID"])
    try:
        with Session(engine) as session:
            bundle = resolve_approved_production_package(session, project_id)
    finally:
        reset_current_tenant_id(tenant_token)

    assert bundle["project_id"] == project_id
    assert bundle["approved_script_snapshot"] == bundle["script"]
    assert bundle["approved_character_package_snapshot"] == bundle["characters"]
    assert bundle["script"]
    assert bundle["characters"]
    assert bundle["references"][selected_ids[0]] == "https://example.test/captain-ref.png"
    assert bundle["seeds"][selected_ids[0]]
    assert bundle["prompts"][selected_ids[0]]["visual_prompt_base"]
    assert bundle["prompts"][selected_ids[0]]["negative_prompt_base"]
    assert bundle["identity_rules"][selected_ids[0]]["lock_identity"] is True
    assert bundle["reference_bundles"][selected_ids[0]] == [
        "https://example.test/captain-ref.png",
        "https://example.test/captain-ref-2.png",
    ]
    assert bundle["voice_profiles"][selected_ids[0]]["voice_profile"] == "narrator"


def test_archive_project_hides_it_from_active_project_list() -> None:
    client = workflow_client()

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Archive Me",
            "idea_prompt": "A quiet ending for an old project.",
            "genre": "Drama",
            "target_duration_minutes": 2,
        },
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["project_id"]

    archive_res = client.post(f"/workflow/projects/{project_id}/archive")
    assert archive_res.status_code == 200
    archived_payload = archive_res.json()
    assert archived_payload["project_id"] == project_id
    assert archived_payload["archived_at"] is not None

    list_res = client.get("/workflow/projects")
    assert list_res.status_code == 200
    assert all(project["project_id"] != project_id for project in list_res.json())

    get_res = client.get(f"/workflow/projects/{project_id}")
    assert get_res.status_code == 200
    assert get_res.json()["archived_at"] is not None


def test_delete_all_workflow_projects_clears_records_and_files() -> None:
    client = workflow_client()

    create_res_one = client.post(
        "/workflow/projects",
        json={
            "title": "Delete One",
            "idea_prompt": "First test project.",
            "genre": "Drama",
            "target_duration_minutes": 2,
        },
    )
    create_res_two = client.post(
        "/workflow/projects",
        json={
            "title": "Delete Two",
            "idea_prompt": "Second test project.",
            "genre": "Drama",
            "target_duration_minutes": 2,
        },
    )
    assert create_res_one.status_code == 200
    assert create_res_two.status_code == 200
    project_id_one = create_res_one.json()["project_id"]
    project_id_two = create_res_two.json()["project_id"]

    assert (PROJECTS_DIR / project_id_one).exists()
    assert (PROJECTS_DIR / project_id_two).exists()

    delete_res = client.delete("/workflow/projects")
    assert delete_res.status_code == 200
    payload = delete_res.json()
    assert payload["deleted_count"] == 2
    assert set(payload["deleted_ids"]) == {project_id_one, project_id_two}

    list_res = client.get("/workflow/projects")
    assert list_res.status_code == 200
    assert list_res.json() == []
    assert not (PROJECTS_DIR / project_id_one).exists()
    assert not (PROJECTS_DIR / project_id_two).exists()


def test_api_project_alias_supports_guided_workflow_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = workflow_client()

    monkeypatch.setattr(
        workflow_service,
        "generate_image_for_scene",
        lambda project_id, scene_id, prompt, style: {"image_path": f"/tmp/{project_id}-{scene_id}.png"},
    )
    monkeypatch.setattr(
        workflow_service,
        "generate_voice_for_scene",
        lambda project_id, scene_id, text, voice_profile="default": {
            "audio_path": f"/tmp/{project_id}-{scene_id}.wav"
        },
    )
    monkeypatch.setattr(
        workflow_service,
        "render_video",
        lambda project_id: {"video_path": f"https://example.test/{project_id}-alias.mp4"},
    )

    create_res = client.post(
        "/api/projects",
        json={
            "title": "API Alias Test",
            "idea_prompt": "A crew solves a puzzle together.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
        },
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["project_id"]

    generate_res = client.post(
        f"/api/projects/{project_id}/generate-script",
        json={
            "title": "API Alias Test",
            "idea_prompt": "A crew solves a puzzle together.",
            "genre": "Adventure",
            "target_duration_minutes": 2,
            "tone": "cinematic",
        },
    )
    assert generate_res.status_code == 200
    assert generate_res.json()["workflow_state"] == "script_generated"

    approve_res = client.post(f"/api/projects/{project_id}/approve-script")
    assert approve_res.status_code == 200
    assert approve_res.json()["workflow_state"] == "script_approved"

    create_character_res = client.post(
        f"/api/projects/{project_id}/characters/create",
        json={
            "name": "Captain Nova",
            "role_type": "main",
            "description": "Calm and observant",
            "select_after_create": True,
        },
    )
    assert create_character_res.status_code == 200
    selected_ids = create_character_res.json()["selected_character_ids"]

    approve_characters_res = client.post(
        f"/api/projects/{project_id}/approve-characters",
        json={"selected_character_ids": selected_ids},
    )
    assert approve_characters_res.status_code == 200
    assert approve_characters_res.json()["approved_character_ids"] == selected_ids

    summary_res = client.get(f"/api/projects/{project_id}/production-summary")
    assert summary_res.status_code == 200
    assert summary_res.json()["workflow_state"] == "production_ready"

    start_res = client.post(f"/api/projects/{project_id}/start-production")
    assert start_res.status_code == 200
    assert start_res.json()["project"]["workflow_state"] == "production_queued"

    process_res = client.post("/orchestration/queue/process?limit=1")
    assert process_res.status_code == 200
    assert process_res.json()["processed"] == 1

    status_res = client.get(f"/api/projects/{project_id}/production-status")
    assert status_res.status_code == 200
    assert status_res.json()["workflow_state"] == "video_completed"
    assert status_res.json()["final_video_url"] == f"https://example.test/{project_id}-alias.mp4"


def test_duplicate_project_copies_guided_state_without_live_output_fields() -> None:
    client = workflow_client()

    create_res = client.post(
        "/workflow/projects",
        json={
            "title": "Duplicate Source",
            "idea_prompt": "A crew prepares for a second mission.",
            "genre": "Adventure",
            "target_duration_minutes": 3,
        },
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["project_id"]

    client.post(
        f"/workflow/projects/{project_id}/generate-script",
        json={
            "title": "Duplicate Source",
            "idea_prompt": "A crew prepares for a second mission.",
            "genre": "Adventure",
            "target_duration_minutes": 3,
            "tone": "cinematic",
        },
    )
    client.post(f"/workflow/projects/{project_id}/approve-script")
    create_character_res = client.post(
        f"/workflow/projects/{project_id}/characters/create",
        json={
            "name": "Captain Echo",
            "role_type": "main",
            "description": "Steady and precise",
            "select_after_create": True,
        },
    )
    assert create_character_res.status_code == 200
    selected_ids = create_character_res.json()["selected_character_ids"]
    client.post(
        f"/workflow/projects/{project_id}/approve-characters",
        json={"selected_character_ids": selected_ids},
    )

    duplicate_res = client.post(f"/workflow/projects/{project_id}/duplicate")
    assert duplicate_res.status_code == 200
    duplicate_payload = duplicate_res.json()

    assert duplicate_payload["project_id"] != project_id
    assert duplicate_payload["title"] == "Duplicate Source Copy"
    assert duplicate_payload["workflow_state"] == "production_ready"
    assert duplicate_payload["script_draft"]
    assert duplicate_payload["script_approved"]
    assert duplicate_payload["character_package_approved"] is True
    assert duplicate_payload["selected_character_ids"] == selected_ids
    assert duplicate_payload["production_job_id"] is None
    assert duplicate_payload["final_video_url"] is None
    assert duplicate_payload["archived_at"] is None

    with Session(engine) as session:
        duplicated_versions = session.exec(
            select(ProjectScriptVersion).where(
                ProjectScriptVersion.project_id == duplicate_payload["project_id"]
            )
        ).all()
        assert {version.version_type for version in duplicated_versions} == {"draft", "approved"}

        duplicated_package = session.exec(
            select(ProjectCharacterPackage).where(
                ProjectCharacterPackage.project_id == duplicate_payload["project_id"]
            )
        ).first()
        assert duplicated_package is not None
        assert json.loads(duplicated_package.selected_character_ids_json) == selected_ids
