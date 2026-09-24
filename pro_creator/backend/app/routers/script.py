from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import get_current_user
from app.config import CREDITS_COST_SCRIPT_GENERATE, CREDITS_COST_SCRIPT_IMPORT, XAI_TEXT_MODEL
from app.database import get_session
from app.models import Scene, User
from app.schemas import (
    ScriptClearRequest,
    ScriptImportRequest,
    ScriptLiveRequest,
    ScriptRequest,
    ScriptResponse,
    SceneResponse,
)
from app.services.credits import (
    consume_credits,
    record_usage_event,
)
from app.services.script_engine import generate_script
from app.tenant import current_tenant_id
from app.utils.file_manager import (
    clear_script_assets,
    ensure_project_dirs,
    write_scene_metadata,
    write_script,
)
from app.utils.logger import get_logger

router = APIRouter(
    prefix="/script",
    tags=["Script"],
    dependencies=[Depends(get_current_user)],
)
logger = get_logger(__name__)


@router.post("/generate", response_model=ScriptResponse)
def generate_script_endpoint(
    payload: ScriptRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ScriptResponse:
    tenant_id = current_tenant_id()
    try:
        result = generate_script(
            payload.topic,
            payload.duration_minutes,
            payload.tone,
            genre=payload.genre,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Script generation failed: {exc}") from exc
    project_path = ensure_project_dirs(payload.project_id)
    write_script(project_path, result["full_script"])
    write_scene_metadata(project_path, result["scenes"])

    scene_models = []
    for scene in result["scenes"]:
        scene_model = Scene(tenant_id=tenant_id, project_id=payload.project_id, text=scene["text"])
        session.add(scene_model)
        scene_models.append(scene_model)
    session.commit()
    consume_credits(
        session=session,
        user=current_user,
        amount=CREDITS_COST_SCRIPT_GENERATE,
        reason="script generation",
        action="script.generate",
        reference_id=payload.project_id,
        provider="xai",
        model=XAI_TEXT_MODEL,
        metadata={"duration_minutes": payload.duration_minutes, "tone": payload.tone},
    )

    logger.info("Generated script for project %s", payload.project_id)
    return ScriptResponse(
        full_script=result["full_script"],
        scenes=[
            SceneResponse(
                id=scene.id or idx + 1,
                text=scene.text,
                image_path=scene.image_path,
                audio_path=scene.audio_path,
            )
            for idx, scene in enumerate(scene_models)
        ],
    )


@router.post("/import", response_model=ScriptResponse)
def import_script_endpoint(
    payload: ScriptImportRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ScriptResponse:
    tenant_id = current_tenant_id()
    project_path = ensure_project_dirs(payload.project_id)
    script_text = payload.script.strip()
    if not script_text:
        script_text = "(empty script)"
    write_script(project_path, script_text)

    raw_scenes = [line.strip() for line in script_text.splitlines() if line.strip()]
    scenes = [
        {"id": idx + 1, "text": text}
        for idx, text in enumerate(raw_scenes[:20])
    ]
    if not scenes:
        scenes = [{"id": 1, "text": script_text[:200]}]
    write_scene_metadata(project_path, scenes)

    session.exec(
        Scene.__table__.delete().where(
            Scene.project_id == payload.project_id,
            Scene.tenant_id == tenant_id,
        )
    )
    scene_models = []
    for scene in scenes:
        scene_model = Scene(tenant_id=tenant_id, project_id=payload.project_id, text=scene["text"])
        session.add(scene_model)
        scene_models.append(scene_model)
    session.commit()
    consume_credits(
        session=session,
        user=current_user,
        amount=CREDITS_COST_SCRIPT_IMPORT,
        reason="script import",
        action="script.import",
        reference_id=payload.project_id,
        provider="manual",
        model="n/a",
    )

    return ScriptResponse(
        full_script=script_text,
        scenes=[
            SceneResponse(
                id=scene.id or idx + 1,
                text=scene.text,
                image_path=scene.image_path,
                audio_path=scene.audio_path,
            )
            for idx, scene in enumerate(scene_models)
        ],
    )


@router.patch("/live", response_model=ScriptResponse)
def live_script_endpoint(
    payload: ScriptLiveRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ScriptResponse:
    tenant_id = current_tenant_id()
    project_path = ensure_project_dirs(payload.project_id)
    script_text = payload.script.strip() or "(empty script)"
    write_script(project_path, script_text)

    if payload.update_scenes:
        raw_scenes = [line.strip() for line in script_text.splitlines() if line.strip()]
        scenes = [
            {"id": idx + 1, "text": text}
            for idx, text in enumerate(raw_scenes[:20])
        ]
        if not scenes:
            scenes = [{"id": 1, "text": script_text[:200]}]
        write_scene_metadata(project_path, scenes)
        session.exec(
            Scene.__table__.delete().where(
                Scene.project_id == payload.project_id,
                Scene.tenant_id == tenant_id,
            )
        )
        scene_models = []
        for scene in scenes:
            scene_model = Scene(tenant_id=tenant_id, project_id=payload.project_id, text=scene["text"])
            session.add(scene_model)
            scene_models.append(scene_model)
        session.commit()
        record_usage_event(
            session=session,
            user=current_user,
            action="script.live_update",
            reason="live script edit (scene sync)",
            reference_id=payload.project_id,
        )
        return ScriptResponse(
            full_script=script_text,
            scenes=[
                SceneResponse(
                    id=scene.id or idx + 1,
                    text=scene.text,
                    image_path=scene.image_path,
                    audio_path=scene.audio_path,
                )
                for idx, scene in enumerate(scene_models)
            ],
        )
    record_usage_event(
        session=session,
        user=current_user,
        action="script.live_update",
        reason="live script edit",
        reference_id=payload.project_id,
    )

    existing_scenes = session.exec(
        select(Scene).where(
            Scene.project_id == payload.project_id,
            Scene.tenant_id == tenant_id,
        )
    ).all()
    return ScriptResponse(
        full_script=script_text,
        scenes=[
            SceneResponse(
                id=scene.id or idx + 1,
                text=scene.text,
                image_path=scene.image_path,
                audio_path=scene.audio_path,
            )
            for idx, scene in enumerate(existing_scenes)
        ],
    )


@router.post("/clear", response_model=ScriptResponse)
def clear_script_endpoint(
    payload: ScriptClearRequest, session: Session = Depends(get_session)
) -> ScriptResponse:
    tenant_id = current_tenant_id()
    clear_script_assets(payload.project_id)

    session.exec(
        Scene.__table__.delete().where(
            Scene.project_id == payload.project_id,
            Scene.tenant_id == tenant_id,
        )
    )
    session.commit()

    return ScriptResponse(full_script="", scenes=[])
