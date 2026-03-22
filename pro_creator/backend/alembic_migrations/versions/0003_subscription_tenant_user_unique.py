"""Make subscription uniqueness tenant-scoped.

Revision ID: 0003_subscription_tenant_user_unique
Revises: 0002_add_tenant_id
Create Date: 2026-02-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_subscription_tenant_user_unique"
down_revision = "0002_add_tenant_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    index_names = {index["name"] for index in inspector.get_indexes("subscriptionaccount")}

    if "ix_subscriptionaccount_user_id" in index_names:
        op.drop_index("ix_subscriptionaccount_user_id", table_name="subscriptionaccount")

    if "ix_subscriptionaccount_tenant_user_id" in index_names:
        op.drop_index("ix_subscriptionaccount_tenant_user_id", table_name="subscriptionaccount")

    op.create_index(
        "ix_subscriptionaccount_tenant_user_id",
        "subscriptionaccount",
        ["tenant_id", "user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_subscriptionaccount_tenant_user_id", table_name="subscriptionaccount")
    op.create_index(
        "ix_subscriptionaccount_tenant_user_id",
        "subscriptionaccount",
        ["tenant_id", "user_id"],
        unique=False,
    )
    op.create_index("ix_subscriptionaccount_user_id", "subscriptionaccount", ["user_id"], unique=True)
