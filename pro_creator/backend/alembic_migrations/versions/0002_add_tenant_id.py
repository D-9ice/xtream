"""Add tenant_id columns (single-tenant default).

Revision ID: 0002_add_tenant_id
Revises: 0001_initial
Create Date: 2026-02-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_add_tenant_id"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


DEFAULT_TENANT = "default"


def _add_tenant(table: str, index_cols: list[str] | None = None) -> None:
    op.add_column(
        table,
        sa.Column(
            "tenant_id",
            sa.String(),
            nullable=False,
            server_default=DEFAULT_TENANT,
        ),
    )
    if index_cols:
        op.create_index(
            f"ix_{table}_tenant_" + "_".join(index_cols),
            table,
            ["tenant_id", *index_cols],
            unique=False,
        )


def upgrade() -> None:
    _add_tenant("project", ["project_id"])
    _add_tenant("scene", ["project_id"])
    _add_tenant("clip", ["project_id"])
    _add_tenant("orchestrationjob", ["project_id"])
    _add_tenant("orchestrationschedule", ["project_id"])
    _add_tenant("subscriptionaccount", ["user_id"])
    _add_tenant("creditledgerentry", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_creditledgerentry_tenant_user_id", table_name="creditledgerentry")
    op.drop_column("creditledgerentry", "tenant_id")

    op.drop_index("ix_subscriptionaccount_tenant_user_id", table_name="subscriptionaccount")
    op.drop_column("subscriptionaccount", "tenant_id")

    op.drop_index("ix_orchestrationschedule_tenant_project_id", table_name="orchestrationschedule")
    op.drop_column("orchestrationschedule", "tenant_id")

    op.drop_index("ix_orchestrationjob_tenant_project_id", table_name="orchestrationjob")
    op.drop_column("orchestrationjob", "tenant_id")

    op.drop_index("ix_clip_tenant_project_id", table_name="clip")
    op.drop_column("clip", "tenant_id")

    op.drop_index("ix_scene_tenant_project_id", table_name="scene")
    op.drop_column("scene", "tenant_id")

    op.drop_index("ix_project_tenant_project_id", table_name="project")
    op.drop_column("project", "tenant_id")

