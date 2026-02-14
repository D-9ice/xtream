from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlmodel import Session, select

from app.auth import get_current_user
from app.config import CREDITS_COST_VOICE_GENERATE
from app.database import get_session
from app.models import Scene, User
from app.schemas import (
    VoiceCloneResponse,
    VoiceProfileDeleteResponse,
    VoiceProfilesResponse,
    VoiceRequest,
    VoiceResponse,
)
from app.services.credits import consume_credits, record_usage_event
from app.services.lipsync_engine import generate_lipsync
from app.services.provider_routing import resolve_voice_provider
from app.services.voice_engine import clone_voice_profile, generate_voice_for_scene
from app.utils.file_manager import (
    delete_voice_profile,
    ensure_project_dirs,
    list_voice_profiles,
    save_voice_profile,
    update_voice_profile_metadata,
)
from app.utils.logger import get_logger

router = APIRouter(
    prefix="/voice",
    tags=["Voice"],
    dependencies=[Depends(get_current_user)],
)
logger = get_logger(__name__)


@router.post("/generate", response_model=VoiceResponse)
def generate_voice_endpoint(
    payload: VoiceRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> VoiceResponse:
    provider = resolve_voice_provider(payload.tts_provider)
    scenes = session.exec(
        select(Scene).where(Scene.project_id == payload.project_id)
    ).all()
    result = generate_voice_for_scene(
        payload.project_id,
        1,
        payload.text,
        payload.voice_profile,
        provider,
    )
    if scenes:
        for scene in scenes:
            scene_result = generate_voice_for_scene(
                payload.project_id,
                scene.id or 1,
                scene.text or payload.text,
                payload.voice_profile,
                provider,
            )
            scene.audio_path = scene_result["audio_path"]
            session.add(scene)
        session.commit()
    try:
        generate_lipsync(payload.project_id)
    except Exception as exc:
        logger.warning("Lip sync generation failed: %s", exc)
    consume_credits(
        session=session,
        user=current_user,
        amount=CREDITS_COST_VOICE_GENERATE,
        reason="voice generation",
        action="voice.generate",
        reference_id=payload.project_id,
        provider=provider,
        model=payload.voice_profile,
        metadata={"scene_count": len(scenes) if scenes else 1},
    )
    logger.info("Generated voice for project %s", payload.project_id)
    return VoiceResponse(**result)


@router.post("/clone", response_model=VoiceCloneResponse)
async def clone_voice_endpoint(
    project_id: str = Form(...),
    profile_name: str = Form("default"),
    tts_provider: str | None = Form(None),
    sample: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> VoiceCloneResponse:
    ensure_project_dirs(project_id)
    content = await sample.read()
    profile_path = save_voice_profile(project_id, profile_name, content)
    clone_result = clone_voice_profile(profile_name, content, tts_provider)
    update_voice_profile_metadata(
        project_id,
        profile_name,
        {
            "provider": clone_result.get("provider"),
            "voice_id": clone_result.get("voice_id"),
            "sample_key": f"{project_id}/voice_profiles/{profile_name}.wav",
        },
    )
    record_usage_event(
        session=session,
        user=current_user,
        action="voice.clone",
        reason="voice profile clone",
        reference_id=project_id,
        provider=resolve_voice_provider(tts_provider),
        model=profile_name,
    )
    logger.info("Uploaded voice profile %s for project %s", profile_name, project_id)
    return VoiceCloneResponse(profile_path=str(profile_path))


@router.get("/profiles/{project_id}", response_model=VoiceProfilesResponse)
def list_voice_profiles_endpoint(project_id: str) -> VoiceProfilesResponse:
    profiles = list_voice_profiles(project_id)
    return VoiceProfilesResponse(profiles=profiles)


@router.delete("/profiles/{project_id}/{profile_name}", response_model=VoiceProfileDeleteResponse)
def delete_voice_profile_endpoint(project_id: str, profile_name: str) -> VoiceProfileDeleteResponse:
    deleted = delete_voice_profile(project_id, profile_name)
    return VoiceProfileDeleteResponse(deleted=deleted)
