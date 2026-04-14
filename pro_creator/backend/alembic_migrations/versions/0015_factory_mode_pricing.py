"""add factory mode pricing settings

Revision ID: 0015_factory_mode_pricing
Revises: 0014_hidden_receipts
Create Date: 2026-04-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_factory_mode_pricing"
down_revision = "0014_hidden_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "appsettings" not in table_names:
        return

    settings_columns = {column["name"] for column in inspector.get_columns("appsettings")}
    additions = [
        ("factory_one_time_price_usd", sa.Integer(), "149"),
        ("factory_one_time_stripe_price_id", sa.Text(), None),
        ("factory_subscription_price_usd", sa.Integer(), "39"),
        ("factory_subscription_stripe_price_id", sa.Text(), None),
    ]
    for name, column_type, server_default in additions:
        if name in settings_columns:
            continue
        kwargs = {"nullable": False} if server_default is not None else {"nullable": True}
        if server_default is not None:
            kwargs["server_default"] = server_default
        op.add_column("appsettings", sa.Column(name, column_type, **kwargs))


def downgrade() -> None:
    op.drop_column("appsettings", "factory_subscription_stripe_price_id")
    op.drop_column("appsettings", "factory_subscription_price_usd")
    op.drop_column("appsettings", "factory_one_time_stripe_price_id")
    op.drop_column("appsettings", "factory_one_time_price_usd")
