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
    duration_minutes: int = 3
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


class VideoResponse(BaseModel):
    video_path: str


class VideoImportRequest(BaseModel):
    project_id: str
    url: str


class VideoImportResponse(BaseModel):
    video_path: str


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
    duration_minutes: int = 3
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
    running: bool
    interval_seconds: int


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
