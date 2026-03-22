from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import CREDITS_COST_IMAGE_GENERATE, CREDITS_COST_SCRIPT_GENERATE, CREDITS_COST_VIDEO_RENDER
from app.models import (
    CharacterProfile,
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
from app.utils.file_manager import ensure_project_dirs, write_scene_metadata, write_script

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


def _project_selected_character_ids(project: Project) -> list[str]:
    return _loads_list(project.selected_character_ids_json)


def _store_project_selected_character_ids(project: Project, selected_character_ids: list[str]) -> None:
    deduped = list(dict.fromkeys([item.strip() for item in selected_character_ids if item.strip()]))
    project.selected_character_ids_json = _dumps_json(deduped)
    project.updated_at = utc_now()


def require_script_approved_for_characters(project: Project) -> None:
    if not (project.script_approved or "").strip():
        raise ValueError("Script approval required before choosing characters")


def _personality_traits(profile: CharacterProfile) -> list[str]:
    parsed = _loads_json(profile.personality_traits_json)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return []


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


def list_projects(session: Session) -> list[WorkflowProjectResponse]:
    tenant_id = current_tenant_id()
    projects = session.exec(
        select(Project).where(Project.tenant_id == tenant_id).order_by(Project.updated_at.desc())
    ).all()
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
    _set_project_state(project, "script_generating")
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
    _set_project_state(project, "script_generated")
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
    _set_project_state(project, "script_generated")
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
    _set_project_state(project, "script_approved")
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
    canonical_image_url: str | None,
    visual_prompt_base: str | None,
    negative_prompt_base: str | None,
    lock_identity: bool,
) -> CharacterProfile:
    clean_name = _validate_character_name(name)
    clean_description = description.strip()
    visual, negative = _build_character_prompts(clean_name, role_type, clean_description)
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
        reference_image_url=(reference_image_url or "").strip() or None,
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
    if WORKFLOW_STAGE_ORDER.get(project.workflow_state, 0) < WORKFLOW_STAGE_ORDER["characters_in_progress"]:
        _set_project_state(project, "characters_in_progress")
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
        lock_identity=True,
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
        canonical_image_url=image_url,
        visual_prompt_base=None,
        negative_prompt_base=None,
        lock_identity=True,
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
    _set_project_state(project, "characters_approved")
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
    return {
        "project_id": project_id,
        "script": project.script_approved,
        "characters": snapshot,
        "references": {
            item.get("character_id"): item.get("reference_image_url")
            for item in snapshot
            if isinstance(item, dict)
        },
        "seeds": {
            item.get("character_id"): item.get("consistency_seed")
            for item in snapshot
            if isinstance(item, dict)
        },
        "prompts": prompts,
    }


def _audio_exists(project_id: str, scene_id: int) -> bool:
    return any(
        storage_client.exists(project_key(project_id, f"audio/scene_{scene_id}.{ext}"))
        for ext in VOICE_EXTENSIONS
    )


def _image_exists(project_id: str, scene_id: int) -> bool:
    return storage_client.exists(project_key(project_id, f"images/scene_{scene_id}.png"))


def _scene_prompt(scene_text: str, bundle: dict[str, Any]) -> str:
    cast = []
    for character in bundle.get("characters", []):
        if not isinstance(character, dict):
            continue
        name = str(character.get("name", "")).strip()
        visual = str(character.get("visual_prompt_base", "")).strip()
        if name or visual:
            cast.append(f"{name}: {visual}".strip(": "))
    cast_text = "; ".join(cast[:4])
    if cast_text:
        return f"{scene_text}\n\nCharacter direction: {cast_text}"
    return scene_text


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


def production_status(project: Project) -> WorkflowProductionStatusResponse:
    return WorkflowProductionStatusResponse(
        project_id=project.project_id,
        workflow_state=project.workflow_state,
        production_job_id=project.production_job_id,
        final_video_url=project.final_video_url,
    )


def _write_production_bundle_artifact(project_id: str, bundle: dict[str, Any]) -> None:
    key = project_key(project_id, "workflow/approved_production_bundle.json")
    storage_client.write_text(key, _dumps_json(bundle))


def start_production(
    *,
    session: Session,
    project: Project,
    current_user: User,
) -> tuple[WorkflowProjectResponse, WorkflowProductionStatusResponse, str | None]:
    bundle = resolve_approved_production_package(session, project.project_id)
    summary = workflow_production_summary(session=session, project=project, current_user=current_user)
    if not summary.script_ready:
        raise ValueError("Script approval required")
    if not summary.characters_ready:
        raise ValueError("Character approval required")
    if summary.current_credit_balance < summary.estimated_credits:
        raise ValueError("Not enough credits to start production")

    project.production_job_id = str(uuid4())
    _set_project_state(project, "production_running")
    session.add(project)
    session.commit()

    try:
        approved_script = str(bundle["script"]).strip() or "(empty script)"
        scenes = _scenes_from_script(approved_script)
        _persist_project_script(session=session, project=project, script_text=approved_script, scenes=scenes)
        _write_production_bundle_artifact(project.project_id, bundle)
        for scene in scenes:
            scene_id = int(scene.get("id", 1))
            scene_text = str(scene.get("text", "")).strip() or project.title
            if not _image_exists(project.project_id, scene_id):
                generate_image_for_scene(
                    project.project_id,
                    scene_id,
                    _scene_prompt(scene_text, bundle),
                    "cinematic",
                )
            if not _audio_exists(project.project_id, scene_id):
                generate_voice_for_scene(project.project_id, scene_id, scene_text, voice_profile="default")
        video_result = render_video(project.project_id)
        project.final_video_url = video_result["video_path"]
        _set_project_state(project, "video_completed")
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
        return project_to_response(project), production_status(project), video_result.get("video_path")
    except Exception:
        _set_project_state(project, "production_failed")
        session.add(project)
        session.commit()
        session.refresh(project)
        raise


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
