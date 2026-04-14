"""Add user feedback submissions.

Revision ID: 0009_user_feedback
Revises: 0008_social_publishing
Create Date: 2026-04-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_user_feedback"
down_revision = "0008_social_publishing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "userfeedback" not in table_names:
        op.create_table(
            "userfeedback",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Text(), nullable=False, server_default="default"),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("feedback_id", sa.Text(), nullable=False),
            sa.Column("subject", sa.Text(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("page", sa.Text(), nullable=True),
            sa.Column("project_id", sa.Text(), nullable=True),
            sa.Column("developer_email", sa.Text(), nullable=False, server_default=""),
            sa.Column("email_sent", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_userfeedback_tenant_id", "userfeedback", ["tenant_id"])
        op.create_index("ix_userfeedback_user_id", "userfeedback", ["user_id"])
        op.create_index("ix_userfeedback_feedback_id", "userfeedback", ["feedback_id"])
        op.create_index("ix_userfeedback_page", "userfeedback", ["page"])
        op.create_index("ix_userfeedback_project_id", "userfeedback", ["project_id"])
        op.create_index("ix_userfeedback_created_at", "userfeedback", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_userfeedback_created_at", table_name="userfeedback")
    op.drop_index("ix_userfeedback_project_id", table_name="userfeedback")
    op.drop_index("ix_userfeedback_page", table_name="userfeedback")
    op.drop_index("ix_userfeedback_feedback_id", table_name="userfeedback")
    op.drop_index("ix_userfeedback_user_id", table_name="userfeedback")
    op.drop_index("ix_userfeedback_tenant_id", table_name="userfeedback")
    op.drop_table("userfeedback")
