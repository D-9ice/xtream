from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models import CommunityPost, User
from app.schemas import CommunityPostCreateRequest, CommunityPostListResponse, CommunityPostResponse
from app.tenant import current_tenant_id

router = APIRouter(
    prefix="/community",
    tags=["Community"],
    dependencies=[Depends(get_current_user)],
)


def _author_label(user: User) -> str:
    local_part = user.email.split("@", 1)[0].strip()
    return local_part.replace(".", " ").replace("_", " ").title() or user.email


def _post_to_response(post: CommunityPost) -> CommunityPostResponse:
    return CommunityPostResponse(
        post_id=post.post_id,
        subject=post.subject,
        message=post.message,
        author_label=post.author_label,
        author_email=post.author_email,
        applause_count=post.applause_count,
        created_at=post.created_at,
    )


@router.get("/posts", response_model=CommunityPostListResponse)
def list_community_posts(session: Session = Depends(get_session)) -> CommunityPostListResponse:
    items = session.exec(
        select(CommunityPost)
        .where(CommunityPost.tenant_id == current_tenant_id())
        .order_by(CommunityPost.created_at.desc())
        .limit(100)
    ).all()
    return CommunityPostListResponse(items=[_post_to_response(item) for item in items])


@router.post("/posts", response_model=CommunityPostResponse)
def create_community_post(
    payload: CommunityPostCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CommunityPostResponse:
    post = CommunityPost(
        tenant_id=current_tenant_id(),
        user_id=current_user.id or 0,
        subject=payload.subject.strip(),
        message=payload.message.strip(),
        author_label=_author_label(current_user),
        author_email=current_user.email,
    )
    session.add(post)
    session.commit()
    session.refresh(post)
    return _post_to_response(post)


@router.post("/posts/{post_id}/applaud", response_model=CommunityPostResponse)
def applaud_community_post(
    post_id: str,
    session: Session = Depends(get_session),
) -> CommunityPostResponse:
    post = session.exec(
        select(CommunityPost)
        .where(CommunityPost.tenant_id == current_tenant_id())
        .where(CommunityPost.post_id == post_id)
    ).first()
    if post is None:
        raise HTTPException(status_code=404, detail="Community post not found")
    post.applause_count = (post.applause_count or 0) + 1
    session.add(post)
    session.commit()
    session.refresh(post)
    return _post_to_response(post)
