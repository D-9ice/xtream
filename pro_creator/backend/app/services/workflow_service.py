from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import CREDITS_COST_IMAGE_GENERATE, CREDITS_COST_SCRIPT_GENERATE, CREDITS_COST_VIDEO_RENDER
from app.models import (
    CharacterProfile,
    OrchestrationJob,
    Project,
    ProjectCharacterPackage,
    ProjectScriptVersion,
    Scene,
    User,
)
from app.schemas import (
    WorkflowCharacterListResponse,
    WorkflowCharacterResponse,
    WorkflowLibraryResponse,
    WorkflowProductionStatusResponse,
    WorkflowProductionSummaryResponse,
    WorkflowProjectResponse,
)
from app.services.credits import consume_credits, get_or_create_subscription
from app.services.image_engine import generate_image_bytes, generate_image_for_scene
from app.services.provider_routing import resolve_script_route
from app.services.script_engine import generate_script
from app.services.video_engine import render_video
from app.services.voice_engine import generate_voice_for_scene
from app.storage import project_key, storage_client
from app.tenant import current_tenant_id
from app.utils.file_manager import (
    ensure_project_dirs,
    write_character_voice_profiles,
    write_scene_metadata,
    write_script,
)

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
    return WorkflowProjectResponse(
        project_id=project.project_id,
        title=project.title,
        topic=project.topic,
        status=project.status,
        idea_prompt=project.idea_prompt,
        genre=project.genre,
        target_duration_minutes=project.target_duration_minutes,
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
        updated_at=project.updated_at,
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


def create_project(
    *,
    session: Session,
    title: str,
    idea_prompt: str | None,
    genre: str | None,
    target_duration_minutes: int,
) -> WorkflowProjectResponse:
    project = Project(
        tenant_id=current_tenant_id(),
        project_id=str(uuid4()),
        title=title.strip(),
        topic=_topic_from_inputs(title, idea_prompt, genre),
        idea_prompt=(idea_prompt or "").strip() or None,
        genre=(genre or "").strip() or None,
        target_duration_minutes=max(1, int(target_duration_minutes or 3)),
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
    genre: str | None = None,
    target_duration_minutes: int | None = None,
) -> WorkflowProjectResponse:
    if title is not None and title.strip():
        project.title = title.strip()
    if idea_prompt is not None:
        project.idea_prompt = idea_prompt.strip() or None
    if genre is not None:
        project.genre = genre.strip() or None
    if target_duration_minutes is not None:
        project.target_duration_minutes = max(1, int(target_duration_minutes))
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
        genre=project.genre,
        target_duration_minutes=project.target_duration_minutes,
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

    subscription = get_or_create_subscription(session, current_user)
    script_provider, script_model = resolve_script_route(subscription.plan_name)
    result = generate_script(
        project.topic,
        project.target_duration_minutes,
        tone,
        script_provider=script_provider,
        model_name=script_model,
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
        provider=script_provider,
        model=script_model,
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
    return session.exec(
        select(CharacterProfile)
        .where(CharacterProfile.tenant_id == tenant_id)
        .order_by(CharacterProfile.updated_at.desc())
    ).all()


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
) -> CharacterProfile:
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
    name: str,
    role_type: str,
    description: str,
    filename: str,
    content: bytes,
    voice_profile: str | None,
    lock_identity: bool,
) -> CharacterProfile:
    character_id = str(uuid4())
    suffix = Path(filename or "reference.png").suffix.lower() or ".png"
    content_type = "image/png" if suffix == ".png" else "image/jpeg"
    key = f"_library/characters/{character_id}{suffix}"
    storage_client.write_bytes(key, content, content_type=content_type)
    image_url = storage_client.public_url(key)
    return create_character_profile(
        session=session,
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
    if not project.character_package_approved:
        raise ValueError("Character approval required")
    package = latest_character_package(session, project_id)
    if not package:
        raise ValueError("Approved character package not found")
    snapshot = _loads_json(package.package_snapshot_json)
    if not isinstance(snapshot, list) or not snapshot:
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
    characters = []
    if selected_ids:
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
        characters_ready=bool(project.character_package_approved),
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
        provider="video",
        model="ffmpeg",
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
