"""Add social account connections and publish jobs.

Revision ID: 0008_social_publishing
Revises: 0007_character_slot_pricing
Create Date: 2026-04-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_social_publishing"
down_revision = "0007_character_slot_pricing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "socialaccountconnection" not in table_names:
        op.create_table(
            "socialaccountconnection",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Text(), nullable=False, server_default="default"),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("connection_id", sa.Text(), nullable=False),
            sa.Column("platform", sa.Text(), nullable=False),
            sa.Column("account_label", sa.Text(), nullable=False),
            sa.Column("account_identifier", sa.Text(), nullable=True),
            sa.Column("access_token_encrypted", sa.Text(), nullable=False),
            sa.Column("access_token_secret_encrypted", sa.Text(), nullable=True),
            sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
            sa.Column("client_key_encrypted", sa.Text(), nullable=True),
            sa.Column("client_secret_encrypted", sa.Text(), nullable=True),
            sa.Column("token_expires_at", sa.DateTime(), nullable=True),
            sa.Column("scopes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_socialaccountconnection_tenant_id", "socialaccountconnection", ["tenant_id"])
        op.create_index("ix_socialaccountconnection_user_id", "socialaccountconnection", ["user_id"])
        op.create_index("ix_socialaccountconnection_connection_id", "socialaccountconnection", ["connection_id"])
        op.create_index("ix_socialaccountconnection_platform", "socialaccountconnection", ["platform"])
        op.create_index(
            "ix_socialaccountconnection_account_identifier",
            "socialaccountconnection",
            ["account_identifier"],
        )

    if "socialpublishjob" not in table_names:
        op.create_table(
            "socialpublishjob",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Text(), nullable=False, server_default="default"),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("job_id", sa.Text(), nullable=False),
            sa.Column("project_id", sa.Text(), nullable=False),
            sa.Column("connection_id", sa.Text(), nullable=False),
            sa.Column("platform", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
            sa.Column("remote_post_id", sa.Text(), nullable=True),
            sa.Column("published_url", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("published_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_socialpublishjob_tenant_id", "socialpublishjob", ["tenant_id"])
        op.create_index("ix_socialpublishjob_user_id", "socialpublishjob", ["user_id"])
        op.create_index("ix_socialpublishjob_job_id", "socialpublishjob", ["job_id"])
        op.create_index("ix_socialpublishjob_project_id", "socialpublishjob", ["project_id"])
        op.create_index("ix_socialpublishjob_connection_id", "socialpublishjob", ["connection_id"])
        op.create_index("ix_socialpublishjob_platform", "socialpublishjob", ["platform"])
        op.create_index("ix_socialpublishjob_status", "socialpublishjob", ["status"])


def downgrade() -> None:
    op.drop_index("ix_socialpublishjob_status", table_name="socialpublishjob")
    op.drop_index("ix_socialpublishjob_platform", table_name="socialpublishjob")
    op.drop_index("ix_socialpublishjob_connection_id", table_name="socialpublishjob")
    op.drop_index("ix_socialpublishjob_project_id", table_name="socialpublishjob")
    op.drop_index("ix_socialpublishjob_job_id", table_name="socialpublishjob")
    op.drop_index("ix_socialpublishjob_user_id", table_name="socialpublishjob")
    op.drop_index("ix_socialpublishjob_tenant_id", table_name="socialpublishjob")
    op.drop_table("socialpublishjob")
    op.drop_index("ix_socialaccountconnection_account_identifier", table_name="socialaccountconnection")
    op.drop_index("ix_socialaccountconnection_platform", table_name="socialaccountconnection")
    op.drop_index("ix_socialaccountconnection_connection_id", table_name="socialaccountconnection")
    op.drop_index("ix_socialaccountconnection_user_id", table_name="socialaccountconnection")
    op.drop_index("ix_socialaccountconnection_tenant_id", table_name="socialaccountconnection")
    op.drop_table("socialaccountconnection")
