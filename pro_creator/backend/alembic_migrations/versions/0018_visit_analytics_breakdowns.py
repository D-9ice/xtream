"""add visit analytics breakdowns

Revision ID: 0018_visit_analytics_breakdowns
Revises: 0017_visit_analytics
Create Date: 2026-04-10 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018_visit_analytics_breakdowns"
down_revision = "0017_visit_analytics"
branch_labels = None
depends_on = None


def _table_columns(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "visitevent" not in table_names:
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
                    device_type VARCHAR,
                    country_code VARCHAR,
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
            bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_visitevent_device_type ON visitevent (device_type)")
            bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_visitevent_country_code ON visitevent (country_code)")
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
            sa.Column("device_type", sa.String(), nullable=True),
            sa.Column("country_code", sa.String(), nullable=True),
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
        op.create_index(op.f("ix_visitevent_device_type"), "visitevent", ["device_type"], unique=False)
        op.create_index(op.f("ix_visitevent_country_code"), "visitevent", ["country_code"], unique=False)
        op.create_index(op.f("ix_visitevent_created_at"), "visitevent", ["created_at"], unique=False)
        return

    columns = _table_columns(inspector, "visitevent")
    if "device_type" not in columns:
        if bind.dialect.name == "sqlite":
            bind.exec_driver_sql("ALTER TABLE visitevent ADD COLUMN device_type VARCHAR")
        else:
            op.add_column("visitevent", sa.Column("device_type", sa.String(), nullable=True))
    if "country_code" not in columns:
        if bind.dialect.name == "sqlite":
            bind.exec_driver_sql("ALTER TABLE visitevent ADD COLUMN country_code VARCHAR")
        else:
            op.add_column("visitevent", sa.Column("country_code", sa.String(), nullable=True))

    index_names = _index_names(inspector, "visitevent")
    if "ix_visitevent_device_type" not in index_names:
        if bind.dialect.name == "sqlite":
            bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_visitevent_device_type ON visitevent (device_type)")
        else:
            op.create_index(op.f("ix_visitevent_device_type"), "visitevent", ["device_type"], unique=False)
    if "ix_visitevent_country_code" not in index_names:
        if bind.dialect.name == "sqlite":
            bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_visitevent_country_code ON visitevent (country_code)")
        else:
            op.create_index(op.f("ix_visitevent_country_code"), "visitevent", ["country_code"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "visitevent" not in table_names:
        return

    index_names = _index_names(inspector, "visitevent")
    if "ix_visitevent_country_code" in index_names:
        op.drop_index(op.f("ix_visitevent_country_code"), table_name="visitevent")
    if "ix_visitevent_device_type" in index_names:
        op.drop_index(op.f("ix_visitevent_device_type"), table_name="visitevent")

    columns = _table_columns(inspector, "visitevent")
    if "country_code" in columns:
        if bind.dialect.name == "sqlite":
            pass
        else:
            op.drop_column("visitevent", "country_code")
    if "device_type" in columns:
        if bind.dialect.name == "sqlite":
            pass
        else:
            op.drop_column("visitevent", "device_type")
