from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.auth import require_admin_dashboard_access, require_owner
from app.database import get_session
from app.models import User
from app.schemas import (
    VisitAnalyticsSummaryResponse,
    VisitEventCreateRequest,
    VisitEventResponse,
)
from app.services.analytics import clear_visits, record_visit, summarize_visits

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def require_analytics_admin(
    current_user: User = Depends(require_owner),
    token_subject: str = Depends(require_admin_dashboard_access),
) -> User:
    if token_subject.strip().lower() != current_user.email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin access token does not match user",
        )
    return current_user


@router.post("/visits", response_model=VisitEventResponse)
def create_visit_event(
    payload: VisitEventCreateRequest,
    session: Session = Depends(get_session),
) -> VisitEventResponse:
    return VisitEventResponse.model_validate(record_visit(session, payload), from_attributes=True)


@router.get(
    "/summary",
    response_model=VisitAnalyticsSummaryResponse,
    dependencies=[Depends(require_analytics_admin)],
)
def get_visit_summary(
    days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session),
) -> VisitAnalyticsSummaryResponse:
    return summarize_visits(session, window_days=days)


@router.delete(
    "/visits",
    dependencies=[Depends(require_analytics_admin)],
)
def reset_visit_analytics(
    session: Session = Depends(get_session),
) -> dict[str, object]:
    deleted_count = clear_visits(session)
    return {"deleted": True, "deleted_count": deleted_count}
