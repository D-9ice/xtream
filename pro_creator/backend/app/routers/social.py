from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session
from app.routers.billing import require_owner_dashboard_access
from app.models import User
from app.schemas import (
    SocialAccountConnectionListResponse,
    SocialAccountConnectionRequest,
    SocialAccountConnectionResponse,
    SocialDeleteResponse,
    SocialPublishJobListResponse,
    SocialPublishJobResponse,
    SocialPublishRequest,
)
from app.services.social_publish import (
    connection_to_response,
    delete_connection,
    job_to_payload,
    list_connections,
    list_publish_jobs,
    publish_to_all_connections,
    publish_to_connections,
    upsert_connection,
)

router = APIRouter(
    prefix="/social",
    tags=["Social"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/connections", response_model=SocialAccountConnectionListResponse)
def get_social_connections(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> SocialAccountConnectionListResponse:
    return SocialAccountConnectionListResponse(
        items=[connection_to_response(connection) for connection in list_connections(session, current_user)]
    )


@router.post("/connections", response_model=SocialAccountConnectionResponse)
def save_social_connection(
    payload: SocialAccountConnectionRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> SocialAccountConnectionResponse:
    connection = upsert_connection(
        session,
        current_user,
        connection_id=payload.connection_id,
        platform=payload.platform,
        account_label=payload.account_label,
        account_identifier=payload.account_identifier,
        access_token=payload.access_token,
        access_token_secret=payload.access_token_secret,
        refresh_token=payload.refresh_token,
        client_key=payload.client_key,
        client_secret=payload.client_secret,
        token_expires_at=payload.token_expires_at,
        scopes=payload.scopes,
        metadata=payload.metadata,
        enabled=payload.enabled,
    )
    return SocialAccountConnectionResponse(**connection_to_response(connection))


@router.delete("/connections/{connection_id}", response_model=SocialDeleteResponse)
def remove_social_connection(
    connection_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> SocialDeleteResponse:
    delete_connection(session, current_user, connection_id)
    return SocialDeleteResponse(deleted=True)


@router.get("/publish/jobs", response_model=SocialPublishJobListResponse)
def get_publish_jobs(
    project_id: str | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> SocialPublishJobListResponse:
    return SocialPublishJobListResponse(
        items=[SocialPublishJobResponse(**job_to_payload(job)) for job in list_publish_jobs(session, current_user, project_id)]
    )


@router.post("/publish", response_model=SocialPublishJobListResponse)
def publish_social_videos(
    payload: SocialPublishRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> SocialPublishJobListResponse:
    connection_ids = [connection_id for connection_id in payload.connection_ids if connection_id.strip()]
    if connection_ids:
        jobs = publish_to_connections(
            session=session,
            current_user=current_user,
            project_id=payload.project_id,
            connection_ids=connection_ids,
            message=payload.message,
            title=payload.title,
        )
    else:
        jobs = publish_to_all_connections(
            session=session,
            current_user=current_user,
            project_id=payload.project_id,
            message=payload.message,
            title=payload.title,
        )
    return SocialPublishJobListResponse(
        items=[SocialPublishJobResponse(**job_to_payload(job)) for job in jobs]
    )


@router.get(
    "/admin/connections",
    response_model=SocialAccountConnectionListResponse,
    dependencies=[Depends(require_owner_dashboard_access)],
)
def get_admin_social_connections(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_owner_dashboard_access),
) -> SocialAccountConnectionListResponse:
    return SocialAccountConnectionListResponse(
        items=[connection_to_response(connection) for connection in list_connections(session, current_user)]
    )


@router.post(
    "/admin/connections",
    response_model=SocialAccountConnectionResponse,
    dependencies=[Depends(require_owner_dashboard_access)],
)
def save_admin_social_connection(
    payload: SocialAccountConnectionRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_owner_dashboard_access),
) -> SocialAccountConnectionResponse:
    connection = upsert_connection(
        session,
        current_user,
        connection_id=payload.connection_id,
        platform=payload.platform,
        account_label=payload.account_label,
        account_identifier=payload.account_identifier,
        access_token=payload.access_token,
        access_token_secret=payload.access_token_secret,
        refresh_token=payload.refresh_token,
        client_key=payload.client_key,
        client_secret=payload.client_secret,
        token_expires_at=payload.token_expires_at,
        scopes=payload.scopes,
        metadata=payload.metadata,
        enabled=payload.enabled,
    )
    return SocialAccountConnectionResponse(**connection_to_response(connection))


@router.delete(
    "/admin/connections/{connection_id}",
    response_model=SocialDeleteResponse,
    dependencies=[Depends(require_owner_dashboard_access)],
)
def remove_admin_social_connection(
    connection_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_owner_dashboard_access),
) -> SocialDeleteResponse:
    delete_connection(session, current_user, connection_id)
    return SocialDeleteResponse(deleted=True)
