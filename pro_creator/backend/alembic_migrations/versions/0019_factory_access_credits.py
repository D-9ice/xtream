"""add configurable Factory Mode credit allocations

Revision ID: 0019_factory_access_credits
Revises: 0018_visit_analytics_breakdowns
Create Date: 2026-09-19 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0019_factory_access_credits"
down_revision = "0018_visit_analytics_breakdowns"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("appsettings")}


def upgrade() -> None:
    columns = _columns()
    if "factory_one_time_credits" not in columns:
        op.add_column("appsettings", sa.Column("factory_one_time_credits", sa.Integer(), nullable=False, server_default="0"))
    if "factory_subscription_credits" not in columns:
        op.add_column("appsettings", sa.Column("factory_subscription_credits", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    columns = _columns()
    if "factory_subscription_credits" in columns:
        op.drop_column("appsettings", "factory_subscription_credits")
    if "factory_one_time_credits" in columns:
        op.drop_column("appsettings", "factory_one_time_credits")
