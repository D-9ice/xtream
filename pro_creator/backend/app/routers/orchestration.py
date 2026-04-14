from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.auth import get_current_user
from app.config import ENABLE_CELERY, FACTORY_MODE_ENABLED
from app.database import engine, get_session
from app.models import OrchestrationJob, OrchestrationSchedule, Scene, User
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
    ScriptRequest,
    VoiceRequest,
    ImageRequest,
    VideoRequest,
)
from app.services.image_engine import generate_image_for_scene
from app.services.script_engine import generate_script
from app.services.video_engine import render_video
from app.services.voice_engine import generate_voice_bytes, generate_voice_for_scene
from app.services.workflow_service import execute_factory_mode_job, execute_workflow_production_job
from app.services.credits import has_owner_mode_access
from app.celery_app import celery_app
from app import tasks as celery_tasks
from app.utils.file_manager import (
    ensure_project_dirs,
    read_character_voice_profiles,
    write_scene_metadata,
    write_script,
)
from app.utils.logger import get_logger
from app.routers.video import export_preset
from app.tenant import current_tenant_id
from app.storage import storage_client

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
    return OrchestrationQueueItem(
        id=job.id or 0,
        project_id=job.project_id,
        kind=job.kind,
        status=job.status,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        last_error=job.last_error,
        task_id=job.task_id,
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


def _run_script(payload: OrchestrationQueueRequest, session: Session) -> None:
    tenant_id = current_tenant_id()
    result = generate_script(
        payload.topic or "Untitled",
        payload.duration_minutes,
        payload.tone,
        genre=payload.genre,
    )
    project_path = ensure_project_dirs(payload.project_id)
    write_script(project_path, result["full_script"])
    write_scene_metadata(project_path, result["scenes"])

    session.exec(
        Scene.__table__.delete().where(
            Scene.project_id == payload.project_id,
            Scene.tenant_id == tenant_id,
        )
    )
    for scene in result["scenes"]:
        session.add(Scene(tenant_id=tenant_id, project_id=payload.project_id, text=scene["text"]))
    session.commit()


def _extract_dialogue_lines(scene_text: str) -> list[tuple[str, str]]:
    dialogue: list[tuple[str, str]] = []
    for raw_line in (scene_text or "").splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        if line.lower().startswith(("scene ", "intent:", "narration:", "visuals:")):
            continue
        speaker, text = line.split(":", 1)
        speaker = speaker.strip()
        text = text.strip()
        if not speaker or not text:
            continue
        # Avoid treating long descriptive labels as speakers.
        if len(speaker) > 24 or re.search(r"\s{2,}", speaker):
            continue
        dialogue.append((speaker, text))
    return dialogue


def _render_dialogue_scene(
    *,
    project_id: str,
    scene_id: int,
    dialogue: list[tuple[str, str]],
) -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise HTTPException(status_code=400, detail="ffmpeg is required for dialogue rendering.")

    character_map = {
        str(item.get("character_id", "")).strip(): item
        for item in read_character_voice_profiles(project_id)
        if isinstance(item, dict)
    }

    with tempfile.TemporaryDirectory(prefix="pro_creator_orch_dialogue_") as temp_dir:
        temp_path = Path(temp_dir)
        parts: list[Path] = []
        idx = 0
        for speaker, text in dialogue:
            mapped = character_map.get(speaker, {})
            audio_bytes, ext, content_type = generate_voice_bytes(
                project_id=project_id,
                text=text,
                voice_profile=mapped.get("voice_profile") or "default",
                provider=None,
                override_voice_id=mapped.get("voice_id"),
            )
            seg_path = temp_path / f"seg_{idx}.{ext}"
            seg_path.write_bytes(audio_bytes)
            parts.append(seg_path)
            idx += 1
            pause_path = temp_path / f"pause_{idx}.wav"
            subprocess.run(
                [
                    ffmpeg_path,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=22050:cl=mono",
                    "-t",
                    "0.20",
                    str(pause_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            parts.append(pause_path)
            idx += 1

        concat_path = temp_path / "concat.txt"
        concat_path.write_text("\n".join([f"file '{p}'" for p in parts]), encoding="utf-8")
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
                str(concat_path),
                "-c:a",
                "aac",
                str(out_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        key = f"{project_id}/audio/scene_{scene_id}.m4a"
        storage_client.write_bytes(key, out_path.read_bytes(), content_type="audio/mp4")
        return storage_client.public_url(key)


def _run_voice(payload: OrchestrationQueueRequest, session: Session) -> None:
    tenant_id = current_tenant_id()
    scenes = session.exec(
        select(Scene).where(
            Scene.project_id == payload.project_id,
            Scene.tenant_id == tenant_id,
        )
    ).all()
    text = payload.voice_text or (scenes[0].text if scenes else "Provide a concise narration for this project.")
    result = generate_voice_for_scene(payload.project_id, 1, text)
    if scenes:
        for scene in scenes:
            scene_id = scene.id or 1
            scene_text = scene.text or text
            dialogue = _extract_dialogue_lines(scene_text)
            if len(dialogue) >= 2 and len({speaker.lower() for speaker, _ in dialogue}) >= 2:
                scene.audio_path = _render_dialogue_scene(
                    project_id=payload.project_id,
                    scene_id=scene_id,
                    dialogue=dialogue,
                )
            else:
                scene_result = generate_voice_for_scene(
                    payload.project_id,
                    scene_id,
                    scene_text,
                )
                scene.audio_path = scene_result["audio_path"]
            session.add(scene)
        session.commit()
    return result


def _run_image(payload: OrchestrationQueueRequest, session: Session) -> None:
    tenant_id = current_tenant_id()
    scenes = session.exec(
        select(Scene).where(
            Scene.project_id == payload.project_id,
            Scene.tenant_id == tenant_id,
        )
    ).all()
    prompt = payload.image_prompt or (scenes[0].text if scenes else "Scene visual")
    result = generate_image_for_scene(payload.project_id, 1, prompt, "cinematic")
    if scenes:
        for scene in scenes:
            scene_result = generate_image_for_scene(
                payload.project_id,
                scene.id or 1,
                scene.text or prompt,
                "cinematic",
            )
            scene.image_path = scene_result["image_path"]
            session.add(scene)
        session.commit()
    return result


def _run_video(payload: OrchestrationQueueRequest) -> None:
    render_video(payload.project_id)


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

    if job.kind == "script":
        _run_script(request, session)
    elif job.kind == "voice":
        _run_voice(request, session)
    elif job.kind == "image":
        _run_image(request, session)
    elif job.kind == "render":
        _run_video(request)
    elif job.kind == "export":
        _run_export(request)
    elif job.kind == "full":
        _run_script(request, session)
        _run_voice(request, session)
        _run_image(request, session)
        _run_video(request)
        _run_export(request)
    elif job.kind == "workflow_production":
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
    if job.kind == "script":
        result = celery_tasks.generate_script_task.delay(
            job.project_id,
            payload.get("topic") or "",
            payload.get("duration_minutes") or 3,
            payload.get("tone") or "neutral",
        )
    elif job.kind == "voice":
        result = celery_tasks.generate_voice_task.delay(
            job.project_id,
            payload.get("voice_text") or "",
        )
    elif job.kind == "image":
        result = celery_tasks.generate_image_task.delay(
            job.project_id,
            payload.get("image_prompt") or "",
            "cinematic",
        )
    elif job.kind == "render":
        result = celery_tasks.render_video_task.delay(job.project_id)
    elif job.kind == "export":
        result = celery_tasks.export_preset_task.delay(
            job.project_id,
            payload.get("export_preset") or "youtube",
        )
    elif job.kind == "full":
        result = celery_tasks.full_pipeline_task.delay(
            job.project_id,
            payload.get("topic") or "",
            payload.get("duration_minutes") or 3,
            payload.get("tone") or "neutral",
            payload.get("export_preset") or "youtube",
            payload.get("voice_text"),
            payload.get("image_prompt"),
        )
    elif job.kind == "workflow_production":
        result = celery_tasks.workflow_production_task.delay(job.id or 0)
    elif job.kind == "factory_mode":
        result = celery_tasks.factory_mode_task.delay(job.id or 0)
    else:
        raise ValueError(f"Unknown job kind: {job.kind}")
    return result.id


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
async def stop_runner() -> OrchestrationRunnerStatus:
    if ENABLE_CELERY:
        raise HTTPException(status_code=400, detail=_runner_disabled_detail())
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


@router.post("/queue/{job_id}/retry", response_model=OrchestrationQueueItem)
def retry_job(job_id: int, session: Session = Depends(get_session)) -> OrchestrationQueueItem:
    tenant_id = current_tenant_id()
    job = session.get(OrchestrationJob, job_id)
    if not job or job.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "failed":
        raise HTTPException(status_code=400, detail="Job is not failed")
    job.status = "queued"
    job.updated_at = utc_now_naive()
    session.add(job)
    session.commit()
    session.refresh(job)
    return _job_to_item(job)


@router.post("/schedules", response_model=OrchestrationScheduleItem)
def create_schedule(
    payload: OrchestrationScheduleRequest, session: Session = Depends(get_session)
) -> OrchestrationScheduleItem:
    tenant_id = current_tenant_id()
    schedule = OrchestrationSchedule(
        tenant_id=tenant_id,
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
def run_schedules(session: Session = Depends(get_session)) -> OrchestrationScheduleResponse:
    tenant_id = current_tenant_id()
    now = utc_now_naive()
    schedules = session.exec(
        select(OrchestrationSchedule).where(OrchestrationSchedule.tenant_id == tenant_id)
    ).all()
    for schedule in schedules:
        if schedule.enabled and schedule.next_run_at <= now:
            job = OrchestrationJob(
                tenant_id=tenant_id,
                project_id=schedule.project_id,
                kind="full",
                status="queued",
                payload=json.dumps({"export_preset": "social-vertical"}),
            )
            session.add(job)
            schedule.last_run_at = now
            schedule.next_run_at = now + timedelta(days=schedule.cadence_days)
            session.add(schedule)
    session.commit()
    return OrchestrationScheduleResponse(
        items=[_schedule_to_item(item) for item in schedules]
    )
