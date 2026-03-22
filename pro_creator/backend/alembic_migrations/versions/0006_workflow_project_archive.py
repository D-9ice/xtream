"""Add workflow project archive support.

Revision ID: 0006_workflow_project_archive
Revises: 0005_character_reference_bundles
Create Date: 2026-03-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_workflow_project_archive"
down_revision = "0005_character_reference_bundles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project", sa.Column("archived_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("project", "archived_at")
