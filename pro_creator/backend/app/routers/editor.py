from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models import Clip
from app.schemas import ClipCreateRequest, ClipResponse, ClipUpdateRequest
from app.tenant import current_tenant_id

router = APIRouter(
    prefix="/editor",
    tags=["Editor"],
    dependencies=[Depends(get_current_user)],
)


def _to_response(clip: Clip) -> ClipResponse:
    return ClipResponse(
        id=clip.id or 0,
        project_id=clip.project_id,
        title=clip.title,
        start_time=clip.start_time,
        end_time=clip.end_time,
        order_index=clip.order_index,
        source_url=clip.source_url,
        notes=clip.notes,
        created_at=clip.created_at,
    )


@router.get("/{project_id}/clips", response_model=list[ClipResponse])
def list_clips(project_id: str, session: Session = Depends(get_session)) -> list[ClipResponse]:
    tenant_id = current_tenant_id()
    clips = session.exec(
        select(Clip)
        .where(
            Clip.project_id == project_id,
            Clip.tenant_id == tenant_id,
        )
        .order_by(Clip.order_index.asc())
    ).all()
    return [_to_response(clip) for clip in clips]


@router.post("/{project_id}/clips", response_model=ClipResponse)
def create_clip(
    project_id: str,
    payload: ClipCreateRequest,
    session: Session = Depends(get_session),
) -> ClipResponse:
    tenant_id = current_tenant_id()
    clip = Clip(
        tenant_id=tenant_id,
        project_id=project_id,
        title=payload.title,
        start_time=payload.start_time,
        end_time=payload.end_time,
        order_index=payload.order_index,
        source_url=payload.source_url,
        notes=payload.notes,
    )
    session.add(clip)
    session.commit()
    session.refresh(clip)
    return _to_response(clip)


@router.patch("/{project_id}/clips/{clip_id}", response_model=ClipResponse)
def update_clip(
    project_id: str,
    clip_id: int,
    payload: ClipUpdateRequest,
    session: Session = Depends(get_session),
) -> ClipResponse:
    tenant_id = current_tenant_id()
    clip = session.get(Clip, clip_id)
    if not clip or clip.project_id != project_id or clip.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Clip not found")
    data = payload.dict(exclude_unset=True)
    for key, value in data.items():
        setattr(clip, key, value)
    session.add(clip)
    session.commit()
    session.refresh(clip)
    return _to_response(clip)


@router.delete("/{project_id}/clips/{clip_id}")
def delete_clip(
    project_id: str,
    clip_id: int,
    session: Session = Depends(get_session),
) -> dict:
    tenant_id = current_tenant_id()
    clip = session.get(Clip, clip_id)
    if not clip or clip.project_id != project_id or clip.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Clip not found")
    session.delete(clip)
    session.commit()
    return {"deleted": True}
