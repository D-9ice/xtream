from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import get_current_user
from app.config import CREDITS_COST_IMAGE_GENERATE
from app.database import get_session
from app.models import Scene, User
from app.schemas import ImageRequest, ImageResponse
from app.services.credits import consume_credits
from app.services.image_engine import generate_image_for_scene
from app.services.provider_routing import resolve_image_provider
from app.tenant import current_tenant_id
from app.utils.logger import get_logger

router = APIRouter(
    prefix="/image",
    tags=["Image"],
    dependencies=[Depends(get_current_user)],
)
logger = get_logger(__name__)


@router.post("/generate", response_model=ImageResponse)
def generate_image_endpoint(
    payload: ImageRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ImageResponse:
    tenant_id = current_tenant_id()
    provider = resolve_image_provider()
    scenes = session.exec(
        select(Scene).where(
            Scene.project_id == payload.project_id,
            Scene.tenant_id == tenant_id,
        )
    ).all()
    try:
        result = generate_image_for_scene(
            payload.project_id,
            1,
            payload.prompt,
            payload.style,
            provider=provider,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image generation failed: {exc}") from exc
    if scenes:
        for scene in scenes:
            try:
                scene_result = generate_image_for_scene(
                    payload.project_id,
                    scene.id or 1,
                    scene.text or payload.prompt,
                    payload.style,
                    provider=provider,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Image generation failed for scene {scene.id or 1}: {exc}",
                ) from exc
            scene.image_path = scene_result["image_path"]
            session.add(scene)
        session.commit()
    consume_credits(
        session=session,
        user=current_user,
        amount=CREDITS_COST_IMAGE_GENERATE,
        reason="image generation",
        action="image.generate",
        reference_id=payload.project_id,
        provider=provider,
        model=payload.style,
        metadata={"scene_count": len(scenes) if scenes else 1},
    )
    logger.info("Generated image for project %s", payload.project_id)
    return ImageResponse(**result)
