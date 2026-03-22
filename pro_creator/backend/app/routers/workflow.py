from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session
from app.models import User
from app.schemas import (
    WorkflowCharacterCreateRequest,
    WorkflowCharacterGenerateRequest,
    WorkflowCharacterListResponse,
    WorkflowCharacterSelectRequest,
    WorkflowGenerateScriptRequest,
    WorkflowLibraryResponse,
    WorkflowProductionStartResponse,
    WorkflowProductionStatusResponse,
    WorkflowProductionSummaryResponse,
    WorkflowProjectCreateRequest,
    WorkflowProjectResponse,
    WorkflowProjectUpdateRequest,
    WorkflowScriptUpdateRequest,
)
from app.services.workflow_service import (
    approve_character_package,
    approve_script,
    archive_project,
    build_character_list_response,
    create_character_profile,
    create_project,
    duplicate_project,
    generate_character_profile,
    generate_project_script,
    get_project_or_404,
    list_projects,
    production_status,
    project_to_response,
    require_script_approved_for_characters,
    retry_production,
    select_characters,
    start_production,
    update_project_metadata,
    update_script_draft,
    upload_character_reference,
    workflow_library,
    workflow_production_summary,
)

router = APIRouter(
    prefix="/workflow",
    tags=["Workflow"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/projects", response_model=list[WorkflowProjectResponse])
def list_workflow_projects(session: Session = Depends(get_session)) -> list[WorkflowProjectResponse]:
    return list_projects(session)


@router.post("/projects", response_model=WorkflowProjectResponse)
def create_workflow_project(
    payload: WorkflowProjectCreateRequest,
    session: Session = Depends(get_session),
) -> WorkflowProjectResponse:
    return create_project(
        session=session,
        title=payload.title,
        idea_prompt=payload.idea_prompt,
        genre=payload.genre,
        target_duration_minutes=payload.target_duration_minutes,
    )


@router.get("/projects/{project_id}", response_model=WorkflowProjectResponse)
def get_workflow_project(
    project_id: str,
    session: Session = Depends(get_session),
) -> WorkflowProjectResponse:
    project = get_project_or_404(session, project_id)
    return project_to_response(project)


@router.patch("/projects/{project_id}", response_model=WorkflowProjectResponse)
def patch_workflow_project(
    project_id: str,
    payload: WorkflowProjectUpdateRequest,
    session: Session = Depends(get_session),
) -> WorkflowProjectResponse:
    project = get_project_or_404(session, project_id)
    return update_project_metadata(
        session=session,
        project=project,
        title=payload.title,
        idea_prompt=payload.idea_prompt,
        genre=payload.genre,
        target_duration_minutes=payload.target_duration_minutes,
    )


@router.post("/projects/{project_id}/archive", response_model=WorkflowProjectResponse)
def workflow_archive_project(
    project_id: str,
    session: Session = Depends(get_session),
) -> WorkflowProjectResponse:
    project = get_project_or_404(session, project_id)
    return archive_project(session=session, project=project)


@router.post("/projects/{project_id}/duplicate", response_model=WorkflowProjectResponse)
def workflow_duplicate_project(
    project_id: str,
    session: Session = Depends(get_session),
) -> WorkflowProjectResponse:
    project = get_project_or_404(session, project_id)
    return duplicate_project(session=session, project=project)


@router.post("/projects/{project_id}/generate-script", response_model=WorkflowProjectResponse)
def workflow_generate_script(
    project_id: str,
    payload: WorkflowGenerateScriptRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowProjectResponse:
    project = get_project_or_404(session, project_id)
    try:
        return generate_project_script(
            session=session,
            project=project,
            current_user=current_user,
            title=payload.title,
            idea_prompt=payload.idea_prompt,
            genre=payload.genre,
            target_duration_minutes=payload.target_duration_minutes,
            tone=payload.tone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Script generation failed: {exc}") from exc


@router.post("/projects/{project_id}/approve-script", response_model=WorkflowProjectResponse)
def workflow_approve_script(
    project_id: str,
    session: Session = Depends(get_session),
) -> WorkflowProjectResponse:
    project = get_project_or_404(session, project_id)
    try:
        return approve_script(session=session, project=project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/regenerate-script", response_model=WorkflowProjectResponse)
def workflow_regenerate_script(
    project_id: str,
    payload: WorkflowGenerateScriptRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowProjectResponse:
    project = get_project_or_404(session, project_id)
    try:
        return generate_project_script(
            session=session,
            project=project,
            current_user=current_user,
            title=payload.title,
            idea_prompt=payload.idea_prompt,
            genre=payload.genre,
            target_duration_minutes=payload.target_duration_minutes,
            tone=payload.tone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Script regeneration failed: {exc}") from exc


@router.patch("/projects/{project_id}/script", response_model=WorkflowProjectResponse)
def workflow_update_script(
    project_id: str,
    payload: WorkflowScriptUpdateRequest,
    session: Session = Depends(get_session),
) -> WorkflowProjectResponse:
    project = get_project_or_404(session, project_id)
    return update_script_draft(
        session=session,
        project=project,
        script_text=payload.script,
        update_scenes=payload.update_scenes,
    )


@router.get("/projects/{project_id}/characters", response_model=WorkflowCharacterListResponse)
def workflow_project_characters(
    project_id: str,
    session: Session = Depends(get_session),
) -> WorkflowCharacterListResponse:
    project = get_project_or_404(session, project_id)
    return build_character_list_response(session=session, project=project)


@router.post("/projects/{project_id}/characters/select", response_model=WorkflowCharacterListResponse)
def workflow_select_characters(
    project_id: str,
    payload: WorkflowCharacterSelectRequest,
    session: Session = Depends(get_session),
) -> WorkflowCharacterListResponse:
    project = get_project_or_404(session, project_id)
    try:
        return select_characters(
            session=session,
            project=project,
            selected_character_ids=payload.selected_character_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/characters/create", response_model=WorkflowCharacterListResponse)
def workflow_create_character(
    project_id: str,
    payload: WorkflowCharacterCreateRequest,
    session: Session = Depends(get_session),
) -> WorkflowCharacterListResponse:
    project = get_project_or_404(session, project_id)
    try:
        require_script_approved_for_characters(project)
        profile = create_character_profile(
            session=session,
            name=payload.name,
            role_type=payload.role_type,
            description=payload.description,
            personality_traits=payload.personality_traits,
            voice_profile=payload.voice_profile,
            reference_image_url=payload.reference_image_url,
            reference_image_urls=payload.reference_image_urls,
            canonical_image_url=None,
            visual_prompt_base=payload.visual_prompt_base,
            negative_prompt_base=payload.negative_prompt_base,
            lock_identity=payload.lock_identity,
        )
        if payload.select_after_create:
            selected_ids = build_character_list_response(session=session, project=project).selected_character_ids
            selected_ids.append(profile.character_id)
            return select_characters(session=session, project=project, selected_character_ids=selected_ids)
        return build_character_list_response(session=session, project=project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/characters/generate", response_model=WorkflowCharacterListResponse)
def workflow_generate_character(
    project_id: str,
    payload: WorkflowCharacterGenerateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowCharacterListResponse:
    project = get_project_or_404(session, project_id)
    try:
        require_script_approved_for_characters(project)
        profile = generate_character_profile(
            session=session,
            current_user=current_user,
            name=payload.name,
            role_type=payload.role_type,
            description=payload.description,
            personality_traits=payload.personality_traits,
            voice_profile=payload.voice_profile,
            style=payload.style,
        )
        if payload.select_after_create:
            selected_ids = build_character_list_response(session=session, project=project).selected_character_ids
            selected_ids.append(profile.character_id)
            return select_characters(session=session, project=project, selected_character_ids=selected_ids)
        return build_character_list_response(session=session, project=project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/characters/upload", response_model=WorkflowCharacterListResponse)
async def workflow_upload_character(
    project_id: str,
    name: str = Form(...),
    role_type: str = Form("supporting"),
    description: str = Form(""),
    voice_profile: str | None = Form(None),
    select_after_create: bool = Form(True),
    reference: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> WorkflowCharacterListResponse:
    project = get_project_or_404(session, project_id)
    try:
        require_script_approved_for_characters(project)
        content = await reference.read()
        if not content:
            raise HTTPException(status_code=400, detail="Reference upload is empty")
        profile = upload_character_reference(
            session=session,
            name=name,
            role_type=role_type,
            description=description,
            filename=reference.filename or "reference.png",
            content=content,
            voice_profile=voice_profile,
        )
        if select_after_create:
            selected_ids = build_character_list_response(session=session, project=project).selected_character_ids
            selected_ids.append(profile.character_id)
            return select_characters(session=session, project=project, selected_character_ids=selected_ids)
        return build_character_list_response(session=session, project=project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/approve-characters", response_model=WorkflowCharacterListResponse)
def workflow_approve_characters(
    project_id: str,
    payload: WorkflowCharacterSelectRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowCharacterListResponse:
    project = get_project_or_404(session, project_id)
    try:
        return approve_character_package(
            session=session,
            project=project,
            current_user=current_user,
            selected_character_ids=payload.selected_character_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/production-summary", response_model=WorkflowProductionSummaryResponse)
def workflow_get_production_summary(
    project_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowProductionSummaryResponse:
    project = get_project_or_404(session, project_id)
    return workflow_production_summary(session=session, project=project, current_user=current_user)


@router.post("/projects/{project_id}/start-production", response_model=WorkflowProductionStartResponse)
def workflow_start_production(
    project_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowProductionStartResponse:
    project = get_project_or_404(session, project_id)
    try:
        updated_project, status, video_path = start_production(
            session=session,
            project=project,
            current_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Production failed: {exc}") from exc
    return WorkflowProductionStartResponse(
        project=updated_project,
        status=status,
        video_path=video_path,
    )


@router.get("/projects/{project_id}/production-status", response_model=WorkflowProductionStatusResponse)
def workflow_get_production_status(
    project_id: str,
    session: Session = Depends(get_session),
) -> WorkflowProductionStatusResponse:
    project = get_project_or_404(session, project_id)
    return production_status(session, project)


@router.post("/projects/{project_id}/retry-production", response_model=WorkflowProductionStatusResponse)
def workflow_retry_production(
    project_id: str,
    session: Session = Depends(get_session),
) -> WorkflowProductionStatusResponse:
    project = get_project_or_404(session, project_id)
    try:
        return retry_production(session=session, project=project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/library", response_model=WorkflowLibraryResponse)
def workflow_get_library(session: Session = Depends(get_session)) -> WorkflowLibraryResponse:
    return workflow_library(session)
