"""Add character slot pricing and quota settings.

Revision ID: 0007_character_slot_pricing
Revises: 0006_workflow_project_archive
Create Date: 2026-03-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_character_slot_pricing"
down_revision = "0006_workflow_project_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "subscriptionaccount" in table_names:
        subscription_columns = {column["name"] for column in inspector.get_columns("subscriptionaccount")}
        if "extra_character_slots" not in subscription_columns:
            op.add_column(
                "subscriptionaccount",
                sa.Column(
                    "extra_character_slots",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
            )

    if "appsettings" not in table_names:
        return

    settings_columns = {column["name"] for column in inspector.get_columns("appsettings")}
    additions = [
        ("plan_moderate_credits", sa.Integer(), "500"),
        ("plan_moderate_price_usd", sa.Integer(), "15"),
        ("plan_moderate_stripe_price_id", sa.Text(), None),
        ("plan_pro_credits", sa.Integer(), "2000"),
        ("plan_pro_price_usd", sa.Integer(), "49"),
        ("plan_pro_stripe_price_id", sa.Text(), None),
        ("plan_studio_credits", sa.Integer(), "6000"),
        ("plan_studio_price_usd", sa.Integer(), "119"),
        ("plan_studio_stripe_price_id", sa.Text(), None),
        ("free_character_slots", sa.Integer(), "100"),
        ("moderate_character_slots", sa.Integer(), "5"),
        ("pro_character_slots", sa.Integer(), "10"),
        ("studio_character_slots", sa.Integer(), "15"),
        ("character_slot_addon_size", sa.Integer(), "5"),
        ("character_slot_addon_cost_credits", sa.Integer(), "50"),
    ]
    for name, column_type, server_default in additions:
        if name in settings_columns:
            continue
        kwargs = {"nullable": False} if server_default is not None else {"nullable": True}
        if server_default is not None:
            kwargs["server_default"] = server_default
        op.add_column("appsettings", sa.Column(name, column_type, **kwargs))


def downgrade() -> None:
    op.drop_column("subscriptionaccount", "extra_character_slots")
    op.drop_column("appsettings", "character_slot_addon_cost_credits")
    op.drop_column("appsettings", "character_slot_addon_size")
    op.drop_column("appsettings", "studio_character_slots")
    op.drop_column("appsettings", "pro_character_slots")
    op.drop_column("appsettings", "moderate_character_slots")
    op.drop_column("appsettings", "free_character_slots")
    op.drop_column("appsettings", "plan_studio_stripe_price_id")
    op.drop_column("appsettings", "plan_studio_price_usd")
    op.drop_column("appsettings", "plan_studio_credits")
    op.drop_column("appsettings", "plan_pro_stripe_price_id")
    op.drop_column("appsettings", "plan_pro_price_usd")
    op.drop_column("appsettings", "plan_pro_credits")
    op.drop_column("appsettings", "plan_moderate_stripe_price_id")
    op.drop_column("appsettings", "plan_moderate_price_usd")
    op.drop_column("appsettings", "plan_moderate_credits")
