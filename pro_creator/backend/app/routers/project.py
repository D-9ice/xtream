from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
import tempfile
import zipfile
from pathlib import Path
from sqlmodel import Session, select
from uuid import uuid4

from app.auth import get_current_user, require_role
from app.database import get_session
from app.models import Clip, OrchestrationJob, OrchestrationSchedule, Project, Scene
from app.schemas import (
    ProjectBulkDeleteResponse,
    ProjectCreateRequest,
    ProjectDeleteResponse,
    ProjectPurgeRequest,
    ProjectPurgeResponse,
    ProjectResponse,
    SceneResponse,
)
from app.storage import storage_client
from app.tenant import current_tenant_id
from app.utils.file_manager import (
    delete_project_dir,
    ensure_project_dirs,
    project_has_assets,
    read_scene_metadata,
    read_script,
)
from app.utils.logger import get_logger

router = APIRouter(
    prefix="/project",
    tags=["Project"],
    dependencies=[Depends(get_current_user)],
)
logger = get_logger(__name__)


@router.post("/create", response_model=ProjectResponse)
def create_project(
    payload: ProjectCreateRequest, session: Session = Depends(get_session)
) -> ProjectResponse:
    tenant_id = current_tenant_id()
    project_id = str(uuid4())
    ensure_project_dirs(project_id)

    project = Project(
        tenant_id=tenant_id,
        project_id=project_id,
        title=payload.title,
        topic=payload.topic,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    logger.info("Created project %s", project_id)
    return ProjectResponse(
        project_id=project.project_id,
        title=project.title,
        topic=project.topic,
        status=project.status,
        created_at=project.created_at,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, session: Session = Depends(get_session)) -> ProjectResponse:
    tenant_id = current_tenant_id()
    statement = select(Project).where(
        Project.project_id == project_id,
        Project.tenant_id == tenant_id,
    )
    project = session.exec(statement).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse(
        project_id=project.project_id,
        title=project.title,
        topic=project.topic,
        status=project.status,
        created_at=project.created_at,
    )


@router.get("/", response_model=list[ProjectResponse])
def list_projects(session: Session = Depends(get_session)) -> list[ProjectResponse]:
    tenant_id = current_tenant_id()
    projects = session.exec(select(Project).where(Project.tenant_id == tenant_id)).all()
    return [
        ProjectResponse(
            project_id=project.project_id,
            title=project.title,
            topic=project.topic,
            status=project.status,
            created_at=project.created_at,
        )
        for project in projects
    ]


@router.get("/{project_id}/script")
def get_project_script(project_id: str) -> dict:
    return {"script": read_script(project_id)}


@router.get("/{project_id}/scenes", response_model=list[SceneResponse])
def get_project_scenes(
    project_id: str, session: Session = Depends(get_session)
) -> list[SceneResponse]:
    tenant_id = current_tenant_id()
    statement = select(Scene).where(
        Scene.project_id == project_id,
        Scene.tenant_id == tenant_id,
    )
    scenes = session.exec(statement).all()
    if scenes:
        return [
            SceneResponse(
                id=scene.id or idx + 1,
                text=scene.text,
                image_path=scene.image_path,
                audio_path=scene.audio_path,
            )
            for idx, scene in enumerate(scenes)
        ]
    metadata = read_scene_metadata(project_id)
    return [
        SceneResponse(
            id=scene.get("id", idx + 1),
            text=scene.get("text", ""),
            image_path=scene.get("image_path"),
            audio_path=scene.get("audio_path"),
        )
        for idx, scene in enumerate(metadata)
    ]


@router.get("/{project_id}/bundle")
def download_project_bundle(project_id: str) -> FileResponse:
    project_dir = ensure_project_dirs(project_id)
    if storage_client.backend == "local" and not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    temp_dir = tempfile.mkdtemp(prefix=f"pro_creator_{project_id}_")
    bundle_path = Path(temp_dir) / f"{project_id}_bundle.zip"

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as archive:
        if storage_client.backend == "s3":
            prefix = f"{project_id}/"
            for key in storage_client.list_keys(prefix):
                relative_name = key.replace(prefix, "", 1)
                content = storage_client.read_bytes(key)
                archive.writestr(relative_name, content)
        else:
            for path in project_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(project_dir))

    return FileResponse(
        path=bundle_path,
        filename=f"{project_id}_bundle.zip",
        media_type="application/zip",
    )


@router.delete("/{project_id}", response_model=ProjectDeleteResponse)
def delete_project(project_id: str, session: Session = Depends(get_session)) -> ProjectDeleteResponse:
    tenant_id = current_tenant_id()
    statement = select(Project).where(
        Project.project_id == project_id,
        Project.tenant_id == tenant_id,
    )
    project = session.exec(statement).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    session.exec(
        Scene.__table__.delete().where(
            Scene.project_id == project_id,
            Scene.tenant_id == tenant_id,
        )
    )
    # Delete any related editor/orchestration rows (these tables don't have DB-level cascades).
    session.exec(
        Clip.__table__.delete().where(
            Clip.project_id == project_id,
            Clip.tenant_id == tenant_id,
        )
    )
    session.exec(
        OrchestrationJob.__table__.delete().where(
            OrchestrationJob.project_id == project_id,
            OrchestrationJob.tenant_id == tenant_id,
        )
    )
    session.exec(
        OrchestrationSchedule.__table__.delete().where(
            OrchestrationSchedule.project_id == project_id,
            OrchestrationSchedule.tenant_id == tenant_id,
        )
    )
    session.delete(project)
    session.commit()
    delete_project_dir(project_id)
    logger.info("Deleted project %s", project_id)
    return ProjectDeleteResponse(deleted=True)


@router.delete("/", response_model=ProjectBulkDeleteResponse)
def delete_all_projects(
    session: Session = Depends(get_session),
    _: object = Depends(require_role("admin")),
) -> ProjectBulkDeleteResponse:
    tenant_id = current_tenant_id()
    projects = session.exec(select(Project).where(Project.tenant_id == tenant_id)).all()
    deleted_ids = [project.project_id for project in projects]
    if deleted_ids:
        session.exec(Scene.__table__.delete().where(Scene.tenant_id == tenant_id))
        session.exec(Clip.__table__.delete().where(Clip.tenant_id == tenant_id))
        session.exec(OrchestrationJob.__table__.delete().where(OrchestrationJob.tenant_id == tenant_id))
        session.exec(OrchestrationSchedule.__table__.delete().where(OrchestrationSchedule.tenant_id == tenant_id))
        session.exec(Project.__table__.delete().where(Project.tenant_id == tenant_id))
        session.commit()
        for project_id in deleted_ids:
            delete_project_dir(project_id)
    logger.info("Deleted %s projects", len(deleted_ids))
    return ProjectBulkDeleteResponse(deleted_count=len(deleted_ids), deleted_ids=deleted_ids)


@router.post("/purge", response_model=ProjectPurgeResponse)
def purge_stale_projects(
    payload: ProjectPurgeRequest,
    session: Session = Depends(get_session),
    _: object = Depends(require_role("admin")),
) -> ProjectPurgeResponse:
    tenant_id = current_tenant_id()
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=payload.min_age_days)
    projects = session.exec(select(Project).where(Project.tenant_id == tenant_id)).all()
    stale_ids: list[str] = []
    for project in projects:
        if project.created_at <= cutoff and not project_has_assets(project.project_id):
            stale_ids.append(project.project_id)

    if stale_ids:
        session.exec(
            Scene.__table__.delete().where(
                Scene.tenant_id == tenant_id,
                Scene.project_id.in_(stale_ids),
            )
        )
        session.exec(
            Clip.__table__.delete().where(
                Clip.tenant_id == tenant_id,
                Clip.project_id.in_(stale_ids),
            )
        )
        session.exec(
            OrchestrationJob.__table__.delete().where(
                OrchestrationJob.tenant_id == tenant_id,
                OrchestrationJob.project_id.in_(stale_ids),
            )
        )
        session.exec(
            OrchestrationSchedule.__table__.delete().where(
                OrchestrationSchedule.tenant_id == tenant_id,
                OrchestrationSchedule.project_id.in_(stale_ids),
            )
        )
        session.exec(
            Project.__table__.delete().where(
                Project.tenant_id == tenant_id,
                Project.project_id.in_(stale_ids),
            )
        )
        session.commit()
        for project_id in stale_ids:
            delete_project_dir(project_id)
    logger.info("Purged %s stale projects", len(stale_ids))
    return ProjectPurgeResponse(deleted_count=len(stale_ids), deleted_ids=stale_ids)
