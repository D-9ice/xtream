from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models import Project, User, UserFeedback
from app.tenant import current_tenant_id
from app.schemas import (
    WorkflowAutoCreateRequest,
    WorkflowAutoCreateResponse,
    ProjectBulkDeleteResponse,
    ProjectDeleteResponse,
    WorkflowCharacterCreateRequest,
    WorkflowCharacterGenerateRequest,
    WorkflowCharacterListResponse,
    WorkflowCharacterSelectRequest,
    WorkflowFeedbackRequest,
    WorkflowFeedbackResponse,
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
    auto_create_project,
    build_character_list_response,
    create_character_profile,
    create_project,
    duplicate_project,
    delete_project,
    delete_projects,
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
from app.services.receipt_email import send_feedback_email

router = APIRouter(
    prefix="/workflow",
    tags=["Workflow"],
    dependencies=[Depends(get_current_user)],
)

api_router = APIRouter(
    prefix="/api",
    tags=["Workflow API"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/projects", response_model=list[WorkflowProjectResponse])
@api_router.get("/projects", response_model=list[WorkflowProjectResponse])
def list_workflow_projects(session: Session = Depends(get_session)) -> list[WorkflowProjectResponse]:
    return list_projects(session)


@router.post("/projects", response_model=WorkflowProjectResponse)
@api_router.post("/projects", response_model=WorkflowProjectResponse)
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


@router.post("/auto-create", response_model=WorkflowAutoCreateResponse)
@api_router.post("/auto-create", response_model=WorkflowAutoCreateResponse)
def workflow_auto_create(
    payload: WorkflowAutoCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowAutoCreateResponse:
    try:
        return auto_create_project(
            session=session,
            current_user=current_user,
            title=payload.title,
            duration_minutes=payload.duration_minutes,
            genre=payload.genre,
            short_description=payload.short_description,
            custom_characters=[character.model_dump() for character in payload.custom_characters],
            start_credits=payload.start_credits,
            end_credits=payload.end_credits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Auto-create failed: {exc}") from exc


@router.get("/projects/{project_id}", response_model=WorkflowProjectResponse)
@api_router.get("/projects/{project_id}", response_model=WorkflowProjectResponse)
def get_workflow_project(
    project_id: str,
    session: Session = Depends(get_session),
) -> WorkflowProjectResponse:
    project = get_project_or_404(session, project_id)
    return project_to_response(project)


@router.patch("/projects/{project_id}", response_model=WorkflowProjectResponse)
@api_router.patch("/projects/{project_id}", response_model=WorkflowProjectResponse)
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
@api_router.post("/projects/{project_id}/archive", response_model=WorkflowProjectResponse)
def workflow_archive_project(
    project_id: str,
    session: Session = Depends(get_session),
) -> WorkflowProjectResponse:
    project = get_project_or_404(session, project_id)
    return archive_project(session=session, project=project)


@router.post("/projects/{project_id}/duplicate", response_model=WorkflowProjectResponse)
@api_router.post("/projects/{project_id}/duplicate", response_model=WorkflowProjectResponse)
def workflow_duplicate_project(
    project_id: str,
    session: Session = Depends(get_session),
) -> WorkflowProjectResponse:
    project = get_project_or_404(session, project_id)
    return duplicate_project(session=session, project=project)


@router.delete("/projects/{project_id}", response_model=ProjectDeleteResponse)
@api_router.delete("/projects/{project_id}", response_model=ProjectDeleteResponse)
def workflow_delete_project(
    project_id: str,
    session: Session = Depends(get_session),
) -> ProjectDeleteResponse:
    project = get_project_or_404(session, project_id)
    delete_project(session=session, project=project)
    return ProjectDeleteResponse(deleted=True)


@router.delete("/projects", response_model=ProjectBulkDeleteResponse)
@api_router.delete("/projects", response_model=ProjectBulkDeleteResponse)
def workflow_delete_all_projects(
    session: Session = Depends(get_session),
) -> ProjectBulkDeleteResponse:
    projects = session.exec(select(Project).where(Project.tenant_id == current_tenant_id())).all()
    deleted_ids = delete_projects(session=session, projects=projects)
    return ProjectBulkDeleteResponse(deleted_count=len(deleted_ids), deleted_ids=deleted_ids)


@router.post("/projects/{project_id}/generate-script", response_model=WorkflowProjectResponse)
@api_router.post("/projects/{project_id}/generate-script", response_model=WorkflowProjectResponse)
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
@api_router.post("/projects/{project_id}/approve-script", response_model=WorkflowProjectResponse)
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
@api_router.post("/projects/{project_id}/regenerate-script", response_model=WorkflowProjectResponse)
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
@api_router.patch("/projects/{project_id}/script", response_model=WorkflowProjectResponse)
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
@api_router.get("/projects/{project_id}/characters", response_model=WorkflowCharacterListResponse)
def workflow_project_characters(
    project_id: str,
    session: Session = Depends(get_session),
) -> WorkflowCharacterListResponse:
    project = get_project_or_404(session, project_id)
    return build_character_list_response(session=session, project=project)


@router.post("/characters/create", response_model=WorkflowLibraryResponse)
@api_router.post("/characters/create", response_model=WorkflowLibraryResponse)
def workflow_create_library_character(
    payload: WorkflowCharacterCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowLibraryResponse:
    create_character_profile(
        session=session,
        current_user=current_user,
        name=payload.name,
        role_type=payload.role_type,
        description=payload.description,
        personality_traits=payload.personality_traits,
        voice_profile=payload.voice_profile,
        reference_image_url=payload.reference_image_url,
        reference_image_urls=payload.reference_image_urls,
        canonical_image_url=payload.canonical_image_url,
        visual_prompt_base=payload.visual_prompt_base,
        negative_prompt_base=payload.negative_prompt_base,
        lock_identity=payload.lock_identity,
    )
    return workflow_library(session)


@router.post("/characters/generate", response_model=WorkflowLibraryResponse)
@api_router.post("/characters/generate", response_model=WorkflowLibraryResponse)
def workflow_generate_library_character(
    payload: WorkflowCharacterGenerateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowLibraryResponse:
    generate_character_profile(
        session=session,
        current_user=current_user,
        name=payload.name,
        role_type=payload.role_type,
        description=payload.description,
        personality_traits=payload.personality_traits,
        voice_profile=payload.voice_profile,
        style=payload.style,
        lock_identity=payload.lock_identity,
    )
    return workflow_library(session)


@router.post("/characters/upload", response_model=WorkflowLibraryResponse)
@api_router.post("/characters/upload", response_model=WorkflowLibraryResponse)
async def workflow_upload_library_character(
    name: str = Form(...),
    role_type: str = Form("supporting"),
    description: str = Form(""),
    voice_profile: str | None = Form(None),
    lock_identity: bool = Form(True),
    reference: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowLibraryResponse:
    content = await reference.read()
    if not content:
        raise HTTPException(status_code=400, detail="Reference upload is empty")
    upload_character_reference(
        session=session,
        current_user=current_user,
        name=name,
        role_type=role_type,
        description=description,
        filename=reference.filename or "reference.png",
        content=content,
        voice_profile=voice_profile,
        lock_identity=lock_identity,
    )
    return workflow_library(session)


@router.post("/projects/{project_id}/characters/select", response_model=WorkflowCharacterListResponse)
@api_router.post("/projects/{project_id}/characters/select", response_model=WorkflowCharacterListResponse)
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
@api_router.post("/projects/{project_id}/characters/create", response_model=WorkflowCharacterListResponse)
def workflow_create_character(
    project_id: str,
    payload: WorkflowCharacterCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowCharacterListResponse:
    project = get_project_or_404(session, project_id)
    try:
        require_script_approved_for_characters(project)
        profile = create_character_profile(
            session=session,
            current_user=current_user,
            name=payload.name,
            role_type=payload.role_type,
            description=payload.description,
            personality_traits=payload.personality_traits,
            voice_profile=payload.voice_profile,
            reference_image_url=payload.reference_image_url,
            reference_image_urls=payload.reference_image_urls,
            canonical_image_url=payload.canonical_image_url,
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
@api_router.post("/projects/{project_id}/characters/generate", response_model=WorkflowCharacterListResponse)
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
            lock_identity=payload.lock_identity,
        )
        if payload.select_after_create:
            selected_ids = build_character_list_response(session=session, project=project).selected_character_ids
            selected_ids.append(profile.character_id)
            return select_characters(session=session, project=project, selected_character_ids=selected_ids)
        return build_character_list_response(session=session, project=project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/characters/upload", response_model=WorkflowCharacterListResponse)
@api_router.post("/projects/{project_id}/characters/upload", response_model=WorkflowCharacterListResponse)
async def workflow_upload_character(
    project_id: str,
    name: str = Form(...),
    role_type: str = Form("supporting"),
    description: str = Form(""),
    voice_profile: str | None = Form(None),
    lock_identity: bool = Form(True),
    select_after_create: bool = Form(True),
    reference: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowCharacterListResponse:
    project = get_project_or_404(session, project_id)
    try:
        require_script_approved_for_characters(project)
        content = await reference.read()
        if not content:
            raise HTTPException(status_code=400, detail="Reference upload is empty")
        profile = upload_character_reference(
            session=session,
            current_user=current_user,
            name=name,
            role_type=role_type,
            description=description,
            filename=reference.filename or "reference.png",
            content=content,
            voice_profile=voice_profile,
            lock_identity=lock_identity,
        )
        if select_after_create:
            selected_ids = build_character_list_response(session=session, project=project).selected_character_ids
            selected_ids.append(profile.character_id)
            return select_characters(session=session, project=project, selected_character_ids=selected_ids)
        return build_character_list_response(session=session, project=project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/approve-characters", response_model=WorkflowCharacterListResponse)
@api_router.post("/projects/{project_id}/approve-characters", response_model=WorkflowCharacterListResponse)
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
@api_router.get("/projects/{project_id}/production-summary", response_model=WorkflowProductionSummaryResponse)
def workflow_get_production_summary(
    project_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowProductionSummaryResponse:
    project = get_project_or_404(session, project_id)
    return workflow_production_summary(session=session, project=project, current_user=current_user)


@router.post("/projects/{project_id}/start-production", response_model=WorkflowProductionStartResponse)
@api_router.post("/projects/{project_id}/start-production", response_model=WorkflowProductionStartResponse)
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
@api_router.get("/projects/{project_id}/production-status", response_model=WorkflowProductionStatusResponse)
def workflow_get_production_status(
    project_id: str,
    session: Session = Depends(get_session),
) -> WorkflowProductionStatusResponse:
    project = get_project_or_404(session, project_id)
    return production_status(session, project)


@router.post("/projects/{project_id}/retry-production", response_model=WorkflowProductionStatusResponse)
@api_router.post("/projects/{project_id}/retry-production", response_model=WorkflowProductionStatusResponse)
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


@router.post("/feedback", response_model=WorkflowFeedbackResponse)
@api_router.post("/feedback", response_model=WorkflowFeedbackResponse)
def workflow_submit_feedback(
    payload: WorkflowFeedbackRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowFeedbackResponse:
    feedback = UserFeedback(
        tenant_id=current_tenant_id(),
        user_id=current_user.id or 0,
        subject=payload.subject.strip(),
        message=payload.message.strip(),
        page=(payload.page or "").strip() or None,
        project_id=(payload.project_id or "").strip() or None,
        developer_email=current_user.email,
    )
    session.add(feedback)
    session.commit()
    session.refresh(feedback)

    email_sent = False
    try:
        email_sent = send_feedback_email(
            sender_email=current_user.email,
            subject=feedback.subject,
            message=feedback.message,
            page=feedback.page,
            project_id=feedback.project_id,
        )
    except Exception:
        email_sent = False

    feedback.email_sent = email_sent
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    return WorkflowFeedbackResponse(
        feedback_id=feedback.feedback_id,
        subject=feedback.subject,
        page=feedback.page,
        project_id=feedback.project_id,
        email_sent=email_sent,
        created_at=feedback.created_at,
    )
