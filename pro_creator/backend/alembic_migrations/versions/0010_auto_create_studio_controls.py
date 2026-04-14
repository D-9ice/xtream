"""Add auto-create studio controls fields.

Revision ID: 0010_auto_create_studio_controls
Revises: 0009_user_feedback
Create Date: 2026-04-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010_auto_create_studio_controls"
down_revision = "0009_user_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("project")}

    if "short_description" not in columns:
        op.add_column("project", sa.Column("short_description", sa.Text(), nullable=True))
    if "start_credits" not in columns:
        op.add_column("project", sa.Column("start_credits", sa.Text(), nullable=True))
    if "end_credits" not in columns:
        op.add_column("project", sa.Column("end_credits", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("project")}

    if "end_credits" in columns:
        op.drop_column("project", "end_credits")
    if "start_credits" in columns:
        op.drop_column("project", "start_credits")
    if "short_description" in columns:
        op.drop_column("project", "short_description")
