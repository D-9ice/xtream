import subprocess
import tempfile
from pathlib import Path
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from app.auth import get_current_user
from app.config import CREDITS_COST_VOICE_GENERATE
from app.database import get_session
from app.models import Scene, User
from app.schemas import (
    CharacterVoiceProfile,
    CharacterVoiceProfileListResponse,
    DialogueRenderRequest,
    DialogueRenderResponse,
    DialogueSceneResult,
    VoiceCloneResponse,
    VoiceProfileDeleteResponse,
    VoiceProfilesResponse,
    VoiceRequest,
    VoiceResponse,
)
from app.services.credits import consume_credits, record_usage_event
from app.services.lipsync_engine import generate_lipsync
from app.services.voice_engine import clone_voice_profile, generate_voice_bytes, generate_voice_for_scene
from app.tenant import current_tenant_id
from app.utils.file_manager import (
    delete_voice_profile,
    delete_character_voice_profile,
    ensure_project_dirs,
    list_voice_profiles,
    read_character_voice_profiles,
    save_voice_profile,
    upsert_character_voice_profile,
    update_voice_profile_metadata,
    write_scene_metadata,
    read_scene_metadata,
)
from app.utils.logger import get_logger

router = APIRouter(
    prefix="/voice",
    tags=["Voice"],
    dependencies=[Depends(get_current_user)],
)
logger = get_logger(__name__)


def _normalize_character_payload(payload: CharacterVoiceProfile) -> dict:
    return {
        "character_id": payload.character_id.strip(),
        "display_name": payload.display_name.strip() or payload.character_id.strip(),
        "voice_profile": payload.voice_profile.strip() or "default",
        "provider": "xai",
        "voice_id": payload.voice_id.strip() if payload.voice_id else None,
    }


def _write_scene_audio_path(project_id: str, scene_id: int, audio_path: str) -> None:
    scenes = read_scene_metadata(project_id)
    if not scenes:
        return
    updated = False
    for scene in scenes:
        try:
            sid = int(scene.get("id"))
        except (TypeError, ValueError):
            continue
        if sid == scene_id:
            scene["audio_path"] = audio_path
            updated = True
            break
    if updated:
        write_scene_metadata(Path(ensure_project_dirs(project_id)), scenes)


def _render_scene_dialogue_audio(
    *,
    project_id: str,
    scene_id: int,
    lines: list,
    character_map: dict[str, dict],
) -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise HTTPException(status_code=400, detail="ffmpeg is required for dialogue rendering.")

    with tempfile.TemporaryDirectory(prefix="pro_creator_dialogue_") as temp_dir:
        temp_path = Path(temp_dir)
        segment_files: list[Path] = []
        item_index = 0
        for line in lines:
            speaker_id = line.speaker_id.strip()
            line_text = line.text.strip()
            if not speaker_id or not line_text:
                continue
            mapped = character_map.get(speaker_id, {})
            voice_profile = line.voice_profile or mapped.get("voice_profile") or "default"
            voice_id = line.voice_id or mapped.get("voice_id")
            audio_bytes, ext, _content_type = generate_voice_bytes(
                project_id=project_id,
                text=line_text,
                voice_profile=voice_profile,
                provider=None,
                override_voice_id=voice_id,
            )
            segment_path = temp_path / f"line_{item_index}.{ext}"
            segment_path.write_bytes(audio_bytes)
            segment_files.append(segment_path)
            item_index += 1
            pause_ms = max(0, int(line.pause_ms))
            if pause_ms > 0:
                pause_path = temp_path / f"pause_{item_index}.wav"
                subprocess.run(
                    [
                        ffmpeg_path,
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "anullsrc=r=22050:cl=mono",
                        "-t",
                        f"{pause_ms/1000:.3f}",
                        str(pause_path),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                segment_files.append(pause_path)
                item_index += 1

        if not segment_files:
            raise HTTPException(status_code=400, detail=f"Scene {scene_id} has no valid dialogue lines.")

        list_path = temp_path / "concat.txt"
        list_path.write_text("\n".join([f"file '{p}'" for p in segment_files]), encoding="utf-8")
        out_path = temp_path / f"scene_{scene_id}.m4a"
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c:a",
                "aac",
                str(out_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        key = f"{project_id}/audio/scene_{scene_id}.m4a"
        from app.storage import storage_client

        storage_client.write_bytes(key, out_path.read_bytes(), content_type="audio/mp4")
        return storage_client.public_url(key)


@router.post("/generate", response_model=VoiceResponse)
def generate_voice_endpoint(
    payload: VoiceRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> VoiceResponse:
    tenant_id = current_tenant_id()
    scenes = session.exec(
        select(Scene).where(
            Scene.project_id == payload.project_id,
            Scene.tenant_id == tenant_id,
        )
    ).all()
    result = generate_voice_for_scene(
        payload.project_id,
        1,
        payload.text,
        payload.voice_profile,
        None,
    )
    if scenes:
        for scene in scenes:
            scene_result = generate_voice_for_scene(
                payload.project_id,
                scene.id or 1,
                scene.text or payload.text,
                payload.voice_profile,
                None,
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
        provider="xai",
        model=payload.voice_profile,
        metadata={"scene_count": len(scenes) if scenes else 1},
    )
    logger.info("Generated voice for project %s", payload.project_id)
    return VoiceResponse(**result)


@router.post("/clone", response_model=VoiceCloneResponse)
async def clone_voice_endpoint(
    project_id: str = Form(...),
    profile_name: str = Form("default"),
    sample: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> VoiceCloneResponse:
    ensure_project_dirs(project_id)
    content = await sample.read()
    profile_path = save_voice_profile(project_id, profile_name, content)
    clone_result = clone_voice_profile(profile_name, content, None)
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
        provider="xai",
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


@router.get("/characters/{project_id}", response_model=CharacterVoiceProfileListResponse)
def list_character_profiles(project_id: str) -> CharacterVoiceProfileListResponse:
    characters = [
        CharacterVoiceProfile(**item)
        for item in read_character_voice_profiles(project_id)
        if isinstance(item, dict)
    ]
    return CharacterVoiceProfileListResponse(characters=characters)


@router.post("/characters/{project_id}", response_model=CharacterVoiceProfileListResponse)
def upsert_character_profile(
    project_id: str,
    payload: CharacterVoiceProfile,
) -> CharacterVoiceProfileListResponse:
    normalized = _normalize_character_payload(payload)
    if not normalized["character_id"]:
        raise HTTPException(status_code=400, detail="character_id is required")
    updated = upsert_character_voice_profile(project_id, normalized)
    return CharacterVoiceProfileListResponse(
        characters=[CharacterVoiceProfile(**item) for item in updated]
    )


@router.delete(
    "/characters/{project_id}/{character_id}",
    response_model=CharacterVoiceProfileListResponse,
)
def remove_character_profile(
    project_id: str,
    character_id: str,
) -> CharacterVoiceProfileListResponse:
    updated = delete_character_voice_profile(project_id, character_id)
    return CharacterVoiceProfileListResponse(
        characters=[CharacterVoiceProfile(**item) for item in updated]
    )


@router.post("/dialogue/render", response_model=DialogueRenderResponse)
def render_dialogue(
    payload: DialogueRenderRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DialogueRenderResponse:
    character_map = {
        str(item.get("character_id", "")).strip(): item
        for item in read_character_voice_profiles(payload.project_id)
        if isinstance(item, dict)
    }
    scene_results: list[DialogueSceneResult] = []
    for scene in payload.scenes:
        audio_path = _render_scene_dialogue_audio(
            project_id=payload.project_id,
            scene_id=scene.scene_id,
            lines=scene.lines,
            character_map=character_map,
        )
        if payload.write_scene_audio_paths:
            _write_scene_audio_path(payload.project_id, scene.scene_id, audio_path)
        scene_results.append(
            DialogueSceneResult(
                scene_id=scene.scene_id,
                audio_path=audio_path,
                line_count=len(scene.lines),
            )
        )
    consume_credits(
        session=session,
        user=current_user,
        amount=max(CREDITS_COST_VOICE_GENERATE, len(scene_results) * CREDITS_COST_VOICE_GENERATE),
        reason="multi-character dialogue render",
        action="voice.dialogue.render",
        reference_id=payload.project_id,
        provider="xai",
        model="multi-character",
        metadata={"scene_count": len(scene_results)},
    )
    try:
        generate_lipsync(payload.project_id)
    except Exception as exc:
        logger.warning("Lip sync generation after dialogue render failed: %s", exc)
    return DialogueRenderResponse(scenes=scene_results)
