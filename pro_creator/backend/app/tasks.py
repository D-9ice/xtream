from datetime import datetime, timedelta, timezone
import json

from redis import Redis
from redis.exceptions import LockError, RedisError
from sqlmodel import Session, select

from app.celery_app import celery_app
from app.config import REDIS_URL
from app.database import engine
from app.models import OrchestrationJob, OrchestrationSchedule, Project
from app.services.script_engine import generate_script
from app.services.lipsync_engine import generate_lipsync
from app.services.voice_engine import generate_voice_for_scene
from app.services.image_engine import generate_image_for_scene
from app.services.video_engine import render_video
from app.services.workflow_service import execute_factory_mode_job, execute_workflow_production_job
from app.services.metrics import FACTORY_RUN_TOTAL, ORCHESTRATION_JOB_TOTAL
from app.utils.file_manager import ensure_project_dirs, write_scene_metadata, write_script
from app.schemas import ExportPresetRequest
from app.routers.video import export_preset


@celery_app.task(name="pro_creator.generate_script")
def generate_script_task(
    project_id: str,
    topic: str,
    duration_minutes: float,
    tone: str,
    genre: str | None = None,
) -> dict:
    result = generate_script(topic, duration_minutes, tone, genre=genre)
    project_path = ensure_project_dirs(project_id)
    write_script(project_path, result["full_script"])
    write_scene_metadata(project_path, result["scenes"])
    return result


@celery_app.task(name="pro_creator.generate_voice")
def generate_voice_task(project_id: str, text: str, scene_id: int = 1) -> dict:
    result = generate_voice_for_scene(project_id, scene_id, text)
    try:
        generate_lipsync(project_id)
    except Exception as exc:
        return {"warning": f"Lip sync failed: {exc}", **result}
    return result


@celery_app.task(name="pro_creator.generate_image")
def generate_image_task(project_id: str, prompt: str, style: str, scene_id: int = 1) -> dict:
    return generate_image_for_scene(project_id, scene_id, prompt, style)


@celery_app.task(name="pro_creator.render_video")
def render_video_task(project_id: str) -> dict:
    return render_video(project_id)


@celery_app.task(name="pro_creator.export_preset")
def export_preset_task(project_id: str, preset: str) -> dict:
    response = export_preset(ExportPresetRequest(project_id=project_id, preset=preset))
    return {"export_path": response.export_path}


@celery_app.task(name="pro_creator.workflow_production")
def workflow_production_task(job_id: int) -> dict:
    with Session(engine) as session:
        job = session.get(OrchestrationJob, job_id)
        if not job:
            raise ValueError(f"Workflow production job {job_id} not found")
        video_path = execute_workflow_production_job(session=session, job=job)
        return {"video_path": video_path}


@celery_app.task(name="pro_creator.factory_mode")
def factory_mode_task(job_id: int) -> dict:
    with Session(engine) as session:
        job = session.get(OrchestrationJob, job_id)
        if not job:
            raise ValueError(f"Factory mode job {job_id} not found")
        if job.status == "cancelled":
            FACTORY_RUN_TOTAL.labels(status="cancelled").inc()
            return {"processed_titles": 0, "titles": [], "stopped_reason": "cancelled"}
        try:
            result = execute_factory_mode_job(session=session, job=job)
            session.refresh(job)
            if job.status != "cancelled":
                job.status = "complete"
                job.last_error = None
                job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                session.add(job)
                session.commit()
                FACTORY_RUN_TOTAL.labels(status="complete").inc()
            else:
                FACTORY_RUN_TOTAL.labels(status="cancelled").inc()
            return result
        except Exception as exc:
            session.refresh(job)
            if job.status not in {"cancelled", "cancel_requested"}:
                job.status = "failed"
                job.last_error = str(exc)
                job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                session.add(job)
                session.commit()
                FACTORY_RUN_TOTAL.labels(status="failed").inc()
            else:
                FACTORY_RUN_TOTAL.labels(status="cancelled").inc()
            raise


@celery_app.task(name="pro_creator.run_due_schedules")
def run_due_schedules_task() -> dict:
    """Persist and dispatch due scheduled jobs from one Celery Beat authority."""
    lock = Redis.from_url(
        REDIS_URL,
        socket_connect_timeout=2,
        socket_timeout=2,
    ).lock(
        "procreator:scheduler:run_due_schedules",
        timeout=55,
        blocking_timeout=0,
    )
    try:
        acquired = bool(lock.acquire(blocking=False))
    except RedisError as exc:
        raise RuntimeError("Scheduler lock could not be acquired from Redis.") from exc
    if not acquired:
        return {"queued_job_ids": [], "count": 0, "skipped": "scheduler_lock_held"}

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        queued_ids: list[int] = []
        with Session(engine) as session:
            schedules = session.exec(
                select(OrchestrationSchedule).where(
                    OrchestrationSchedule.enabled == True,  # noqa: E712
                    OrchestrationSchedule.next_run_at <= now,
                )
            ).all()
            for schedule in schedules:
                project = session.exec(
                    select(Project).where(
                        Project.project_id == schedule.project_id,
                        Project.tenant_id == schedule.tenant_id,
                    )
                ).first()
                if not project:
                    schedule.enabled = False
                    session.add(schedule)
                    session.commit()
                    continue

                scheduled_for = schedule.next_run_at
                cadence = timedelta(days=max(1, schedule.cadence_days))
                next_run_at = scheduled_for
                while next_run_at <= now:
                    next_run_at += cadence

                if not schedule.user_id:
                    schedule.enabled = False
                    session.add(schedule)
                    session.commit()
                    continue

                job = OrchestrationJob(
                    tenant_id=schedule.tenant_id,
                    project_id=schedule.project_id,
                    kind="workflow_production",
                    status="queued",
                    attempts=0,
                    max_attempts=3,
                    payload=json.dumps(
                        {
                            "user_id": schedule.user_id,
                            "export_preset": "social-vertical",
                            "schedule_id": schedule.id,
                            "scheduled_for": scheduled_for.isoformat(),
                        }
                    ),
                )
                schedule.last_run_at = now
                schedule.next_run_at = next_run_at
                session.add(job)
                session.add(schedule)
                session.commit()
                session.refresh(job)

                try:
                    result = workflow_production_task.delay(job.id or 0)
                except Exception as exc:
                    job.status = "failed"
                    job.last_error = f"Scheduled task dispatch failed: {exc}"
                    job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    session.add(job)
                    session.commit()
                    raise

                job.task_id = result.id
                job.status = "processing"
                job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                session.add(job)
                session.commit()
                queued_ids.append(job.id or 0)
        return {"queued_job_ids": queued_ids, "count": len(queued_ids)}
    finally:
        try:
            lock.release()
        except (LockError, RedisError):
            pass


@celery_app.task(name="pro_creator.reconcile_orchestration_jobs")
def reconcile_orchestration_jobs_task() -> dict:
    completed = 0
    failed = 0
    with Session(engine) as session:
        jobs = session.exec(
            select(OrchestrationJob).where(
                OrchestrationJob.status == "processing",
                OrchestrationJob.task_id.is_not(None),
            )
        ).all()
        for job in jobs:
            result = celery_app.AsyncResult(job.task_id or "")
            if not result.ready():
                continue
            if result.failed():
                job.status = "failed"
                job.last_error = str(result.result)
                ORCHESTRATION_JOB_TOTAL.labels(kind=job.kind, status="failed").inc()
                failed += 1
            else:
                job.status = "complete"
                job.last_error = None
                ORCHESTRATION_JOB_TOTAL.labels(kind=job.kind, status="complete").inc()
                completed += 1
            job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            session.add(job)
        session.commit()
    return {"completed": completed, "failed": failed}
