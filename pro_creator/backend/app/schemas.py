from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


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
    genre: Optional[str] = None


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


class VoiceResponse(BaseModel):
    audio_path: str
    duration_seconds: float


class CharacterVoiceProfile(BaseModel):
    character_id: str
    display_name: str
    voice_profile: str = "default"
    voice_id: Optional[str] = None


class CharacterVoiceProfileListResponse(BaseModel):
    characters: List[CharacterVoiceProfile]


class DialogueLine(BaseModel):
    speaker_id: str
    text: str
    pause_ms: int = 250
    voice_profile: Optional[str] = None
    voice_id: Optional[str] = None


class DialogueSceneRequest(BaseModel):
    scene_id: int
    lines: List[DialogueLine]


class DialogueRenderRequest(BaseModel):
    project_id: str
    scenes: List[DialogueSceneRequest]
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


class SocialAccountConnectionRequest(BaseModel):
    connection_id: Optional[str] = None
    platform: str
    account_label: str
    account_identifier: Optional[str] = None
    access_token: Optional[str] = None
    access_token_secret: Optional[str] = None
    refresh_token: Optional[str] = None
    client_key: Optional[str] = None
    client_secret: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    scopes: List[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class SocialAccountConnectionResponse(BaseModel):
    connection_id: str
    platform: str
    account_label: str
    account_identifier: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    token_expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class SocialAccountConnectionListResponse(BaseModel):
    items: List[SocialAccountConnectionResponse]


class SocialOAuthStartResponse(BaseModel):
    authorization_url: str
    state: str


class SocialOAuthCompleteRequest(BaseModel):
    platform: str
    state: str
    code: Optional[str] = None
    oauth_token: Optional[str] = None
    oauth_verifier: Optional[str] = None


class SocialPublishRequest(BaseModel):
    project_id: str
    connection_ids: List[str] = Field(default_factory=list)
    message: Optional[str] = None
    title: Optional[str] = None


class SocialPublishJobResponse(BaseModel):
    job_id: str
    project_id: str
    connection_id: str
    platform: str
    status: str
    remote_post_id: Optional[str] = None
    published_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None


class SocialPublishJobListResponse(BaseModel):
    items: List[SocialPublishJobResponse]


class SocialDeleteResponse(BaseModel):
    deleted: bool


class EditByTextRequest(BaseModel):
    project_id: str
    remove_ranges: List[List[float]]


class EditByTextResponse(BaseModel):
    segments_remaining: int
    video_path: Optional[str] = None


class FeatureOperationResponse(BaseModel):
    status: str
    detail: str


class UserCreateRequest(BaseModel):
    email: str
    password: str
    role: str = "admin"


class PublicRegistrationRequest(BaseModel):
    email: str
    password: str


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
    genre: Optional[str] = None
    titles: List[str] = Field(default_factory=list)
    short_description: Optional[str] = None
    start_credits: Optional[str] = None
    end_credits: Optional[str] = None
    publish_message: Optional[str] = None
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
    cadence_days: int = Field(default=1, ge=1, le=3650)


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
    extra_character_slots: int = 0
    owner_mode_enabled: bool = False
    factory_mode_status: str = "inactive"
    factory_mode_access: str = "none"
    factory_mode_renewal_date: Optional[datetime] = None
    factory_mode_purchased_at: Optional[datetime] = None
    character_slots: "CharacterSlotSummaryResponse"


class CharacterSlotSummaryResponse(BaseModel):
    base_slots: int
    extra_slots: int
    total_slots: int
    used_slots: int
    remaining_slots: int
    addon_pack_size: int
    addon_pack_cost_credits: int
    is_full: bool = False


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
    kind: str = "credits"
    credits: int
    price_usd: int
    base_character_slots: int
    popular: bool = False
    stripe_price_id: Optional[str] = None
    checkout_providers: List[str] = Field(default_factory=list)
    checkout_enabled: bool = False
    access_mode: Optional[str] = None
    access_days: Optional[int] = None
    description: Optional[str] = None


class CreditPlanListResponse(BaseModel):
    plans: List[CreditPlan]


class CreditsPurchaseRequest(BaseModel):
    plan_id: str
    provider: str = "stripe"


class CharacterSlotPurchaseRequest(BaseModel):
    pack_count: int = 1


class BillingCheckoutSessionResponse(BaseModel):
    provider: str = "stripe"
    session_id: str
    checkout_url: str


class StripeCheckoutSessionResponse(BillingCheckoutSessionResponse):
    provider: str = "stripe"


class BillingReceiptItem(BaseModel):
    receipt_id: int
    created_at: datetime
    kind: str
    action: Optional[str] = None
    amount: int
    reason: Optional[str] = None
    reference_id: Optional[str] = None
    provider: Optional[str] = None
    balance_after: int
    reserved_after: int
    plan_id: Optional[str] = None
    plan_kind: Optional[str] = None
    access_mode: Optional[str] = None
    purchase_label: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BillingReceiptListResponse(BaseModel):
    items: List[BillingReceiptItem]


class BillingReceiptDeleteResponse(BaseModel):
    deleted: bool
    receipt_id: int
    deleted_permanently: bool = False


class BillingTransactionRecordItem(BaseModel):
    record_id: int
    created_at: datetime
    kind: str
    action: Optional[str] = None
    amount: int
    reason: Optional[str] = None
    reference_id: Optional[str] = None
    provider: Optional[str] = None
    balance_after: int
    reserved_after: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class BillingTransactionRecordListResponse(BaseModel):
    items: List[BillingTransactionRecordItem]


class BillingTransactionRecordClearResponse(BaseModel):
    deleted: bool
    deleted_count: int
    deleted_ids: List[int]


class AdminSubscriptionUpdateRequest(BaseModel):
    plan_name: Optional[str] = None
    status: Optional[str] = None
    credits_delta: Optional[int] = None
    credits_balance: Optional[int] = None
    renewal_date: Optional[datetime] = None
    factory_mode_access: Optional[str] = None
    factory_mode_renewal_date: Optional[datetime] = None


class AdminSubscriptionListResponse(BaseModel):
    items: List[CreditBalanceResponse]


class AdminUserDeleteResponse(BaseModel):
    deleted: bool
    email: str


class AdminUserBulkDeleteResponse(BaseModel):
    deleted_count: int
    deleted_emails: List[str]


class BillingPricingSettingsResponse(BaseModel):
    plans: List[CreditPlan]
    owner_mode_enabled: bool
    receipts_live_mode: bool
    free_base_character_slots: int
    character_slot_addon_size: int
    character_slot_addon_cost_credits: int


class AdminBillingSettingsUpdateRequest(BaseModel):
    moderate_credits: int
    moderate_price_usd: int
    moderate_base_character_slots: int
    moderate_stripe_price_id: Optional[str] = None
    pro_credits: int
    pro_price_usd: int
    pro_base_character_slots: int
    pro_stripe_price_id: Optional[str] = None
    studio_credits: int
    studio_price_usd: int
    studio_base_character_slots: int
    studio_stripe_price_id: Optional[str] = None
    factory_subscription_credits: int
    factory_subscription_price_usd: int
    factory_subscription_stripe_price_id: Optional[str] = None
    owner_mode_enabled: bool
    receipts_live_mode: bool
    free_base_character_slots: int
    character_slot_addon_size: int
    character_slot_addon_cost_credits: int


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


class WorkflowAutoCreateCharacterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role_type: str = Field(default="supporting", max_length=40)
    description: Optional[str] = Field(default=None, max_length=500)


class WorkflowAutoCreateRequest(BaseModel):
    title: str
    duration_minutes: int = 3
    genre: Optional[str] = None
    short_description: Optional[str] = None
    start_credits: Optional[str] = None
    end_credits: Optional[str] = None
    custom_characters: List[WorkflowAutoCreateCharacterRequest] = Field(default_factory=list)


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
    short_description: Optional[str] = None
    genre: Optional[str] = None
    target_duration_minutes: Optional[int] = None
    start_credits: Optional[str] = None
    end_credits: Optional[str] = None
    workflow_state: str
    script_draft: Optional[str] = None
    script_approved: Optional[str] = None
    script_approved_at: Optional[datetime] = None
    character_package_approved: bool = False
    character_package_approved_at: Optional[datetime] = None
    selected_character_ids: List[str] = []
    production_job_id: Optional[str] = None
    final_video_url: Optional[str] = None
    archived_at: Optional[datetime] = None
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
    reference_image_urls: List[str] = []
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
    reference_image_urls: List[str] = []
    canonical_image_url: Optional[str] = None
    lock_identity: bool = True
    select_after_create: bool = True


class WorkflowCharacterGenerateRequest(BaseModel):
    name: str
    role_type: str = "supporting"
    description: str
    personality_traits: List[str] = []
    voice_profile: Optional[str] = None
    style: str = "cinematic"
    lock_identity: bool = True
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
    queue_status: Optional[str] = None
    queue_attempts: int = 0
    queue_max_attempts: int = 0
    last_error: Optional[str] = None
    can_retry: bool = False
    final_video_url: Optional[str] = None


class WorkflowProductionStartResponse(BaseModel):
    project: WorkflowProjectResponse
    status: WorkflowProductionStatusResponse
    video_path: Optional[str] = None


class WorkflowAutoCreateResponse(BaseModel):
    project: WorkflowProjectResponse
    status: WorkflowProductionStatusResponse
    video_path: Optional[str] = None
    requested_duration_minutes: int
    applied_duration_minutes: int
    max_affordable_duration_minutes: int
    estimated_credits: int


class WorkflowLibraryResponse(BaseModel):
    characters: List[WorkflowCharacterResponse]
    scripts: List[WorkflowProjectResponse]
    videos: List[WorkflowProjectResponse]


class WorkflowFeedbackRequest(BaseModel):
    subject: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=10, max_length=5000)
    page: Optional[str] = Field(default=None, max_length=120)
    project_id: Optional[str] = Field(default=None, max_length=120)


class WorkflowFeedbackResponse(BaseModel):
    feedback_id: str
    subject: str
    page: Optional[str] = None
    project_id: Optional[str] = None
    email_sent: bool = False
    created_at: datetime


class CommunityPostCreateRequest(BaseModel):
    subject: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=10, max_length=5000)


class CommunityPostResponse(BaseModel):
    post_id: str
    subject: str
    message: str
    author_label: str
    author_email: str
    applause_count: int = 0
    created_at: datetime


class CommunityPostListResponse(BaseModel):
    items: list[CommunityPostResponse]


class VisitEventCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    path: str = Field(min_length=1, max_length=512)
    referrer: Optional[str] = Field(default=None, max_length=512)
    user_agent: Optional[str] = Field(default=None, max_length=512)
    device_hint: Optional[str] = Field(default=None, max_length=40)
    country_hint: Optional[str] = Field(default=None, max_length=40)
    page_title: Optional[str] = Field(default=None, max_length=200)
    session_id: Optional[str] = Field(default=None, max_length=120)
    event_type: str = Field(default="page_view", max_length=40)
    bot_hint: bool = False


class VisitEventResponse(BaseModel):
    visit_id: str
    path: str
    referrer: Optional[str] = None
    device_type: Optional[str] = None
    country_code: Optional[str] = None
    page_title: Optional[str] = None
    session_id: Optional[str] = None
    event_type: str = "page_view"
    is_bot: bool = False
    bot_reason: Optional[str] = None
    created_at: datetime


class VisitAnalyticsTopPathResponse(BaseModel):
    path: str
    visits: int
    human_visits: int
    bot_visits: int


class VisitAnalyticsBreakdownResponse(BaseModel):
    label: str
    visits: int
    human_visits: int
    bot_visits: int


class VisitAnalyticsDailyPointResponse(BaseModel):
    day: date
    visits: int
    human_visits: int
    bot_visits: int


class VisitAnalyticsSummaryResponse(BaseModel):
    total_visits: int
    human_visits: int
    bot_visits: int
    unique_sessions: int
    unique_paths: int
    visits_last_24h: int
    visits_last_7d: int
    top_paths: list[VisitAnalyticsTopPathResponse] = Field(default_factory=list)
    top_devices: list[VisitAnalyticsBreakdownResponse] = Field(default_factory=list)
    top_countries: list[VisitAnalyticsBreakdownResponse] = Field(default_factory=list)
    recent_visits: list[VisitEventResponse] = Field(default_factory=list)
    daily_visits: list[VisitAnalyticsDailyPointResponse] = Field(default_factory=list)
