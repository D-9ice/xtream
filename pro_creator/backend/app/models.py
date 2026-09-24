from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    project_id: str = Field(index=True, unique=True)
    title: str
    topic: str
    status: str = Field(default="created")
    idea_prompt: Optional[str] = None
    short_description: Optional[str] = None
    genre: Optional[str] = None
    target_duration_minutes: Optional[int] = None
    start_credits: Optional[str] = None
    end_credits: Optional[str] = None
    workflow_state: str = Field(default="draft", index=True)
    script_draft: Optional[str] = None
    script_approved: Optional[str] = None
    script_approved_at: Optional[datetime] = None
    character_package_approved: bool = Field(default=False)
    character_package_approved_at: Optional[datetime] = None
    selected_character_ids_json: Optional[str] = None
    production_job_id: Optional[str] = None
    final_video_url: Optional[str] = None
    archived_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    scenes: List["Scene"] = Relationship(back_populates="project")


class ProjectScriptVersion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    version_id: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    project_id: str = Field(index=True)
    version_type: str = Field(index=True)
    script_content: str
    created_at: datetime = Field(default_factory=utc_now)


class ProjectCharacterPackage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    package_id: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    project_id: str = Field(index=True)
    approved_by_user_id: int = Field(index=True)
    selected_character_ids_json: str
    package_snapshot_json: str
    approved_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)


class CharacterProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    character_id: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    name: str
    role_type: str = Field(default="supporting", index=True)
    description: str = ""
    visual_prompt_base: str = ""
    negative_prompt_base: str = ""
    consistency_seed: str = Field(index=True)
    identity_hash: str = Field(index=True)
    lock_identity: bool = Field(default=True)
    reference_image_url: Optional[str] = None
    reference_image_urls_json: str = "[]"
    canonical_image_url: Optional[str] = None
    personality_traits_json: str = "[]"
    voice_profile: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Scene(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    project_id: str = Field(foreign_key="project.project_id", index=True)
    text: str
    image_path: Optional[str] = None
    audio_path: Optional[str] = None

    project: Optional[Project] = Relationship(back_populates="scenes")


class OrchestrationJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    project_id: str = Field(index=True)
    kind: str
    status: str = Field(default="queued", index=True)
    attempts: int = Field(default=0)
    max_attempts: int = Field(default=3)
    last_error: Optional[str] = None
    payload: Optional[str] = None
    task_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class OrchestrationSchedule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    project_id: str = Field(index=True)
    cadence_days: int = Field(default=1)
    next_run_at: datetime
    enabled: bool = Field(default=True)
    last_run_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)


class Clip(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    project_id: str = Field(index=True)
    title: str
    start_time: float = Field(default=0.0)
    end_time: float = Field(default=0.0)
    order_index: int = Field(default=0)
    source_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    role: str = Field(default="admin")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)
    subscription: Optional["SubscriptionAccount"] = Relationship(
        back_populates="user"
    )


class SubscriptionAccount(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_subscriptionaccount_tenant_user"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    plan_name: str = Field(default="free")
    status: str = Field(default="active")
    credits_balance: int = Field(default=0)
    credits_reserved: int = Field(default=0)
    credits_used_total: int = Field(default=0)
    extra_character_slots: int = Field(default=0)
    factory_mode_status: str = Field(default="inactive")
    factory_mode_access: str = Field(default="none")
    factory_mode_renewal_date: Optional[datetime] = None
    factory_mode_purchased_at: Optional[datetime] = None
    renewal_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    user: Optional[User] = Relationship(back_populates="subscription")


class CreditLedgerEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    subscription_id: int = Field(foreign_key="subscriptionaccount.id", index=True)
    kind: str = Field(index=True)  # grant | reserve | consume | refund | expire | adjust
    amount: int
    reason: Optional[str] = None
    action: Optional[str] = Field(default=None, index=True)
    reference_id: Optional[str] = Field(default=None, index=True)
    provider: Optional[str] = None
    model: Optional[str] = None
    metadata_json: Optional[str] = None
    balance_after: int = Field(default=0)
    reserved_after: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class HiddenReceipt(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "ledger_entry_id", name="uq_hiddenreceipt_tenant_user_ledger"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    ledger_entry_id: int = Field(foreign_key="creditledgerentry.id", index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class AppSettings(SQLModel, table=True):
    """
    Local runtime settings that shouldn't require rebuilding containers.
    Keep this small and safe; treat anything here as non-secret local config.
    """

    id: Optional[int] = Field(default=1, primary_key=True)
    auth_required: bool = Field(default=False)
    plan_moderate_credits: int = Field(default=500)
    plan_moderate_price_usd: int = Field(default=15)
    plan_moderate_stripe_price_id: Optional[str] = None
    plan_pro_credits: int = Field(default=2000)
    plan_pro_price_usd: int = Field(default=49)
    plan_pro_stripe_price_id: Optional[str] = None
    plan_studio_credits: int = Field(default=6000)
    plan_studio_price_usd: int = Field(default=119)
    plan_studio_stripe_price_id: Optional[str] = None
    factory_one_time_credits: int = Field(default=0)
    factory_one_time_price_usd: int = Field(default=149)
    factory_one_time_stripe_price_id: Optional[str] = None
    factory_subscription_credits: int = Field(default=0)
    factory_subscription_price_usd: int = Field(default=39)
    factory_subscription_stripe_price_id: Optional[str] = None
    owner_mode_enabled: bool = Field(default=False)
    billing_receipts_live_mode: bool = Field(default=False)
    free_character_slots: int = Field(default=100)
    moderate_character_slots: int = Field(default=5)
    pro_character_slots: int = Field(default=10)
    studio_character_slots: int = Field(default=15)
    character_slot_addon_size: int = Field(default=5)
    character_slot_addon_cost_credits: int = Field(default=50)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SocialAccountConnection(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    connection_id: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    platform: str = Field(index=True)
    account_label: str
    account_identifier: Optional[str] = Field(default=None, index=True)
    access_token_encrypted: str
    access_token_secret_encrypted: Optional[str] = None
    refresh_token_encrypted: Optional[str] = None
    client_key_encrypted: Optional[str] = None
    client_secret_encrypted: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    scopes_json: str = "[]"
    metadata_json: str = "{}"
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SocialPublishJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    job_id: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    project_id: str = Field(index=True)
    connection_id: str = Field(index=True)
    platform: str = Field(index=True)
    status: str = Field(default="queued", index=True)
    remote_post_id: Optional[str] = None
    published_url: Optional[str] = None
    error_message: Optional[str] = None
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    published_at: Optional[datetime] = None


class UserFeedback(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    feedback_id: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    subject: str
    message: str
    page: Optional[str] = Field(default=None, index=True)
    project_id: Optional[str] = Field(default=None, index=True)
    developer_email: str = Field(default="")
    email_sent: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class CommunityPost(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    post_id: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    subject: str
    message: str
    author_label: str = Field(default="")
    author_email: str = Field(default="")
    applause_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class VisitEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    visit_id: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    path: str = Field(index=True)
    referrer: Optional[str] = Field(default=None, index=True)
    user_agent: Optional[str] = None
    device_type: Optional[str] = Field(default=None, index=True)
    country_code: Optional[str] = Field(default=None, index=True)
    page_title: Optional[str] = None
    session_id: Optional[str] = Field(default=None, index=True)
    event_type: str = Field(default="page_view", index=True)
    is_bot: bool = Field(default=False, index=True)
    bot_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now, index=True)
