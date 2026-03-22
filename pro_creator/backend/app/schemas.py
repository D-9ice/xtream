from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ProjectCreateRequest(BaseModel):
    title: str
    topic: str


class ProjectResponse(BaseModel):
    project_id: str
    title: str
    topic: str
    status: str
    created_at: datetime


class ProjectDeleteResponse(BaseModel):
    deleted: bool


class ProjectBulkDeleteResponse(BaseModel):
    deleted_count: int
    deleted_ids: List[str]


class ProjectPurgeRequest(BaseModel):
    min_age_days: int = 7


class ProjectPurgeResponse(BaseModel):
    deleted_count: int
    deleted_ids: List[str]


class SceneResponse(BaseModel):
    id: int
    text: str
    image_path: Optional[str] = None
    audio_path: Optional[str] = None


class ScriptRequest(BaseModel):
    project_id: str
    topic: str
    duration_minutes: float = 3
    tone: str = "neutral"


class ScriptImportRequest(BaseModel):
    project_id: str
    script: str


class ScriptLiveRequest(BaseModel):
    project_id: str
    script: str
    update_scenes: bool = False


class ScriptClearRequest(BaseModel):
    project_id: str


class ScriptResponse(BaseModel):
    full_script: str
    scenes: List[SceneResponse]


class VoiceRequest(BaseModel):
    project_id: str
    text: str
    voice_profile: str = "default"
    tts_provider: Optional[str] = None


class VoiceResponse(BaseModel):
    audio_path: str
    duration_seconds: float


class CharacterVoiceProfile(BaseModel):
    character_id: str
    display_name: str
    voice_profile: str = "default"
    tts_provider: Optional[str] = None
    voice_id: Optional[str] = None


class CharacterVoiceProfileListResponse(BaseModel):
    characters: List[CharacterVoiceProfile]


class DialogueLine(BaseModel):
    speaker_id: str
    text: str
    pause_ms: int = 250
    voice_profile: Optional[str] = None
    tts_provider: Optional[str] = None
    voice_id: Optional[str] = None


class DialogueSceneRequest(BaseModel):
    scene_id: int
    lines: List[DialogueLine]


class DialogueRenderRequest(BaseModel):
    project_id: str
    scenes: List[DialogueSceneRequest]
    default_tts_provider: Optional[str] = None
    write_scene_audio_paths: bool = True


class DialogueSceneResult(BaseModel):
    scene_id: int
    audio_path: str
    line_count: int


class DialogueRenderResponse(BaseModel):
    scenes: List[DialogueSceneResult]


class VoiceCloneResponse(BaseModel):
    profile_path: str


class VoiceProfilesResponse(BaseModel):
    profiles: List[str]


class VoiceProfileDeleteResponse(BaseModel):
    deleted: bool


class ImageRequest(BaseModel):
    project_id: str
    prompt: str
    style: str = "cinematic"


class ImageResponse(BaseModel):
    image_path: str


class VideoRequest(BaseModel):
    project_id: str
    render_provider: str = "ffmpeg"  # ffmpeg | runway_gen4_turbo | runway_gen4_5


class VideoResponse(BaseModel):
    video_path: str


class VideoImportRequest(BaseModel):
    project_id: str
    url: str


class VideoImportResponse(BaseModel):
    video_path: str


class ThumbnailGenerateRequest(BaseModel):
    project_id: str
    mode: str = "classic"  # classic | ai
    title: Optional[str] = None
    subtitle: Optional[str] = None
    ai_prompt: Optional[str] = None
    style: str = "cinematic"
    source: str = "auto"  # auto | video | image
    scene_id: int = 1
    timestamp_seconds: float = 1.0
    variant_count: int = 1
    format: str = "png"  # png | jpg
    width: int = 1280
    height: int = 720


class ThumbnailVariantResponse(BaseModel):
    variant_id: int
    thumbnail_key: str
    thumbnail_path: str
    source_used: str
    width: int
    height: int


class ThumbnailGenerateResponse(BaseModel):
    thumbnail_path: str
    thumbnail_key: str
    mode_used: str
    source_used: str
    width: int
    height: int
    variants: List[ThumbnailVariantResponse] = []


class ThumbnailSetPrimaryRequest(BaseModel):
    project_id: str
    thumbnail_key: str


class ExportPresetRequest(BaseModel):
    project_id: str
    preset: str


class ExportPresetResponse(BaseModel):
    export_path: str


class ExportBatchRequest(BaseModel):
    project_id: str
    presets: List[str]


class ExportBatchResponse(BaseModel):
    exports: List[str]


class ExportStatusEntry(BaseModel):
    preset: str
    status: str
    path: Optional[str] = None
    size_bytes: Optional[int] = None
    updated_at: Optional[datetime] = None


class ExportStatusResponse(BaseModel):
    project_id: str
    exports: List[ExportStatusEntry]


class EditByTextRequest(BaseModel):
    project_id: str
    remove_ranges: List[List[float]]


class EditByTextResponse(BaseModel):
    segments_remaining: int


class FeatureStubResponse(BaseModel):
    status: str
    detail: str


class UserCreateRequest(BaseModel):
    email: str
    password: str
    role: str = "admin"


class UserResponse(BaseModel):
    email: str
    role: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class PasswordChangeResponse(BaseModel):
    status: str


class ClipCreateRequest(BaseModel):
    title: str
    start_time: float = 0.0
    end_time: float = 0.0
    order_index: int = 0
    source_url: Optional[str] = None
    notes: Optional[str] = None


class ClipUpdateRequest(BaseModel):
    title: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    order_index: Optional[int] = None
    source_url: Optional[str] = None
    notes: Optional[str] = None


class ClipResponse(BaseModel):
    id: int
    project_id: str
    title: str
    start_time: float
    end_time: float
    order_index: int
    source_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class OrchestrationQueueRequest(BaseModel):
    project_id: str
    kind: str = "full"
    topic: Optional[str] = None
    duration_minutes: float = 3
    tone: str = "neutral"
    voice_text: Optional[str] = None
    image_prompt: Optional[str] = None
    export_preset: str = "social-vertical"


class OrchestrationQueueItem(BaseModel):
    id: int
    project_id: str
    kind: str
    status: str
    attempts: int
    max_attempts: int
    last_error: Optional[str] = None
    task_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class OrchestrationQueueResponse(BaseModel):
    items: List[OrchestrationQueueItem]


class OrchestrationQueueBatchRequest(BaseModel):
    items: List[OrchestrationQueueRequest]


class OrchestrationProcessResponse(BaseModel):
    processed: int
    completed: List[int]
    failed: List[int]


class OrchestrationRunnerStatus(BaseModel):
    enabled: bool = True
    running: bool
    interval_seconds: int
    detail: Optional[str] = None


class OrchestrationScheduleRequest(BaseModel):
    project_id: str
    cadence_days: int = 1


class OrchestrationScheduleItem(BaseModel):
    id: int
    project_id: str
    cadence_days: int
    next_run_at: datetime
    enabled: bool
    last_run_at: Optional[datetime] = None
    created_at: datetime


class OrchestrationScheduleResponse(BaseModel):
    items: List[OrchestrationScheduleItem]


class CreditBalanceResponse(BaseModel):
    email: str
    plan_name: str
    status: str
    credits_balance: int
    credits_reserved: int = 0
    credits_used_total: int
    renewal_date: Optional[datetime] = None


class CreditsConsumeRequest(BaseModel):
    amount: int
    from_reserved: bool = False
    reason: Optional[str] = None


class CreditsReserveRequest(BaseModel):
    amount: int
    reason: Optional[str] = None


class CreditsRefundRequest(BaseModel):
    amount: int
    to_reserved: bool = False
    reason: Optional[str] = None


class CreditPlan(BaseModel):
    id: str
    name: str
    credits: int
    price_usd: int
    popular: bool = False
    stripe_price_id: Optional[str] = None
    checkout_enabled: bool = False


class CreditPlanListResponse(BaseModel):
    plans: List[CreditPlan]


class CreditsPurchaseRequest(BaseModel):
    plan_id: str


class StripeCheckoutSessionResponse(BaseModel):
    session_id: str
    checkout_url: str


class AdminSubscriptionUpdateRequest(BaseModel):
    plan_name: Optional[str] = None
    status: Optional[str] = None
    credits_delta: Optional[int] = None
    credits_balance: Optional[int] = None
    renewal_date: Optional[datetime] = None


class AdminSubscriptionListResponse(BaseModel):
    items: List[CreditBalanceResponse]


class AdminAccessVerifyRequest(BaseModel):
    password: str
    otp_code: Optional[str] = None


class AdminAccessVerifyResponse(BaseModel):
    access_token: str
    expires_in_seconds: int


class Admin2FAStatusResponse(BaseModel):
    enabled: bool
    method: str = "totp"
    detail: str


class AuthGateStatusResponse(BaseModel):
    enabled: bool
    source: str  # env | db


class AuthGateUpdateRequest(BaseModel):
    enabled: bool


class WorkflowProjectCreateRequest(BaseModel):
    title: str
    idea_prompt: Optional[str] = None
    genre: Optional[str] = None
    target_duration_minutes: int = 3


class WorkflowProjectUpdateRequest(BaseModel):
    title: Optional[str] = None
    idea_prompt: Optional[str] = None
    genre: Optional[str] = None
    target_duration_minutes: Optional[int] = None


class WorkflowProjectResponse(BaseModel):
    project_id: str
    title: str
    topic: str
    status: str
    idea_prompt: Optional[str] = None
    genre: Optional[str] = None
    target_duration_minutes: Optional[int] = None
    workflow_state: str
    script_draft: Optional[str] = None
    script_approved: Optional[str] = None
    script_approved_at: Optional[datetime] = None
    character_package_approved: bool = False
    character_package_approved_at: Optional[datetime] = None
    selected_character_ids: List[str] = []
    production_job_id: Optional[str] = None
    final_video_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkflowGenerateScriptRequest(BaseModel):
    title: str
    idea_prompt: Optional[str] = None
    genre: Optional[str] = None
    target_duration_minutes: int = 3
    tone: str = "cinematic"


class WorkflowScriptUpdateRequest(BaseModel):
    script: str
    update_scenes: bool = True


class WorkflowCharacterResponse(BaseModel):
    character_id: str
    name: str
    role_type: str
    description: str
    visual_prompt_base: str
    negative_prompt_base: str
    consistency_seed: str
    identity_hash: str
    lock_identity: bool = True
    reference_image_url: Optional[str] = None
    canonical_image_url: Optional[str] = None
    personality_traits: List[str] = []
    voice_profile: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkflowCharacterCreateRequest(BaseModel):
    name: str
    role_type: str = "supporting"
    description: str
    visual_prompt_base: Optional[str] = None
    negative_prompt_base: Optional[str] = None
    personality_traits: List[str] = []
    voice_profile: Optional[str] = None
    reference_image_url: Optional[str] = None
    lock_identity: bool = True
    select_after_create: bool = True


class WorkflowCharacterGenerateRequest(BaseModel):
    name: str
    role_type: str = "supporting"
    description: str
    personality_traits: List[str] = []
    voice_profile: Optional[str] = None
    style: str = "cinematic"
    select_after_create: bool = True


class WorkflowCharacterSelectRequest(BaseModel):
    selected_character_ids: List[str]


class WorkflowCharacterListResponse(BaseModel):
    library: List[WorkflowCharacterResponse]
    selected_character_ids: List[str] = []
    selected: List[WorkflowCharacterResponse] = []
    approved_character_ids: List[str] = []
    approved_at: Optional[datetime] = None


class WorkflowProductionSummaryResponse(BaseModel):
    project_id: str
    workflow_state: str
    script_ready: bool
    characters_ready: bool
    estimated_credits: int
    current_credit_balance: int
    target_duration_minutes: int
    selected_characters: List[WorkflowCharacterResponse] = []
    final_video_url: Optional[str] = None


class WorkflowProductionStatusResponse(BaseModel):
    project_id: str
    workflow_state: str
    production_job_id: Optional[str] = None
    final_video_url: Optional[str] = None


class WorkflowProductionStartResponse(BaseModel):
    project: WorkflowProjectResponse
    status: WorkflowProductionStatusResponse
    video_path: Optional[str] = None


class WorkflowLibraryResponse(BaseModel):
    characters: List[WorkflowCharacterResponse]
    scripts: List[WorkflowProjectResponse]
    videos: List[WorkflowProjectResponse]
