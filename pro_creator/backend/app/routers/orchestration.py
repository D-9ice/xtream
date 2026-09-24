from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.auth import get_current_user
from app.config import ENABLE_CELERY, FACTORY_MODE_ENABLED
from app.database import engine, get_session
from app.models import OrchestrationJob, OrchestrationSchedule, User
from app.schemas import (
    ExportPresetRequest,
    ExportPresetResponse,
    OrchestrationProcessResponse,
    OrchestrationQueueBatchRequest,
    OrchestrationQueueItem,
    OrchestrationQueueRequest,
    OrchestrationQueueResponse,
    OrchestrationRunnerStatus,
    OrchestrationScheduleItem,
    OrchestrationScheduleRequest,
    OrchestrationScheduleResponse,
)
from app.services.workflow_service import execute_factory_mode_job, execute_workflow_production_job
from app.services.credits import has_owner_mode_access
from app.celery_app import celery_app
from app import tasks as celery_tasks
from app.utils.logger import get_logger
from app.routers.video import export_preset
from app.tenant import current_tenant_id

router = APIRouter(
    prefix="/orchestration",
    tags=["Orchestration"],
    dependencies=[Depends(get_current_user)],
)
logger = get_logger(__name__)

_runner_task: Optional[asyncio.Task] = None
_runner_interval = 15


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _runner_disabled_detail() -> str:
    return (
        "In-process runner is disabled when ENABLE_CELERY=true. "
        "Run a worker and a scheduler/beat instead."
    )


def _job_to_item(job: OrchestrationJob) -> OrchestrationQueueItem:
    payload = _parse_payload(job)
    raw_factory_items = payload.get("factory_items") if isinstance(payload, dict) else None
    factory_items = [item for item in raw_factory_items if isinstance(item, dict)] if isinstance(raw_factory_items, list) else []
    return OrchestrationQueueItem(
        id=job.id or 0,
        project_id=job.project_id,
        kind=job.kind,
        status=job.status,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        last_error=job.last_error,
        task_id=job.task_id,
        factory_items=factory_items,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _schedule_to_item(schedule: OrchestrationSchedule) -> OrchestrationScheduleItem:
    return OrchestrationScheduleItem(
        id=schedule.id or 0,
        project_id=schedule.project_id,
        cadence_days=schedule.cadence_days,
        next_run_at=schedule.next_run_at,
        enabled=schedule.enabled,
        last_run_at=schedule.last_run_at,
        created_at=schedule.created_at,
    )


def _parse_payload(job: OrchestrationJob) -> dict:
    if not job.payload:
        return {}
    try:
        return json.loads(job.payload)
    except json.JSONDecodeError:
        return {}


def _factory_mode_available_for_user(session: Session, user) -> bool:
    if FACTORY_MODE_ENABLED:
        return True
    return bool(user and has_owner_mode_access(session, user))


def _run_export(payload: OrchestrationQueueRequest) -> ExportPresetResponse:
    return export_preset(
        ExportPresetRequest(project_id=payload.project_id, preset=payload.export_preset)
    )


def _execute_job(job: OrchestrationJob, session: Session) -> None:
    payload = _parse_payload(job)
    request = OrchestrationQueueRequest(
        project_id=job.project_id,
        kind=job.kind,
        topic=payload.get("topic"),
        duration_minutes=payload.get("duration_minutes", 3),
        tone=payload.get("tone", "neutral"),
        voice_text=payload.get("voice_text"),
        image_prompt=payload.get("image_prompt"),
        export_preset=payload.get("export_preset", "social-vertical"),
    )

    if job.kind == "export":
        _run_export(request)
    elif job.kind in {"full", "workflow_production"}:
        execute_workflow_production_job(session=session, job=job)
    elif job.kind == "factory_mode":
        user_id = int(payload.get("user_id") or 0)
        current_user = session.get(User, user_id) if user_id else None
        if not _factory_mode_available_for_user(session, current_user):
            raise ValueError("Factory Mode is not enabled for this deployment")
        execute_factory_mode_job(session=session, job=job)
    else:
        raise ValueError(f"Unknown job kind: {job.kind}")


def _dispatch_job(job: OrchestrationJob) -> str:
    payload = _parse_payload(job)
    if job.kind == "export":
        result = celery_tasks.export_preset_task.delay(
            job.project_id,
            payload.get("export_preset") or "youtube",
        )
    elif job.kind in {"full", "workflow_production"}:
        result = celery_tasks.workflow_production_task.delay(job.id or 0)
    elif job.kind == "factory_mode":
        result = celery_tasks.factory_mode_task.delay(job.id or 0)
    else:
        raise ValueError(f"Unknown job kind: {job.kind}")
    return result.id


def _dispatch_persisted_job(session: Session, job: OrchestrationJob) -> None:
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.last_error = "Maximum orchestration attempts reached."
        job.task_id = None
        job.updated_at = utc_now_naive()
        session.add(job)
        session.commit()
        session.refresh(job)
        return

    job.attempts += 1
    job.updated_at = utc_now_naive()
    try:
        job.task_id = _dispatch_job(job)
        job.status = "processing"
        job.last_error = None
    except Exception as exc:
        job.status = "failed"
        job.last_error = f"Celery dispatch failed: {exc}"
        job.task_id = None
    session.add(job)
    session.commit()
    session.refresh(job)


def _process_queue_internal(
    limit: int,
    session: Session,
) -> OrchestrationProcessResponse:
    tenant_id = current_tenant_id()
    if ENABLE_CELERY:
        processing_jobs = session.exec(
            select(OrchestrationJob)
            .where(
                OrchestrationJob.status == "processing",
                OrchestrationJob.tenant_id == tenant_id,
            )
        ).all()
        for job in processing_jobs:
            if not job.task_id:
                continue
            async_result = celery_app.AsyncResult(job.task_id)
            if async_result.ready():
                if async_result.failed():
                    job.status = "failed"
                    job.last_error = str(async_result.result)
                else:
                    job.status = "complete"
                    job.last_error = None
                job.updated_at = utc_now_naive()
                session.add(job)
                session.commit()

    jobs = session.exec(
        select(OrchestrationJob)
        .where(
            OrchestrationJob.status == "queued",
            OrchestrationJob.tenant_id == tenant_id,
        )
        .order_by(OrchestrationJob.created_at.asc())
        .limit(limit)
    ).all()

    completed: list[int] = []
    failed: list[int] = []

    for job in jobs:
        job.status = "running"
        job.attempts += 1
        job.updated_at = utc_now_naive()
        session.add(job)
        session.commit()
        session.refresh(job)
        try:
            if ENABLE_CELERY:
                session.refresh(job)
                if job.status in {"cancelled", "cancel_requested"}:
                    continue
                job.task_id = _dispatch_job(job)
                job.status = "processing"
            else:
                _execute_job(job, session)
                job.status = "complete"
                job.last_error = None
                completed.append(job.id or 0)
        except Exception as exc:
            job.last_error = str(exc)
            if job.attempts >= job.max_attempts:
                job.status = "failed"
                failed.append(job.id or 0)
            else:
                job.status = "queued"
        finally:
            job.updated_at = utc_now_naive()
            session.add(job)
            session.commit()
    return OrchestrationProcessResponse(
        processed=len(jobs), completed=completed, failed=failed
    )


async def _runner_loop(interval_seconds: int) -> None:
    while True:
        try:
            with Session(engine) as session:
                _process_queue_internal(1, session)
        except Exception as exc:
            logger.warning("Runner loop error: %s", exc)
        await asyncio.sleep(interval_seconds)


@router.post("/queue", response_model=OrchestrationQueueItem)
def enqueue_job(
    payload: OrchestrationQueueRequest,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
) -> OrchestrationQueueItem:
    tenant_id = current_tenant_id()
    if payload.kind == "factory_mode" and not _factory_mode_available_for_user(session, current_user):
        raise HTTPException(status_code=400, detail="Factory Mode is not enabled for this deployment")
    job = OrchestrationJob(
        tenant_id=tenant_id,
        user_id=current_user.id,
        project_id=payload.project_id,
        kind=payload.kind,
        status="queued",
        attempts=0,
        max_attempts=3,
        payload=json.dumps(
            {
                "user_id": current_user.id if getattr(current_user, "id", None) is not None else None,
                "topic": payload.topic,
                "duration_minutes": payload.duration_minutes,
                "tone": payload.tone,
                "voice_text": payload.voice_text,
                "image_prompt": payload.image_prompt,
                "export_preset": payload.export_preset,
                "genre": payload.genre,
                "titles": payload.titles,
                "short_description": payload.short_description,
                "start_credits": payload.start_credits,
                "end_credits": payload.end_credits,
                "publish_message": payload.publish_message,
            }
        ),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    if ENABLE_CELERY:
        _dispatch_persisted_job(session, job)
    logger.info("Queued orchestration job %s for %s", job.kind, job.project_id)
    return _job_to_item(job)


@router.post("/queue/batch", response_model=OrchestrationQueueResponse)
def enqueue_batch(
    payload: OrchestrationQueueBatchRequest,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
) -> OrchestrationQueueResponse:
    tenant_id = current_tenant_id()
    items: list[OrchestrationQueueItem] = []
    for entry in payload.items:
        if entry.kind == "factory_mode" and not _factory_mode_available_for_user(session, current_user):
            raise HTTPException(status_code=400, detail="Factory Mode is not enabled for this deployment")
        job = OrchestrationJob(
            tenant_id=tenant_id,
            project_id=entry.project_id,
            kind=entry.kind,
            status="queued",
            attempts=0,
            max_attempts=3,
            payload=json.dumps(
                {
                    "user_id": current_user.id if getattr(current_user, "id", None) is not None else None,
                    "topic": entry.topic,
                    "duration_minutes": entry.duration_minutes,
                    "tone": entry.tone,
                    "voice_text": entry.voice_text,
                    "image_prompt": entry.image_prompt,
                    "export_preset": entry.export_preset,
                    "genre": entry.genre,
                    "titles": entry.titles,
                    "short_description": entry.short_description,
                    "start_credits": entry.start_credits,
                    "end_credits": entry.end_credits,
                    "publish_message": entry.publish_message,
                }
            ),
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        if ENABLE_CELERY:
            _dispatch_persisted_job(session, job)
        items.append(_job_to_item(job))
    return OrchestrationQueueResponse(items=items)


@router.get("/queue", response_model=OrchestrationQueueResponse)
def list_queue(
    status: Optional[str] = Query(None),
    session: Session = Depends(get_session),
) -> OrchestrationQueueResponse:
    tenant_id = current_tenant_id()
    statement = select(OrchestrationJob)
    statement = statement.where(OrchestrationJob.tenant_id == tenant_id)
    if status:
        statement = statement.where(OrchestrationJob.status == status)
    jobs = session.exec(statement.order_by(OrchestrationJob.created_at.desc())).all()
    return OrchestrationQueueResponse(items=[_job_to_item(job) for job in jobs])


@router.post("/queue/process", response_model=OrchestrationProcessResponse)
def process_queue(
    limit: int = Query(1, ge=1, le=10),
    session: Session = Depends(get_session),
) -> OrchestrationProcessResponse:
    return _process_queue_internal(limit, session)


@router.post("/queue/runner/start", response_model=OrchestrationRunnerStatus)
async def start_runner(
    interval_seconds: int = Query(15, ge=5, le=300)
) -> OrchestrationRunnerStatus:
    if ENABLE_CELERY:
        raise HTTPException(
            status_code=400,
            detail=_runner_disabled_detail(),
        )
    global _runner_task, _runner_interval
    _runner_interval = interval_seconds
    if _runner_task is None or _runner_task.done():
        loop = asyncio.get_running_loop()
        _runner_task = loop.create_task(_runner_loop(interval_seconds))
    return OrchestrationRunnerStatus(
        enabled=True,
        running=True,
        interval_seconds=_runner_interval,
    )


@router.post("/queue/runner/stop", response_model=OrchestrationRunnerStatus)
async def stop_runner(
    session: Session = Depends(get_session),
) -> OrchestrationRunnerStatus:
    if ENABLE_CELERY:
        tenant_id = current_tenant_id()
        jobs = session.exec(
            select(OrchestrationJob).where(
                OrchestrationJob.tenant_id == tenant_id,
                OrchestrationJob.kind == "factory_mode",
                OrchestrationJob.status.in_(["queued", "running", "processing", "cancel_requested"]),
            )
        ).all()
        cancelled = 0
        for job in jobs:
            payload = _parse_payload(job)
            payload["cancel_requested"] = True
            job.payload = json.dumps(payload)
            if job.status in {"queued", "running"}:
                job.status = "cancelled"
            else:
                job.status = "cancel_requested"
            job.updated_at = utc_now_naive()
            if job.task_id:
                celery_app.control.revoke(job.task_id, terminate=False)
            session.add(job)
            cancelled += 1
        session.commit()
        return OrchestrationRunnerStatus(
            enabled=True,
            running=False,
            interval_seconds=_runner_interval,
            detail=f"Cancellation requested for {cancelled} Factory Mode job(s).",
        )

    global _runner_task
    if _runner_task is not None:
        _runner_task.cancel()
        _runner_task = None
    return OrchestrationRunnerStatus(
        enabled=True,
        running=False,
        interval_seconds=_runner_interval,
    )


@router.get("/queue/runner/status", response_model=OrchestrationRunnerStatus)
def runner_status() -> OrchestrationRunnerStatus:
    if ENABLE_CELERY:
        return OrchestrationRunnerStatus(
            enabled=False,
            running=False,
            interval_seconds=_runner_interval,
            detail=_runner_disabled_detail(),
        )
    running = _runner_task is not None and not _runner_task.done()
    return OrchestrationRunnerStatus(
        enabled=True,
        running=running,
        interval_seconds=_runner_interval,
    )


@router.post("/queue/{job_id}/cancel", response_model=OrchestrationQueueItem)
def cancel_job(job_id: int, session: Session = Depends(get_session)) -> OrchestrationQueueItem:
    tenant_id = current_tenant_id()
    job = session.get(OrchestrationJob, job_id)
    if not job or job.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in {"complete", "failed", "cancelled"}:
        raise HTTPException(status_code=400, detail=f"Job cannot be cancelled from status {job.status}")

    payload = _parse_payload(job)
    payload["cancel_requested"] = True
    job.payload = json.dumps(payload)
    if job.status in {"queued", "running"}:
        job.status = "cancelled"
    else:
        job.status = "cancel_requested"
    job.updated_at = utc_now_naive()
    if ENABLE_CELERY and job.task_id:
        celery_app.control.revoke(job.task_id, terminate=False)
    session.add(job)
    session.commit()
    session.refresh(job)
    return _job_to_item(job)


@router.post("/queue/{job_id}/retry", response_model=OrchestrationQueueItem)
def retry_job(job_id: int, session: Session = Depends(get_session)) -> OrchestrationQueueItem:
    tenant_id = current_tenant_id()
    job = session.get(OrchestrationJob, job_id)
    if not job or job.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "failed":
        raise HTTPException(status_code=400, detail="Job is not failed")
    job.status = "queued"
    job.last_error = None
    job.task_id = None
    job.updated_at = utc_now_naive()
    session.add(job)
    session.commit()
    session.refresh(job)
    if ENABLE_CELERY:
        _dispatch_persisted_job(session, job)
    return _job_to_item(job)


@router.post("/schedules", response_model=OrchestrationScheduleItem)
def create_schedule(
    payload: OrchestrationScheduleRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OrchestrationScheduleItem:
    tenant_id = current_tenant_id()
    schedule = OrchestrationSchedule(
        tenant_id=tenant_id,
        user_id=current_user.id,
        project_id=payload.project_id,
        cadence_days=payload.cadence_days,
        next_run_at=utc_now_naive() + timedelta(days=payload.cadence_days),
        enabled=True,
    )
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return _schedule_to_item(schedule)


@router.get("/schedules", response_model=OrchestrationScheduleResponse)
def list_schedules(session: Session = Depends(get_session)) -> OrchestrationScheduleResponse:
    tenant_id = current_tenant_id()
    schedules = session.exec(
        select(OrchestrationSchedule)
        .where(OrchestrationSchedule.tenant_id == tenant_id)
        .order_by(OrchestrationSchedule.created_at.desc())
    ).all()
    return OrchestrationScheduleResponse(
        items=[_schedule_to_item(schedule) for schedule in schedules]
    )


@router.post("/schedules/run", response_model=OrchestrationScheduleResponse)
def run_schedules(
    session: Session = Depends(get_session),
) -> OrchestrationScheduleResponse:
    tenant_id = current_tenant_id()
    now = utc_now_naive()
    schedules = session.exec(
        select(OrchestrationSchedule).where(OrchestrationSchedule.tenant_id == tenant_id)
    ).all()
    for schedule in schedules:
        if schedule.enabled and schedule.next_run_at <= now:
            if not schedule.user_id:
                schedule.enabled = False
                session.add(schedule)
                continue
            job = OrchestrationJob(
                tenant_id=tenant_id,
                project_id=schedule.project_id,
                kind="workflow_production",
                status="queued",
                payload=json.dumps(
                    {
                        "user_id": schedule.user_id,
                        "export_preset": "social-vertical",
                        "schedule_id": schedule.id,
                        "scheduled_for": schedule.next_run_at.isoformat(),
                    }
                ),
            )
            session.add(job)
            schedule.last_run_at = now
            schedule.next_run_at = now + timedelta(days=schedule.cadence_days)
            session.add(schedule)
    session.commit()
    return OrchestrationScheduleResponse(
        items=[_schedule_to_item(item) for item in schedules]
    )
