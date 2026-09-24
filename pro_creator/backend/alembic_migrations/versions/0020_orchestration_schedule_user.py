"""add user ownership to orchestration schedules

Revision ID: 0020_orchestration_schedule_user
Revises: 0019_factory_access_credits
Create Date: 2026-09-24 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0020_orchestration_schedule_user"
down_revision = "0019_factory_access_credits"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("orchestrationschedule")}


def upgrade() -> None:
    if "user_id" not in _columns():
        op.add_column("orchestrationschedule", sa.Column("user_id", sa.Integer(), nullable=True))
        op.create_index("ix_orchestrationschedule_user_id", "orchestrationschedule", ["user_id"], unique=False)


def downgrade() -> None:
    if "user_id" in _columns():
        try:
            op.drop_index("ix_orchestrationschedule_user_id", table_name="orchestrationschedule")
        except Exception:
            pass
        op.drop_column("orchestrationschedule", "user_id")
