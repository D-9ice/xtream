"""add receipt and owner mode settings

Revision ID: 0016_receipt_mode
Revises: 0015_factory_mode_pricing
Create Date: 2026-04-08 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016_receipt_mode"
down_revision = "0015_factory_mode_pricing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "appsettings" not in table_names:
        return

    settings_columns = {column["name"] for column in inspector.get_columns("appsettings")}
    if "owner_mode_enabled" not in settings_columns:
        op.add_column(
            "appsettings",
            sa.Column(
                "owner_mode_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if "billing_receipts_live_mode" not in settings_columns:
        op.add_column(
            "appsettings",
            sa.Column(
                "billing_receipts_live_mode",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    op.drop_column("appsettings", "billing_receipts_live_mode")
    op.drop_column("appsettings", "owner_mode_enabled")
