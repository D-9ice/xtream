"""add factory mode entitlement columns

Revision ID: 0013_factory_mode_access
Revises: 0012_xtreamer_community_reactions
Create Date: 2026-04-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_factory_mode_access"
down_revision = "0012_xtreamer_community_reactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("subscriptionaccount")}
    additions = [
        ("factory_mode_status", sa.Text(), False, "inactive"),
        ("factory_mode_access", sa.Text(), False, "none"),
        ("factory_mode_renewal_date", sa.DateTime(), True, None),
        ("factory_mode_purchased_at", sa.DateTime(), True, None),
    ]
    for name, column_type, nullable, server_default in additions:
        if name in columns:
            continue
        kwargs = {"nullable": nullable}
        if server_default is not None:
            kwargs["server_default"] = server_default
        op.add_column("subscriptionaccount", sa.Column(name, column_type, **kwargs))


def downgrade() -> None:
    op.drop_column("subscriptionaccount", "factory_mode_purchased_at")
    op.drop_column("subscriptionaccount", "factory_mode_renewal_date")
    op.drop_column("subscriptionaccount", "factory_mode_access")
    op.drop_column("subscriptionaccount", "factory_mode_status")
