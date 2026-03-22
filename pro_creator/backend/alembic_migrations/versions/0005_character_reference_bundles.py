"""Add character reference image bundles.

Revision ID: 0005_character_reference_bundles
Revises: 0004_workflow_upgrade
Create Date: 2026-03-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_character_reference_bundles"
down_revision = "0004_workflow_upgrade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "characterprofile",
        sa.Column(
            "reference_image_urls_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("characterprofile", "reference_image_urls_json")
