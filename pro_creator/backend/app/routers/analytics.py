from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.auth import require_admin_dashboard_access
from app.database import get_session
from app.schemas import (
    VisitAnalyticsSummaryResponse,
    VisitEventCreateRequest,
    VisitEventResponse,
)
from app.services.analytics import record_visit, summarize_visits

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.post("/visits", response_model=VisitEventResponse)
def create_visit_event(
    payload: VisitEventCreateRequest,
    session: Session = Depends(get_session),
) -> VisitEventResponse:
    return VisitEventResponse.model_validate(record_visit(session, payload), from_attributes=True)


@router.get(
    "/summary",
    response_model=VisitAnalyticsSummaryResponse,
    dependencies=[Depends(require_admin_dashboard_access)],
)
def get_visit_summary(
    days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session),
) -> VisitAnalyticsSummaryResponse:
    return summarize_visits(session, window_days=days)
