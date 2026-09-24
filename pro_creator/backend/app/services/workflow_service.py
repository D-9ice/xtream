from __future__ import annotations

from datetime import datetime, timezone
import math
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import (
    CREDITS_COST_IMAGE_GENERATE,
    CREDITS_COST_SCRIPT_GENERATE,
    CREDITS_COST_VIDEO_RENDER,
    CREDITS_COST_VOICE_GENERATE,
    FACTORY_MODE_ENABLED,
    XAI_API_KEY,
    XAI_TEXT_MODEL,
    XAI_VIDEO_MODEL,
)
from app.models import (
    CharacterProfile,
    Clip,
    OrchestrationJob,
    OrchestrationSchedule,
    Project,
    ProjectCharacterPackage,
    ProjectScriptVersion,
    Scene,
    User,
)
from app.schemas import (
    WorkflowAutoCreateResponse,
    WorkflowCharacterListResponse,
    WorkflowCharacterResponse,
    WorkflowLibraryResponse,
    WorkflowProductionStatusResponse,
    WorkflowProductionSummaryResponse,
    WorkflowProjectResponse,
)
from app.services.credits import consume_credits, get_or_create_subscription, has_factory_mode_access, has_owner_mode_access
from app.services.character_slots import ensure_character_slot_available
from app.services.image_engine import generate_image_bytes, generate_image_for_scene
from app.services.script_engine import generate_script
from app.services.social_publish import publish_to_all_connections
from app.services.video_engine import render_video
from app.services.voice_engine import generate_voice_for_scene
from app.storage import project_key, storage_client
from app.tenant import current_tenant_id
from app.utils.file_manager import (
    delete_project_dir,
    ensure_project_dirs,
    write_character_voice_profiles,
    write_scene_metadata,
    write_script,
)

FACTORY_MODE_SERIES_GENRE = "Series Video Maker (Factory Mode Only)"
REAL_EVENTS_GENRE = "Real Events"


def _is_real_events_genre(genre: str | None) -> bool:
    return (genre or "").strip() == REAL_EVENTS_GENRE

WORKFLOW_STAGE_ORDER = {
    "draft": 0,
    "script_generating": 0,
    "script_generated": 1,
    "script_approved": 1,
    "characters_in_progress": 2,
    "characters_approved": 2,
    "production_ready": 3,
    "production_queued": 3,
    "production_running": 3,
    "video_completed": 3,
    "production_failed": 3,
}

WORKFLOW_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"script_generating"},
    "script_generating": {"draft", "script_generated"},
    "script_generated": {"draft", "script_approved", "script_generating"},
    "script_approved": {"characters_in_progress", "script_generated", "script_generating"},
    "characters_in_progress": {
        "characters_approved",
        "script_generated",
        "script_generating",
    },
    "characters_approved": {
        "production_ready",
        "characters_in_progress",
        "script_generated",
        "script_generating",
    },
    "production_ready": {
        "production_queued",
        "characters_in_progress",
        "script_generated",
        "script_generating",
    },
    "production_queued": {"production_failed", "production_running"},
    "production_running": {"production_failed", "video_completed"},
    "video_completed": {"characters_in_progress", "script_generated", "script_generating"},
    "production_failed": {
        "production_ready",
        "characters_in_progress",
        "script_generated",
        "script_generating",
    },
}

VOICE_EXTENSIONS = ("wav", "mp3", "ogg", "m4a")


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _loads_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _loads_json(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _dumps_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _normalize_reference_image_urls(
    reference_image_urls: list[str] | None = None,
    *,
    reference_image_url: str | None = None,
    canonical_image_url: str | None = None,
) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in reference_image_urls or []:
        clean = str(item).strip()
        if clean and clean not in seen:
            seen.add(clean)
            normalized.append(clean)
    for item in [reference_image_url, canonical_image_url]:
        clean = str(item or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            normalized.append(clean)
    return normalized


def _topic_from_inputs(title: str, idea_prompt: str | None, genre: str | None) -> str:
    pieces = [title.strip()]
    if idea_prompt and idea_prompt.strip():
        pieces.append(idea_prompt.strip())
    if genre and genre.strip():
        pieces.append(f"Genre: {genre.strip()}")
    return "\n\n".join([piece for piece in pieces if piece])


def _scenes_from_script(script_text: str) -> list[dict[str, Any]]:
    raw_scenes = [line.strip() for line in script_text.splitlines() if line.strip()]
    scenes = [{"id": idx + 1, "text": text} for idx, text in enumerate(raw_scenes[:20])]
    if scenes:
        return scenes
    trimmed = script_text.strip() or "(empty script)"
    return [{"id": 1, "text": trimmed[:400]}]


def _set_project_state(project: Project, workflow_state: str) -> None:
    project.workflow_state = workflow_state
    project.status = workflow_state
    project.updated_at = utc_now()


def validate_workflow_transition(current_state: str, next_state: str) -> None:
    if current_state == next_state:
        return
    allowed = WORKFLOW_TRANSITIONS.get(current_state, set())
    if next_state not in allowed:
        raise ValueError(f"Invalid workflow transition: {current_state} -> {next_state}")


def transition_project_state(project: Project, next_state: str) -> None:
    validate_workflow_transition(project.workflow_state, next_state)
    _set_project_state(project, next_state)


def _project_selected_character_ids(project: Project) -> list[str]:
    return _loads_list(project.selected_character_ids_json)


def _project_production_job_pk(project: Project) -> int | None:
    raw_job_id = (project.production_job_id or "").strip()
    if not raw_job_id:
        return None
    try:
        return int(raw_job_id)
    except ValueError:
        return None


def _get_project_production_job(session: Session, project: Project) -> OrchestrationJob | None:
    job_id = _project_production_job_pk(project)
    if job_id is None:
        return None
    job = session.get(OrchestrationJob, job_id)
    if not job or job.tenant_id != project.tenant_id:
        return None
    return job


def _store_project_selected_character_ids(project: Project, selected_character_ids: list[str]) -> None:
    deduped = list(dict.fromkeys([item.strip() for item in selected_character_ids if item.strip()]))
    project.selected_character_ids_json = _dumps_json(deduped)
    project.updated_at = utc_now()


def require_script_approved_for_characters(project: Project) -> None:
    if not (project.script_approved or "").strip():
        raise ValueError("Script approval required before choosing characters")


def require_production_ready(project: Project) -> None:
    if project.workflow_state == "characters_approved":
        transition_project_state(project, "production_ready")
        return
    if project.workflow_state != "production_ready":
        raise ValueError("Production is not ready yet")


def _personality_traits(profile: CharacterProfile) -> list[str]:
    parsed = _loads_json(profile.personality_traits_json)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return []


def _reference_image_urls(profile: CharacterProfile) -> list[str]:
    parsed = _loads_json(profile.reference_image_urls_json)
    if isinstance(parsed, list):
        return _normalize_reference_image_urls(
            [str(item).strip() for item in parsed if str(item).strip()],
            reference_image_url=profile.reference_image_url,
            canonical_image_url=profile.canonical_image_url,
        )
    return _normalize_reference_image_urls(
        reference_image_url=profile.reference_image_url,
        canonical_image_url=profile.canonical_image_url,
    )


def _snapshot_reference_image_urls(item: dict[str, Any]) -> list[str]:
    return _normalize_reference_image_urls(
        item.get("reference_image_urls"),
        reference_image_url=item.get("reference_image_url"),
        canonical_image_url=item.get("canonical_image_url"),
    )


def character_to_response(profile: CharacterProfile) -> WorkflowCharacterResponse:
    return WorkflowCharacterResponse(
        character_id=profile.character_id,
        name=profile.name,
        role_type=profile.role_type,
        description=profile.description,
        visual_prompt_base=profile.visual_prompt_base,
        negative_prompt_base=profile.negative_prompt_base,
        consistency_seed=profile.consistency_seed,
        identity_hash=profile.identity_hash,
        lock_identity=profile.lock_identity,
        reference_image_url=profile.reference_image_url,
        reference_image_urls=_reference_image_urls(profile),
        canonical_image_url=profile.canonical_image_url,
        personality_traits=_personality_traits(profile),
        voice_profile=profile.voice_profile,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def project_to_response(project: Project) -> WorkflowProjectResponse:
    updated_at = project.updated_at or project.created_at
    return WorkflowProjectResponse(
        project_id=project.project_id,
        title=project.title,
        topic=project.topic,
        status=project.status,
        idea_prompt=project.idea_prompt,
        short_description=getattr(project, "short_description", None),
        genre=project.genre,
        target_duration_minutes=project.target_duration_minutes,
        start_credits=getattr(project, "start_credits", None),
        end_credits=getattr(project, "end_credits", None),
        workflow_state=project.workflow_state,
        script_draft=project.script_draft,
        script_approved=project.script_approved,
        script_approved_at=project.script_approved_at,
        character_package_approved=project.character_package_approved,
        character_package_approved_at=project.character_package_approved_at,
        selected_character_ids=_project_selected_character_ids(project),
        production_job_id=project.production_job_id,
        final_video_url=project.final_video_url,
        archived_at=project.archived_at,
        created_at=project.created_at,
        updated_at=updated_at,
    )


def get_project_or_404(session: Session, project_id: str) -> Project:
    tenant_id = current_tenant_id()
    project = session.exec(
        select(Project).where(Project.project_id == project_id, Project.tenant_id == tenant_id)
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def list_projects(session: Session, *, include_archived: bool = False) -> list[WorkflowProjectResponse]:
    tenant_id = current_tenant_id()
    statement = select(Project).where(Project.tenant_id == tenant_id)
    if not include_archived:
        statement = statement.where(Project.archived_at.is_(None))
    projects = session.exec(statement.order_by(Project.updated_at.desc())).all()
    return [project_to_response(project) for project in projects]


def delete_projects(
    *,
    session: Session,
    projects: list[Project],
) -> list[str]:
    deleted_ids = [project.project_id for project in projects]
    if not deleted_ids:
        return []

    tenant_id = projects[0].tenant_id
    session.exec(
        ProjectScriptVersion.__table__.delete().where(
            ProjectScriptVersion.tenant_id == tenant_id,
            ProjectScriptVersion.project_id.in_(deleted_ids),
        )
    )
    session.exec(
        ProjectCharacterPackage.__table__.delete().where(
            ProjectCharacterPackage.tenant_id == tenant_id,
            ProjectCharacterPackage.project_id.in_(deleted_ids),
        )
    )
    session.exec(
        Scene.__table__.delete().where(
            Scene.tenant_id == tenant_id,
            Scene.project_id.in_(deleted_ids),
        )
    )
    session.exec(
        Clip.__table__.delete().where(
            Clip.tenant_id == tenant_id,
            Clip.project_id.in_(deleted_ids),
        )
    )
    session.exec(
        OrchestrationJob.__table__.delete().where(
            OrchestrationJob.tenant_id == tenant_id,
            OrchestrationJob.project_id.in_(deleted_ids),
        )
    )
    session.exec(
        OrchestrationSchedule.__table__.delete().where(
            OrchestrationSchedule.tenant_id == tenant_id,
            OrchestrationSchedule.project_id.in_(deleted_ids),
        )
    )
    session.exec(
        Project.__table__.delete().where(
            Project.tenant_id == tenant_id,
            Project.project_id.in_(deleted_ids),
        )
    )
    session.commit()
    for project_id in deleted_ids:
        delete_project_dir(project_id)
    return deleted_ids


def delete_project(
    *,
    session: Session,
    project: Project,
) -> None:
    delete_projects(session=session, projects=[project])


def create_project(
    *,
    session: Session,
    title: str,
    idea_prompt: str | None,
    short_description: str | None = None,
    genre: str | None,
    target_duration_minutes: int,
    start_credits: str | None = None,
    end_credits: str | None = None,
) -> WorkflowProjectResponse:
    project = Project(
        tenant_id=current_tenant_id(),
        project_id=str(uuid4()),
        title=title.strip(),
        topic=_topic_from_inputs(title, idea_prompt, genre),
        idea_prompt=(idea_prompt or "").strip() or None,
        short_description=(short_description or "").strip() or None,
        genre=(genre or "").strip() or None,
        target_duration_minutes=max(1, int(target_duration_minutes or 3)),
        start_credits=(start_credits or "").strip() or None,
        end_credits=(end_credits or "").strip() or None,
        status="draft",
        workflow_state="draft",
    )
    ensure_project_dirs(project.project_id)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project_to_response(project)


def update_project_metadata(
    *,
    session: Session,
    project: Project,
    title: str | None = None,
    idea_prompt: str | None = None,
    short_description: str | None = None,
    genre: str | None = None,
    target_duration_minutes: int | None = None,
    start_credits: str | None = None,
    end_credits: str | None = None,
) -> WorkflowProjectResponse:
    if title is not None and title.strip():
        project.title = title.strip()
    if idea_prompt is not None:
        project.idea_prompt = idea_prompt.strip() or None
    if short_description is not None:
        project.short_description = short_description.strip() or None
    if genre is not None:
        project.genre = genre.strip() or None
    if target_duration_minutes is not None:
        project.target_duration_minutes = max(1, int(target_duration_minutes))
    if start_credits is not None:
        project.start_credits = start_credits.strip() or None
    if end_credits is not None:
        project.end_credits = end_credits.strip() or None
    project.topic = _topic_from_inputs(project.title, project.idea_prompt, project.genre)
    project.updated_at = utc_now()
    session.add(project)
    session.commit()
    session.refresh(project)
    return project_to_response(project)


def archive_project(
    *,
    session: Session,
    project: Project,
) -> WorkflowProjectResponse:
    if project.archived_at is None:
        project.archived_at = utc_now()
    project.updated_at = utc_now()
    session.add(project)
    session.commit()
    session.refresh(project)
    return project_to_response(project)


def _duplicate_workflow_state(project: Project) -> str:
    if project.character_package_approved and (project.script_approved or "").strip():
        return "production_ready"
    if (project.script_approved or "").strip():
        return "script_approved"
    if (project.script_draft or "").strip():
        return "script_generated"
    return "draft"


def duplicate_project(
    *,
    session: Session,
    project: Project,
) -> WorkflowProjectResponse:
    duplicate_id = str(uuid4())
    duplicate_title = f"{project.title} Copy"
    duplicate_state = _duplicate_workflow_state(project)
    duplicate = Project(
        tenant_id=project.tenant_id,
        project_id=duplicate_id,
        title=duplicate_title,
        topic=project.topic,
        status=duplicate_state,
        idea_prompt=project.idea_prompt,
        short_description=getattr(project, "short_description", None),
        genre=project.genre,
        target_duration_minutes=project.target_duration_minutes,
        start_credits=getattr(project, "start_credits", None),
        end_credits=getattr(project, "end_credits", None),
        workflow_state=duplicate_state,
        script_draft=project.script_draft,
        script_approved=project.script_approved,
        script_approved_at=project.script_approved_at,
        character_package_approved=project.character_package_approved,
        character_package_approved_at=project.character_package_approved_at,
        selected_character_ids_json=project.selected_character_ids_json,
        production_job_id=None,
        final_video_url=None,
        archived_at=None,
    )
    ensure_project_dirs(duplicate.project_id)
    session.add(duplicate)
    session.commit()
    session.refresh(duplicate)

    script_source = (duplicate.script_approved or duplicate.script_draft or "").strip()
    if script_source:
        scenes_source = session.exec(
            select(Scene).where(
                Scene.project_id == project.project_id,
                Scene.tenant_id == project.tenant_id,
            )
        ).all()
        scenes = (
            [
                {"id": idx + 1, "text": scene.text}
                for idx, scene in enumerate(scenes_source)
                if (scene.text or "").strip()
            ]
            or _scenes_from_script(script_source)
        )
        _persist_project_script(session=session, project=duplicate, script_text=script_source, scenes=scenes)
        _record_script_version(session, project=duplicate, version_type="draft", script_content=duplicate.script_draft or script_source)
        if (duplicate.script_approved or "").strip():
            _record_script_version(
                session,
                project=duplicate,
                version_type="approved",
                script_content=duplicate.script_approved or script_source,
            )

    if duplicate.character_package_approved:
        original_package = latest_character_package(session, project.project_id)
        if original_package:
            session.add(
                ProjectCharacterPackage(
                    tenant_id=duplicate.tenant_id,
                    project_id=duplicate.project_id,
                    approved_by_user_id=original_package.approved_by_user_id,
                    selected_character_ids_json=original_package.selected_character_ids_json,
                    package_snapshot_json=original_package.package_snapshot_json,
                    approved_at=original_package.approved_at,
                )
            )

    session.add(duplicate)
    session.commit()
    session.refresh(duplicate)
    return project_to_response(duplicate)


def _replace_project_scenes(session: Session, project: Project, scenes: list[dict[str, Any]]) -> None:
    session.exec(
        Scene.__table__.delete().where(
            Scene.project_id == project.project_id,
            Scene.tenant_id == project.tenant_id,
        )
    )
    for scene in scenes:
        session.add(
            Scene(
                tenant_id=project.tenant_id,
                project_id=project.project_id,
                text=str(scene.get("text", "")).strip(),
            )
        )


def _persist_project_script(
    *,
    session: Session,
    project: Project,
    script_text: str,
    scenes: list[dict[str, Any]],
) -> None:
    project_path = ensure_project_dirs(project.project_id)
    write_script(project_path, script_text)
    write_scene_metadata(project_path, scenes)
    _replace_project_scenes(session, project, scenes)


def _clear_downstream_approvals(project: Project) -> None:
    project.script_approved = None
    project.script_approved_at = None
    project.character_package_approved = False
    project.character_package_approved_at = None
    project.production_job_id = None
    project.final_video_url = None


def _record_script_version(
    session: Session,
    *,
    project: Project,
    version_type: str,
    script_content: str,
) -> None:
    session.add(
        ProjectScriptVersion(
            tenant_id=project.tenant_id,
            project_id=project.project_id,
            version_type=version_type,
            script_content=script_content,
        )
    )


def generate_project_script(
    *,
    session: Session,
    project: Project,
    current_user: User,
    title: str,
    idea_prompt: str | None,
    genre: str | None,
    target_duration_minutes: int,
    tone: str,
) -> WorkflowProjectResponse:
    project.title = title.strip()
    project.idea_prompt = (idea_prompt or "").strip() or None
    project.genre = (genre or "").strip() or None
    project.target_duration_minutes = max(1, int(target_duration_minutes or 3))
    project.topic = _topic_from_inputs(project.title, project.idea_prompt, project.genre)
    _clear_downstream_approvals(project)
    transition_project_state(project, "script_generating")
    session.add(project)
    session.commit()

    result = generate_script(
        project.topic,
        project.target_duration_minutes,
        tone,
        genre=project.genre,
    )
    script_text = result["full_script"]
    scenes = result["scenes"]

    _persist_project_script(session=session, project=project, script_text=script_text, scenes=scenes)
    project.script_draft = script_text
    transition_project_state(project, "script_generated")
    _record_script_version(session, project=project, version_type="draft", script_content=script_text)
    session.add(project)
    consume_credits(
        session=session,
        user=current_user,
        amount=CREDITS_COST_SCRIPT_GENERATE,
        reason="workflow script generation",
        action="workflow.script.generate",
        reference_id=project.project_id,
        provider="xai",
        model=XAI_TEXT_MODEL,
        metadata={"duration_minutes": project.target_duration_minutes, "tone": tone},
    )
    session.commit()
    session.refresh(project)
    return project_to_response(project)


def update_script_draft(
    *,
    session: Session,
    project: Project,
    script_text: str,
    update_scenes: bool,
) -> WorkflowProjectResponse:
    next_script = script_text.strip() or "(empty script)"
    scenes = _scenes_from_script(next_script) if update_scenes else _scenes_from_script(next_script)
    _persist_project_script(session=session, project=project, script_text=next_script, scenes=scenes)
    project.script_draft = next_script
    _clear_downstream_approvals(project)
    transition_project_state(project, "script_generated")
    _record_script_version(session, project=project, version_type="draft", script_content=next_script)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project_to_response(project)


def approve_script(*, session: Session, project: Project) -> WorkflowProjectResponse:
    if not (project.script_draft or "").strip():
        raise ValueError("No script draft available")
    project.script_approved = project.script_draft
    project.script_approved_at = utc_now()
    transition_project_state(project, "script_approved")
    _record_script_version(
        session,
        project=project,
        version_type="approved",
        script_content=project.script_draft,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project_to_response(project)


def _identity_hash(*parts: str) -> str:
    digest = hashlib.sha256("|".join([part.strip().lower() for part in parts]).encode("utf-8"))
    return digest.hexdigest()


def _build_character_prompts(name: str, role_type: str, description: str) -> tuple[str, str]:
    visual = f"{name}, {role_type} character, {description.strip()}".strip(", ")
    negative = "blurry, distorted, inconsistent face, extra limbs, duplicate subject"
    return visual, negative


def _validate_character_name(name: str) -> str:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Character name is required")
    return clean_name


def _create_character_image(
    *,
    character_id: str,
    prompt: str,
    style: str,
) -> str:
    image_bytes, _provider = generate_image_bytes(prompt=prompt, style=style, scene_id=1)
    ext = "png"
    key = f"_library/characters/{character_id}.{ext}"
    storage_client.write_bytes(key, image_bytes, content_type="image/png")
    return storage_client.public_url(key)


def create_character_profile(
    *,
    session: Session,
    current_user: User,
    name: str,
    role_type: str,
    description: str,
    personality_traits: list[str],
    voice_profile: str | None,
    reference_image_url: str | None,
    reference_image_urls: list[str] | None,
    canonical_image_url: str | None,
    visual_prompt_base: str | None,
    negative_prompt_base: str | None,
    lock_identity: bool,
) -> CharacterProfile:
    ensure_character_slot_available(session=session, user=current_user)
    clean_name = _validate_character_name(name)
    clean_description = description.strip()
    visual, negative = _build_character_prompts(clean_name, role_type, clean_description)
    normalized_reference_urls = _normalize_reference_image_urls(
        reference_image_urls,
        reference_image_url=reference_image_url,
        canonical_image_url=canonical_image_url,
    )
    profile = CharacterProfile(
        tenant_id=current_tenant_id(),
        name=clean_name,
        role_type=role_type.strip() or "supporting",
        description=clean_description,
        visual_prompt_base=(visual_prompt_base or visual).strip(),
        negative_prompt_base=(negative_prompt_base or negative).strip(),
        consistency_seed=_identity_hash(clean_name, clean_description)[:16],
        identity_hash=_identity_hash(clean_name, clean_description, role_type),
        lock_identity=lock_identity,
        reference_image_url=(reference_image_url or "").strip() or (normalized_reference_urls[0] if normalized_reference_urls else None),
        reference_image_urls_json=_dumps_json(normalized_reference_urls),
        canonical_image_url=(canonical_image_url or "").strip() or None,
        personality_traits_json=_dumps_json(personality_traits),
        voice_profile=(voice_profile or "").strip() or None,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def list_character_profiles(session: Session) -> list[CharacterProfile]:
    tenant_id = current_tenant_id()
    profiles = list(
        session.exec(
        select(CharacterProfile)
        .where(CharacterProfile.tenant_id == tenant_id)
        .order_by(CharacterProfile.updated_at.desc())
        ).all()
    )
    cleaned_profiles: list[CharacterProfile] = []
    removed_empty_profile = False
    for profile in profiles:
        if not (profile.name or "").strip():
            session.delete(profile)
            removed_empty_profile = True
            continue
        cleaned_profiles.append(profile)
    if removed_empty_profile:
        session.commit()
    return cleaned_profiles


def build_character_list_response(*, session: Session, project: Project) -> WorkflowCharacterListResponse:
    library = list_character_profiles(session)
    selected_ids = _project_selected_character_ids(project)
    selected_map = {profile.character_id: profile for profile in library}
    approved_package = latest_character_package(session, project.project_id)
    approved_character_ids = _loads_list(approved_package.selected_character_ids_json) if approved_package else []
    return WorkflowCharacterListResponse(
        library=[character_to_response(profile) for profile in library],
        selected_character_ids=selected_ids,
        selected=[character_to_response(selected_map[item]) for item in selected_ids if item in selected_map],
        approved_character_ids=approved_character_ids,
        approved_at=approved_package.approved_at if approved_package else None,
    )


def select_characters(
    *,
    session: Session,
    project: Project,
    selected_character_ids: list[str],
) -> WorkflowCharacterListResponse:
    require_script_approved_for_characters(project)
    _store_project_selected_character_ids(project, selected_character_ids)
    if project.workflow_state != "characters_in_progress":
        transition_project_state(project, "characters_in_progress")
    project.character_package_approved = False
    project.character_package_approved_at = None
    project.final_video_url = None
    project.production_job_id = None
    session.add(project)
    session.commit()
    session.refresh(project)
    return build_character_list_response(session=session, project=project)


def generate_character_profile(
    *,
    session: Session,
    current_user: User,
    name: str,
    role_type: str,
    description: str,
    personality_traits: list[str],
    voice_profile: str | None,
    style: str,
    lock_identity: bool,
    skip_character_slot_check: bool = False,
) -> CharacterProfile:
    if not skip_character_slot_check:
        ensure_character_slot_available(session=session, user=current_user)
    clean_name = _validate_character_name(name)
    clean_description = description.strip()
    visual, negative = _build_character_prompts(clean_name, role_type, clean_description)
    character_id = str(uuid4())
    canonical_image_url = _create_character_image(
        character_id=character_id,
        prompt=f"{visual}. Premium character concept art. Keep identity consistent.",
        style=style,
    )
    profile = CharacterProfile(
        tenant_id=current_tenant_id(),
        character_id=character_id,
        name=clean_name,
        role_type=role_type.strip() or "supporting",
        description=clean_description,
        visual_prompt_base=visual,
        negative_prompt_base=negative,
        consistency_seed=_identity_hash(clean_name, clean_description)[:16],
        identity_hash=_identity_hash(clean_name, clean_description, role_type),
        lock_identity=lock_identity,
        reference_image_urls_json=_dumps_json([canonical_image_url]),
        canonical_image_url=canonical_image_url,
        personality_traits_json=_dumps_json(personality_traits),
        voice_profile=(voice_profile or "").strip() or None,
    )
    session.add(profile)
    consume_credits(
        session=session,
        user=current_user,
        amount=CREDITS_COST_IMAGE_GENERATE,
        reason="workflow character generation",
        action="workflow.character.generate",
        reference_id=character_id,
        provider="image",
        model=style,
    )
    session.commit()
    session.refresh(profile)
    return profile


def upload_character_reference(
    *,
    session: Session,
    current_user: User,
    name: str,
    role_type: str,
    description: str,
    filename: str,
    content: bytes,
    voice_profile: str | None,
    lock_identity: bool,
) -> CharacterProfile:
    ensure_character_slot_available(session=session, user=current_user)
    character_id = str(uuid4())
    suffix = Path(filename or "reference.png").suffix.lower() or ".png"
    content_type = "image/png" if suffix == ".png" else "image/jpeg"
    key = f"_library/characters/{character_id}{suffix}"
    storage_client.write_bytes(key, content, content_type=content_type)
    image_url = storage_client.public_url(key)
    return create_character_profile(
        session=session,
        current_user=current_user,
        name=name,
        role_type=role_type,
        description=description,
        personality_traits=[],
        voice_profile=voice_profile,
        reference_image_url=image_url,
        reference_image_urls=[image_url],
        canonical_image_url=image_url,
        visual_prompt_base=None,
        negative_prompt_base=None,
        lock_identity=lock_identity,
    )


def latest_character_package(session: Session, project_id: str) -> ProjectCharacterPackage | None:
    tenant_id = current_tenant_id()
    return session.exec(
        select(ProjectCharacterPackage)
        .where(
            ProjectCharacterPackage.project_id == project_id,
            ProjectCharacterPackage.tenant_id == tenant_id,
        )
        .order_by(ProjectCharacterPackage.approved_at.desc())
    ).first()


def approve_character_package(
    *,
    session: Session,
    project: Project,
    current_user: User,
    selected_character_ids: list[str] | None = None,
) -> WorkflowCharacterListResponse:
    require_script_approved_for_characters(project)

    selected_ids = selected_character_ids or _project_selected_character_ids(project)
    selected_ids = list(dict.fromkeys([item.strip() for item in selected_ids if item.strip()]))
    if not selected_ids:
        raise ValueError("Choose at least one character before approval")

    tenant_id = current_tenant_id()
    profiles = session.exec(
        select(CharacterProfile).where(
            CharacterProfile.tenant_id == tenant_id,
            CharacterProfile.character_id.in_(selected_ids),
        )
    ).all()
    if len(profiles) != len(selected_ids):
        raise ValueError("One or more selected characters could not be resolved")

    profile_map = {profile.character_id: profile for profile in profiles}
    snapshot = []
    for character_id in selected_ids:
        profile = profile_map[character_id]
        snapshot.append(
            {
                "character_id": profile.character_id,
                "name": profile.name,
                "role_type": profile.role_type,
                "description": profile.description,
                "visual_prompt_base": profile.visual_prompt_base,
                "negative_prompt_base": profile.negative_prompt_base,
                "consistency_seed": profile.consistency_seed,
                "identity_hash": profile.identity_hash,
                "lock_identity": profile.lock_identity,
                "reference_image_url": profile.reference_image_url,
                "reference_image_urls": _reference_image_urls(profile),
                "canonical_image_url": profile.canonical_image_url,
                "personality_traits": _personality_traits(profile),
                "voice_profile": profile.voice_profile,
            }
        )

    session.add(
        ProjectCharacterPackage(
            tenant_id=tenant_id,
            project_id=project.project_id,
            approved_by_user_id=current_user.id or 0,
            selected_character_ids_json=_dumps_json(selected_ids),
            package_snapshot_json=_dumps_json(snapshot),
        )
    )
    _store_project_selected_character_ids(project, selected_ids)
    project.character_package_approved = True
    project.character_package_approved_at = utc_now()
    transition_project_state(project, "characters_approved")
    transition_project_state(project, "production_ready")
    session.add(project)
    session.commit()
    session.refresh(project)
    return build_character_list_response(session=session, project=project)


def resolve_approved_production_package(session: Session, project_id: str) -> dict[str, Any]:
    project = get_project_or_404(session, project_id)
    if not (project.script_approved or "").strip():
        raise ValueError("Script approval required")
    narration_only = _is_real_events_genre(project.genre)
    if not narration_only and not project.character_package_approved:
        raise ValueError("Character approval required")
    package = latest_character_package(session, project_id)
    if not package:
        if narration_only:
            return {
                "project_id": project_id,
                "approved_script_snapshot": project.script_approved,
                "approved_character_package_snapshot": [],
                "script": project.script_approved,
                "short_description": getattr(project, "short_description", None),
                "start_credits": getattr(project, "start_credits", None),
                "end_credits": getattr(project, "end_credits", None),
                "characters": [],
                "references": {},
                "seeds": {},
                "prompts": {},
                "identity_rules": {},
                "reference_bundles": {},
                "voice_profiles": {},
            }
        raise ValueError("Approved character package not found")
    snapshot = _loads_json(package.package_snapshot_json)
    if not isinstance(snapshot, list) or (not snapshot and not narration_only):
        raise ValueError("Approved character package snapshot is empty")
    prompts = {
        item["character_id"]: {
            "visual_prompt_base": item.get("visual_prompt_base"),
            "negative_prompt_base": item.get("negative_prompt_base"),
        }
        for item in snapshot
        if isinstance(item, dict) and item.get("character_id")
    }
    identity_rules = {}
    reference_bundles = {}
    voice_profiles = {}
    for item in snapshot:
        if not isinstance(item, dict):
            continue
        character_id = str(item.get("character_id", "")).strip()
        if not character_id:
            continue
        refs = _snapshot_reference_image_urls(item)
        identity_rules[character_id] = {
            "identity_hash": item.get("identity_hash"),
            "consistency_seed": item.get("consistency_seed"),
            "lock_identity": bool(item.get("lock_identity", True)),
            "role_type": item.get("role_type"),
        }
        reference_bundles[character_id] = refs
        voice_profiles[character_id] = {
            "character_id": character_id,
            "name": item.get("name"),
            "voice_profile": item.get("voice_profile") or "default",
            "identity_hash": item.get("identity_hash"),
            "consistency_seed": item.get("consistency_seed"),
            "lock_identity": bool(item.get("lock_identity", True)),
            "reference_image_urls": refs,
        }
    return {
        "project_id": project_id,
        "approved_script_snapshot": project.script_approved,
        "approved_character_package_snapshot": snapshot,
        "script": project.script_approved,
        "short_description": getattr(project, "short_description", None),
        "start_credits": getattr(project, "start_credits", None),
        "end_credits": getattr(project, "end_credits", None),
        "characters": snapshot,
        "references": {
            item.get("character_id"): (_snapshot_reference_image_urls(item)[0] if _snapshot_reference_image_urls(item) else None)
            for item in snapshot
            if isinstance(item, dict)
        },
        "seeds": {
            item.get("character_id"): item.get("consistency_seed")
            for item in snapshot
            if isinstance(item, dict)
        },
        "prompts": prompts,
        "identity_rules": identity_rules,
        "reference_bundles": reference_bundles,
        "voice_profiles": voice_profiles,
    }


def _audio_exists(project_id: str, scene_id: int) -> bool:
    return any(
        storage_client.exists(project_key(project_id, f"audio/scene_{scene_id}.{ext}"))
        for ext in VOICE_EXTENSIONS
    )


def _image_exists(project_id: str, scene_id: int) -> bool:
    return storage_client.exists(project_key(project_id, f"images/scene_{scene_id}.png"))


def _scene_prompt(scene_text: str, bundle: dict[str, Any]) -> str:
    context = _build_scene_render_context(scene_text, bundle)
    return context["prompt"]


def _extract_dialogue_speakers(scene_text: str) -> set[str]:
    speakers: set[str] = set()
    for raw_line in (scene_text or "").splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        if line.lower().startswith(("scene ", "intent:", "narration:", "visuals:")):
            continue
        speaker, text_line = line.split(":", 1)
        speaker = speaker.strip()
        text_line = text_line.strip()
        if not speaker or not text_line:
            continue
        if len(speaker) > 32 or re.search(r"\s{2,}", speaker):
            continue
        speakers.add(speaker.lower())
    return speakers


def _scene_characters(scene_text: str, bundle: dict[str, Any]) -> list[dict[str, Any]]:
    text_lower = (scene_text or "").lower()
    dialogue_speakers = _extract_dialogue_speakers(scene_text)
    matched: list[tuple[int, dict[str, Any]]] = []
    fallback: list[dict[str, Any]] = []
    for character in bundle.get("characters", []):
        if not isinstance(character, dict):
            continue
        name = str(character.get("name", "")).strip()
        if not name:
            continue
        fallback.append(character)
        score = 0
        normalized_name = name.lower()
        first_name = normalized_name.split()[0]
        if normalized_name in dialogue_speakers:
            score += 4
        if first_name and first_name in dialogue_speakers:
            score += 3
        if normalized_name and normalized_name in text_lower:
            score += 2
        elif first_name and re.search(rf"\b{re.escape(first_name)}\b", text_lower):
            score += 1
        if score > 0:
            matched.append((score, character))
    if matched:
        return [character for _score, character in sorted(matched, key=lambda item: item[0], reverse=True)]
    if len(fallback) == 1:
        return fallback
    return []


def _build_scene_render_context(scene_text: str, bundle: dict[str, Any]) -> dict[str, Any]:
    matched_characters = _scene_characters(scene_text, bundle)
    focus_characters = matched_characters or [
        character
        for character in bundle.get("characters", [])
        if isinstance(character, dict)
    ][:2]
    cast: list[str] = []
    identity_notes: list[str] = []
    negative_notes: list[str] = []
    matched_character_ids: list[str] = []
    identity_snapshots: list[dict[str, Any]] = []
    selected_voice_profile = "default"

    for index, character in enumerate(focus_characters):
        character_id = str(character.get("character_id", "")).strip()
        name = str(character.get("name", "")).strip()
        if character_id:
            matched_character_ids.append(character_id)
        visual = str(character.get("visual_prompt_base", "")).strip()
        negative = str(character.get("negative_prompt_base", "")).strip()
        if name or visual:
            cast.append(f"{name}: {visual}".strip(": "))
        identity = bundle.get("identity_rules", {}).get(character_id, {})
        refs = bundle.get("reference_bundles", {}).get(character_id, [])
        seed = str(identity.get("consistency_seed", "")).strip()
        identity_hash = str(identity.get("identity_hash", "")).strip()
        if name and seed:
            identity_notes.append(f"{name} seed {seed}")
        if name and identity_hash:
            identity_notes.append(f"{name} hash {identity_hash[:16]}")
        if name and identity.get("lock_identity", True):
            identity_notes.append(f"{name} lock identity")
        if name and refs:
            identity_notes.append(f"{name} refs {', '.join(refs[:2])}")
        if negative:
            negative_notes.append(f"{name}: {negative}".strip(": "))
        if index == 0:
            selected_voice_profile = (
                bundle.get("voice_profiles", {})
                .get(character_id, {})
                .get("voice_profile")
                or character.get("voice_profile")
                or "default"
            )
        identity_snapshots.append(
            {
                "character_id": character_id,
                "name": name,
                "identity_hash": identity_hash or None,
                "consistency_seed": seed or None,
                "lock_identity": bool(identity.get("lock_identity", True)),
                "reference_image_urls": refs[:],
                "voice_profile": (
                    bundle.get("voice_profiles", {})
                    .get(character_id, {})
                    .get("voice_profile")
                    or character.get("voice_profile")
                    or "default"
                ),
            }
        )

    details: list[str] = []
    if cast:
        details.append(f"Approved cast: {'; '.join(cast[:4])}")
    if identity_notes:
        details.append(f"Identity locks: {'; '.join(identity_notes[:6])}")
    if negative_notes:
        details.append(f"Avoid drift: {'; '.join(negative_notes[:4])}")
    prompt = scene_text
    if details:
        prompt = f"{scene_text}\n\n" + "\n".join(details)
    return {
        "prompt": prompt,
        "matched_character_ids": matched_character_ids,
        "identity_snapshots": identity_snapshots,
        "voice_profile": selected_voice_profile or "default",
    }


def workflow_production_summary(
    *,
    session: Session,
    project: Project,
    current_user: User,
) -> WorkflowProductionSummaryResponse:
    subscription = get_or_create_subscription(session, current_user)
    selected_ids = _project_selected_character_ids(project)
    narration_only = _is_real_events_genre(project.genre)
    characters = []
    if selected_ids and not narration_only:
        profiles = session.exec(
            select(CharacterProfile).where(
                CharacterProfile.tenant_id == current_tenant_id(),
                CharacterProfile.character_id.in_(selected_ids),
            )
        ).all()
        profile_map = {profile.character_id: profile for profile in profiles}
        characters = [
            character_to_response(profile_map[item])
            for item in selected_ids
            if item in profile_map
        ]
    return WorkflowProductionSummaryResponse(
        project_id=project.project_id,
        workflow_state=project.workflow_state,
        script_ready=bool((project.script_approved or "").strip()),
        characters_ready=narration_only or bool(project.character_package_approved),
        estimated_credits=CREDITS_COST_VIDEO_RENDER,
        current_credit_balance=subscription.credits_balance,
        target_duration_minutes=max(1, int(project.target_duration_minutes or 3)),
        selected_characters=characters,
        final_video_url=project.final_video_url,
    )


def production_status(session: Session, project: Project) -> WorkflowProductionStatusResponse:
    job = _get_project_production_job(session, project)
    return WorkflowProductionStatusResponse(
        project_id=project.project_id,
        workflow_state=project.workflow_state,
        production_job_id=project.production_job_id,
        queue_status=job.status if job else None,
        queue_attempts=job.attempts if job else 0,
        queue_max_attempts=job.max_attempts if job else 0,
        last_error=job.last_error if job else None,
        can_retry=bool(job and job.status == "failed" and project.workflow_state == "production_failed"),
        final_video_url=project.final_video_url,
    )


def _write_production_bundle_artifact(project_id: str, bundle: dict[str, Any]) -> None:
    key = project_key(project_id, "workflow/approved_production_bundle.json")
    storage_client.write_text(key, _dumps_json(bundle))


def _write_character_dna_artifacts(project_id: str, bundle: dict[str, Any]) -> None:
    voice_profiles = bundle.get("voice_profiles", {})
    if isinstance(voice_profiles, dict):
        write_character_voice_profiles(project_id, list(voice_profiles.values()))
    key = project_key(project_id, "workflow/character_dna_snapshot.json")
    storage_client.write_text(
        key,
        _dumps_json(
            {
                "identity_rules": bundle.get("identity_rules", {}),
                "reference_bundles": bundle.get("reference_bundles", {}),
                "prompts": bundle.get("prompts", {}),
            }
        ),
    )


def _write_scene_identity_plan(project_id: str, plan: list[dict[str, Any]]) -> None:
    key = project_key(project_id, "workflow/scene_identity_plan.json")
    storage_client.write_text(key, _dumps_json(plan))


def _perform_production(
    *,
    session: Session,
    project: Project,
    current_user: User,
    bundle: dict[str, Any],
) -> str | None:
    approved_script = str(bundle["script"]).strip() or "(empty script)"
    scenes = _scenes_from_script(approved_script)
    _persist_project_script(session=session, project=project, script_text=approved_script, scenes=scenes)
    _write_production_bundle_artifact(project.project_id, bundle)
    _write_character_dna_artifacts(project.project_id, bundle)
    grok_mode = bool(XAI_API_KEY.strip())
    scene_rows = {
        int(scene.id or 0): scene
        for scene in session.exec(
            select(Scene).where(
                Scene.project_id == project.project_id,
                Scene.tenant_id == project.tenant_id,
            )
        ).all()
    }
    scene_plan: list[dict[str, Any]] = []
    for scene in scenes:
        scene_id = int(scene.get("id", 1))
        scene_text = str(scene.get("text", "")).strip() or project.title
        scene_context = _build_scene_render_context(scene_text, bundle)
        scene_plan.append(
            {
                "scene_id": scene_id,
                "matched_character_ids": scene_context["matched_character_ids"],
                "identity_snapshots": scene_context["identity_snapshots"],
                "voice_profile": scene_context["voice_profile"],
            }
        )
        if grok_mode:
            continue
        if not _image_exists(project.project_id, scene_id):
            image_result = generate_image_for_scene(
                project.project_id,
                scene_id,
                scene_context["prompt"],
                "cinematic",
            )
            scene_row = scene_rows.get(scene_id)
            if scene_row:
                scene_row.image_path = image_result.get("image_path")
                session.add(scene_row)
        if not _audio_exists(project.project_id, scene_id):
            voice_result = generate_voice_for_scene(
                project.project_id,
                scene_id,
                scene_text,
                voice_profile=scene_context["voice_profile"],
            )
            scene_row = scene_rows.get(scene_id)
            if scene_row:
                scene_row.audio_path = voice_result.get("audio_path")
                session.add(scene_row)
    _write_scene_identity_plan(project.project_id, scene_plan)
    video_result = render_video(project.project_id)
    project.final_video_url = video_result["video_path"]
    transition_project_state(project, "video_completed")
    session.add(project)
    consume_credits(
        session=session,
        user=current_user,
        amount=CREDITS_COST_VIDEO_RENDER,
        reason="workflow video production",
        action="workflow.production.start",
        reference_id=project.project_id,
        provider="xai" if grok_mode else "video",
        model=XAI_VIDEO_MODEL if grok_mode else "ffmpeg",
    )
    session.commit()
    session.refresh(project)
    return video_result.get("video_path")


def execute_workflow_production_job(
    *,
    session: Session,
    job: OrchestrationJob,
) -> str | None:
    project = get_project_or_404(session, job.project_id)
    payload = _loads_json(job.payload) if job.payload else {}
    if not isinstance(payload, dict):
        payload = {}
    user_id = int(payload.get("user_id") or 0)
    current_user = session.get(User, user_id) if user_id else None
    if not current_user:
        raise ValueError("Workflow production user could not be resolved")

    summary = workflow_production_summary(session=session, project=project, current_user=current_user)
    if not summary.script_ready:
        raise ValueError("Script approval required")
    if not summary.characters_ready:
        raise ValueError("Character approval required")
    if summary.current_credit_balance < summary.estimated_credits:
        raise ValueError("Not enough credits to start production")
    if project.workflow_state == "production_ready":
        transition_project_state(project, "production_queued")
    if project.workflow_state == "production_failed":
        transition_project_state(project, "production_ready")
        transition_project_state(project, "production_queued")
    if project.workflow_state != "production_queued":
        raise ValueError("Project is not queued for production")

    transition_project_state(project, "production_running")
    session.add(project)
    session.commit()

    try:
        bundle = resolve_approved_production_package(session, project.project_id)
        return _perform_production(
            session=session,
            project=project,
            current_user=current_user,
            bundle=bundle,
        )
    except Exception:
        project = get_project_or_404(session, job.project_id)
        if project.workflow_state in {"production_queued", "production_running"}:
            transition_project_state(project, "production_failed")
        else:
            _set_project_state(project, "production_failed")
        session.add(project)
        session.commit()
        session.refresh(project)
        raise


def start_production(
    *,
    session: Session,
    project: Project,
    current_user: User,
) -> tuple[WorkflowProjectResponse, WorkflowProductionStatusResponse, str | None]:
    summary = workflow_production_summary(session=session, project=project, current_user=current_user)
    if not summary.script_ready:
        raise ValueError("Script approval required")
    if not summary.characters_ready:
        raise ValueError("Character approval required")
    if summary.current_credit_balance < summary.estimated_credits:
        raise ValueError("Not enough credits to start production")
    require_production_ready(project)
    job = OrchestrationJob(
        tenant_id=project.tenant_id,
        project_id=project.project_id,
        kind="workflow_production",
        status="queued",
        attempts=0,
        max_attempts=1,
        payload=_dumps_json({"user_id": current_user.id}),
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    project.production_job_id = str(job.id or "")
    transition_project_state(project, "production_queued")
    session.add(project)
    session.commit()
    session.refresh(project)
    return project_to_response(project), production_status(session, project), None


def _auto_create_character_specs(title: str) -> list[dict[str, str]]:
    clean_title = title.strip() or "Untitled"
    short_title = clean_title[:28].rstrip() or "Story"
    return [
        {
            "name": f"{short_title} Lead",
            "role_type": "main",
            "description": f"Primary character for {clean_title}.",
            "voice_profile": "default",
        },
        {
            "name": f"{short_title} Support",
            "role_type": "supporting",
            "description": f"Supporting character for {clean_title}.",
            "voice_profile": "default",
        },
    ]


def _auto_create_custom_character_specs(custom_characters: list[dict[str, Any]]) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for item in custom_characters[:10]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        role_type = str(item.get("role_type", "supporting")).strip() or "supporting"
        description = str(item.get("description", "")).strip()
        if not name:
            raise ValueError("Each custom character needs a name")
        specs.append(
            {
                "name": name,
                "role_type": role_type,
                "description": description,
                "voice_profile": str(item.get("voice_profile", "")).strip() or "default",
            }
        )
    return specs


def _auto_create_scene_count(duration_minutes: int) -> int:
    clean_duration = max(1, int(duration_minutes or 1))
    return max(6, min(10, int(math.ceil(clean_duration / 5.0))))


def _auto_create_estimated_credits(duration_minutes: int, *, character_count: int = 2) -> int:
    scene_count = _auto_create_scene_count(duration_minutes)
    character_generation_cost = max(0, int(character_count)) * CREDITS_COST_IMAGE_GENERATE
    return (
        CREDITS_COST_SCRIPT_GENERATE
        + character_generation_cost
        + CREDITS_COST_VIDEO_RENDER
        + (scene_count * (CREDITS_COST_IMAGE_GENERATE + CREDITS_COST_VOICE_GENERATE))
    )


def _max_affordable_auto_create_duration(credits_balance: int, *, character_count: int = 2) -> int:
    for duration in range(120, 0, -1):
        if _auto_create_estimated_credits(duration, character_count=character_count) <= credits_balance:
            return duration
    return 0


def auto_create_project(
    *,
    session: Session,
    current_user: User,
    title: str,
    duration_minutes: int,
    genre: str | None = None,
    short_description: str | None = None,
    custom_characters: list[dict[str, Any]] | None = None,
    start_credits: str | None = None,
    end_credits: str | None = None,
    allow_factory_mode_genre: bool = False,
) -> WorkflowAutoCreateResponse:
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Title is required")
    clean_genre = (genre or "").strip() or None
    clean_short_description = (short_description or "").strip() or None
    clean_start_credits = (start_credits or "").strip() or None
    clean_end_credits = (end_credits or "").strip() or None
    normalized_custom_characters = _auto_create_custom_character_specs(custom_characters or [])
    if len((custom_characters or [])) > 10:
        raise ValueError("Auto-create supports up to 10 custom characters")
    owner_mode_active = bool(session is not None and current_user is not None and has_owner_mode_access(session, current_user))
    if clean_genre == FACTORY_MODE_SERIES_GENRE and not allow_factory_mode_genre and not owner_mode_active:
        raise ValueError("Series Video Maker is available in Factory Mode only")
    if clean_genre == REAL_EVENTS_GENRE and normalized_custom_characters:
        raise ValueError("Real Events does not use character generation")
    requested_duration = max(1, min(120, int(duration_minutes or 3)))

    subscription = get_or_create_subscription(session, current_user)
    if has_owner_mode_access(session, current_user):
        applied_duration = requested_duration
        max_affordable_duration = requested_duration
    else:
        max_affordable_duration = _max_affordable_auto_create_duration(
            subscription.credits_balance,
            character_count=0 if normalized_custom_characters else 2,
        )
        if max_affordable_duration <= 0:
            raise ValueError("Not enough credits to auto-create a full video")
        applied_duration = min(requested_duration, max_affordable_duration)
    estimated_credits = _auto_create_estimated_credits(
        applied_duration,
        character_count=0 if normalized_custom_characters else 2,
    )

    created_project = create_project(
        session=session,
        title=clean_title,
        idea_prompt=clean_short_description,
        short_description=clean_short_description,
        genre=clean_genre,
        target_duration_minutes=applied_duration,
        start_credits=clean_start_credits,
        end_credits=clean_end_credits,
    )
    project = get_project_or_404(session, created_project.project_id)

    generate_project_script(
        session=session,
        project=project,
        current_user=current_user,
        title=clean_title,
        idea_prompt=clean_short_description,
        genre=clean_genre,
        target_duration_minutes=applied_duration,
        tone="cinematic",
    )
    approve_script(session=session, project=project)

    if clean_genre == REAL_EVENTS_GENRE:
        _store_project_selected_character_ids(project, [])
        project.character_package_approved = True
        project.character_package_approved_at = utc_now()
        _set_project_state(project, "production_ready")
        session.add(project)
        session.commit()
        session.refresh(project)
    else:
        created_character_ids: list[str] = []
        if normalized_custom_characters:
            character_specs = normalized_custom_characters
        else:
            character_specs = _auto_create_character_specs(clean_title)
        for spec in character_specs:
            try:
                if normalized_custom_characters:
                    profile = create_character_profile(
                        session=session,
                        current_user=current_user,
                        name=spec["name"],
                        role_type=spec["role_type"],
                        description=spec["description"],
                        personality_traits=["custom-auto-create"],
                        voice_profile=spec["voice_profile"],
                        reference_image_url=None,
                        reference_image_urls=None,
                        canonical_image_url=None,
                        visual_prompt_base=None,
                        negative_prompt_base=None,
                        lock_identity=True,
                    )
                else:
                    profile = generate_character_profile(
                        session=session,
                        current_user=current_user,
                        name=spec["name"],
                        role_type=spec["role_type"],
                        description=spec["description"],
                        personality_traits=["cinematic", "auto-created"],
                        voice_profile=spec["voice_profile"],
                        style="cinematic",
                        lock_identity=True,
                        skip_character_slot_check=owner_mode_active,
                    )
            except ValueError as exc:
                if "Character library is full" in str(exc) and created_character_ids:
                    break
                raise
            created_character_ids.append(profile.character_id)

        if not created_character_ids:
            raise ValueError("Auto-create could not generate any characters")

        select_characters(
            session=session,
            project=project,
            selected_character_ids=created_character_ids,
        )
        approve_character_package(
            session=session,
            project=project,
            current_user=current_user,
            selected_character_ids=created_character_ids,
        )
    project = get_project_or_404(session, project.project_id)
    start_production(
        session=session,
        project=project,
        current_user=current_user,
    )
    job = _get_project_production_job(session, project)
    if not job:
        raise ValueError("Production job not found")
    video_path = execute_workflow_production_job(session=session, job=job)
    job.status = "complete"
    job.last_error = None
    job.updated_at = utc_now()
    session.add(job)
    session.commit()
    session.refresh(job)
    project = get_project_or_404(session, project.project_id)
    return WorkflowAutoCreateResponse(
        project=project_to_response(project),
        status=production_status(session, project),
        video_path=video_path,
        requested_duration_minutes=requested_duration,
        applied_duration_minutes=applied_duration,
        max_affordable_duration_minutes=max_affordable_duration,
        estimated_credits=estimated_credits,
    )


def _factory_cancel_requested(job: OrchestrationJob) -> bool:
    payload = _loads_json(job.payload) if job.payload else {}
    return bool(payload.get("cancel_requested")) if isinstance(payload, dict) else False


def _mark_factory_cancelled(session: Session, job: OrchestrationJob) -> None:
    job.status = "cancelled"
    job.last_error = None
    job.updated_at = utc_now()
    session.add(job)
    session.commit()
    session.refresh(job)


def _clean_factory_mode_titles(raw_titles: Any) -> list[str]:
    titles: list[str] = []
    if isinstance(raw_titles, list):
        source_items = raw_titles
    elif isinstance(raw_titles, str):
        source_items = raw_titles.splitlines()
    else:
        source_items = []
    for item in source_items:
        title = str(item).strip()
        if title:
            titles.append(title)
    seen: set[str] = set()
    unique_titles: list[str] = []
    for title in titles:
        normalized = title.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_titles.append(title)
    return unique_titles[:25]


def execute_factory_mode_job(
    *,
    session: Session,
    job: OrchestrationJob,
) -> dict[str, Any]:
    payload = _loads_json(job.payload) if job.payload else {}
    if not isinstance(payload, dict):
        payload = {}

    user_id = int(payload.get("user_id") or 0)
    current_user = session.get(User, user_id) if user_id else None
    if not current_user:
        raise ValueError("Factory Mode user could not be resolved")
    if not FACTORY_MODE_ENABLED and not has_owner_mode_access(session, current_user):
        raise ValueError("Factory Mode is not enabled for this deployment")

    subscription = get_or_create_subscription(session, current_user)
    if not has_factory_mode_access(subscription, session=session, user=current_user):
        raise ValueError("Factory Mode access is required")

    titles = _clean_factory_mode_titles(payload.get("titles") or [])
    if not titles:
        raise ValueError("At least one title is required for Factory Mode")

    genre = str(payload.get("genre") or "").strip() or None
    short_description = str(payload.get("short_description") or "").strip() or None
    start_credits = str(payload.get("start_credits") or "").strip() or None
    end_credits = str(payload.get("end_credits") or "").strip() or None
    publish_message = str(payload.get("publish_message") or "").strip() or None
    duration_minutes = max(1, min(120, int(payload.get("duration_minutes") or 10)))

    processed: list[dict[str, Any]] = []
    stopped_reason: str | None = None
    for index, title in enumerate(titles, start=1):
        session.refresh(job)
        if _factory_cancel_requested(job):
            _mark_factory_cancelled(session, job)
            stopped_reason = "cancelled"
            break

        subscription = get_or_create_subscription(session, current_user)
        if not has_owner_mode_access(session, current_user) and subscription.credits_balance <= 0:
            stopped_reason = "credits_exhausted"
            break
        try:
            auto_result = auto_create_project(
                session=session,
                current_user=current_user,
                title=title,
                duration_minutes=duration_minutes,
                genre=genre,
                short_description=short_description,
                custom_characters=[],
                start_credits=start_credits,
                end_credits=end_credits,
                allow_factory_mode_genre=True,
            )
        except ValueError as exc:
            if "Not enough credits" in str(exc):
                stopped_reason = "credits_exhausted"
                break
            raise

        session.refresh(job)
        if _factory_cancel_requested(job):
            processed.append(
                {
                    "index": index,
                    "title": title,
                    "project_id": auto_result.project.project_id,
                    "video_path": auto_result.video_path,
                    "published_jobs": [],
                    "publish_error": "Factory Mode cancelled before publishing.",
                }
            )
            _mark_factory_cancelled(session, job)
            stopped_reason = "cancelled"
            break

        published_jobs: list[str] = []
        publish_error: str | None = None
        try:
            published = publish_to_all_connections(
                session=session,
                current_user=current_user,
                project_id=auto_result.project.project_id,
                message=publish_message,
                title=title,
            )
            published_jobs = [job.job_id for job in published]
        except HTTPException as exc:
            if "No connected social accounts found" in str(exc.detail):
                publish_error = str(exc.detail)
            else:
                raise

        processed.append(
            {
                "index": index,
                "title": title,
                "project_id": auto_result.project.project_id,
                "video_path": auto_result.video_path,
                "published_jobs": published_jobs,
                "publish_error": publish_error,
            }
        )

    return {
        "processed_titles": len(processed),
        "titles": processed,
        "stopped_reason": stopped_reason,
    }


def retry_production(
    *,
    session: Session,
    project: Project,
) -> WorkflowProductionStatusResponse:
    job = _get_project_production_job(session, project)
    if not job:
        raise ValueError("Production job not found")
    if job.status != "failed" or project.workflow_state != "production_failed":
        raise ValueError("Production retry is only available after a failed render")

    transition_project_state(project, "production_ready")
    transition_project_state(project, "production_queued")
    project.final_video_url = None
    job.status = "queued"
    job.attempts = 0
    job.max_attempts = 1
    job.last_error = None
    job.task_id = None
    job.updated_at = utc_now()
    session.add(job)
    session.add(project)
    session.commit()
    session.refresh(project)
    session.refresh(job)
    return production_status(session, project)


def workflow_library(session: Session) -> WorkflowLibraryResponse:
    tenant_id = current_tenant_id()
    characters = list_character_profiles(session)
    projects = session.exec(
        select(Project).where(Project.tenant_id == tenant_id).order_by(Project.updated_at.desc())
    ).all()
    approved_scripts = [project_to_response(project) for project in projects if (project.script_approved or "").strip()]
    videos = [project_to_response(project) for project in projects if (project.final_video_url or "").strip()]
    return WorkflowLibraryResponse(
        characters=[character_to_response(profile) for profile in characters],
        scripts=approved_scripts,
        videos=videos,
    )
