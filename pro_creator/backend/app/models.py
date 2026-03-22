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
    genre: Optional[str] = None
    target_duration_minutes: Optional[int] = None
    workflow_state: str = Field(default="draft", index=True)
    script_draft: Optional[str] = None
    script_approved: Optional[str] = None
    script_approved_at: Optional[datetime] = None
    character_package_approved: bool = Field(default=False)
    character_package_approved_at: Optional[datetime] = None
    selected_character_ids_json: Optional[str] = None
    production_job_id: Optional[str] = None
    final_video_url: Optional[str] = None
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
    credits_balance: int = Field(default=1000)
    credits_reserved: int = Field(default=0)
    credits_used_total: int = Field(default=0)
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


class AppSettings(SQLModel, table=True):
    """
    Local runtime settings that shouldn't require rebuilding containers.
    Keep this small and safe; treat anything here as non-secret local config.
    """

    id: Optional[int] = Field(default=1, primary_key=True)
    auth_required: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
