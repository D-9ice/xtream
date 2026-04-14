"""add visit analytics

Revision ID: 0017_visit_analytics
Revises: 0016_receipt_mode
Create Date: 2026-04-10 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0017_visit_analytics"
down_revision = "0016_receipt_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "visitevent" in table_names:
        return
    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS visitevent (
                id INTEGER NOT NULL PRIMARY KEY,
                tenant_id VARCHAR NOT NULL DEFAULT 'default',
                visit_id VARCHAR NOT NULL,
                path VARCHAR NOT NULL,
                referrer VARCHAR,
                user_agent VARCHAR,
                page_title VARCHAR,
                session_id VARCHAR,
                event_type VARCHAR NOT NULL DEFAULT 'page_view',
                is_bot BOOLEAN NOT NULL DEFAULT 0,
                bot_reason VARCHAR,
                created_at DATETIME NOT NULL
            )
            """
        )
        bind.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_visitevent_visit_id ON visitevent (visit_id)"
        )
        bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_visitevent_tenant_id ON visitevent (tenant_id)")
        bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_visitevent_path ON visitevent (path)")
        bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_visitevent_session_id ON visitevent (session_id)")
        bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_visitevent_event_type ON visitevent (event_type)")
        bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_visitevent_is_bot ON visitevent (is_bot)")
        bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_visitevent_created_at ON visitevent (created_at)")
        return

    op.create_table(
        "visitevent",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("visit_id", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("referrer", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("page_title", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False, server_default="page_view"),
        sa.Column("is_bot", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("bot_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_visitevent_tenant_id"), "visitevent", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_visitevent_visit_id"), "visitevent", ["visit_id"], unique=True)
    op.create_index(op.f("ix_visitevent_path"), "visitevent", ["path"], unique=False)
    op.create_index(op.f("ix_visitevent_session_id"), "visitevent", ["session_id"], unique=False)
    op.create_index(op.f("ix_visitevent_event_type"), "visitevent", ["event_type"], unique=False)
    op.create_index(op.f("ix_visitevent_is_bot"), "visitevent", ["is_bot"], unique=False)
    op.create_index(op.f("ix_visitevent_created_at"), "visitevent", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_visitevent_created_at"), table_name="visitevent")
    op.drop_index(op.f("ix_visitevent_is_bot"), table_name="visitevent")
    op.drop_index(op.f("ix_visitevent_event_type"), table_name="visitevent")
    op.drop_index(op.f("ix_visitevent_session_id"), table_name="visitevent")
    op.drop_index(op.f("ix_visitevent_path"), table_name="visitevent")
    op.drop_index(op.f("ix_visitevent_visit_id"), table_name="visitevent")
    op.drop_index(op.f("ix_visitevent_tenant_id"), table_name="visitevent")
    op.drop_table("visitevent")
