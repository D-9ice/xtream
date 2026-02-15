"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-02-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_project_project_id", "project", ["project_id"], unique=True)

    op.create_table(
        "scene",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("image_path", sa.String(), nullable=True),
        sa.Column("audio_path", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["project.project_id"]),
    )
    op.create_index("ix_scene_project_id", "scene", ["project_id"], unique=False)

    op.create_table(
        "orchestrationjob",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("payload", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_orchestrationjob_project_id", "orchestrationjob", ["project_id"], unique=False)
    op.create_index("ix_orchestrationjob_status", "orchestrationjob", ["status"], unique=False)

    op.create_table(
        "orchestrationschedule",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("cadence_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_run_at", sa.DateTime(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_orchestrationschedule_project_id", "orchestrationschedule", ["project_id"], unique=False)

    op.create_table(
        "clip",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False, server_default="0"),
        sa.Column("end_time", sa.Float(), nullable=False, server_default="0"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_clip_project_id", "clip", ["project_id"], unique=False)

    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="admin"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_user_email", "user", ["email"], unique=True)

    op.create_table(
        "subscriptionaccount",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_name", sa.String(), nullable=False, server_default="free"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("credits_balance", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("credits_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_used_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("renewal_date", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
    )
    op.create_index("ix_subscriptionaccount_user_id", "subscriptionaccount", ["user_id"], unique=True)

    op.create_table(
        "creditledgerentry",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=True),
        sa.Column("reference_id", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.String(), nullable=True),
        sa.Column("balance_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptionaccount.id"]),
    )
    op.create_index("ix_creditledgerentry_action", "creditledgerentry", ["action"], unique=False)
    op.create_index("ix_creditledgerentry_kind", "creditledgerentry", ["kind"], unique=False)
    op.create_index("ix_creditledgerentry_reference_id", "creditledgerentry", ["reference_id"], unique=False)
    op.create_index("ix_creditledgerentry_user_id", "creditledgerentry", ["user_id"], unique=False)
    op.create_index("ix_creditledgerentry_subscription_id", "creditledgerentry", ["subscription_id"], unique=False)
    op.create_index("ix_creditledgerentry_created_at", "creditledgerentry", ["created_at"], unique=False)

    op.create_table(
        "appsettings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("auth_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("appsettings")
    op.drop_table("creditledgerentry")
    op.drop_table("subscriptionaccount")
    op.drop_table("user")
    op.drop_table("clip")
    op.drop_table("orchestrationschedule")
    op.drop_table("orchestrationjob")
    op.drop_table("scene")
    op.drop_table("project")

