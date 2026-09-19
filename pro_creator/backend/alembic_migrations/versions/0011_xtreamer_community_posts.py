"""Add X'treamers community posts.

Revision ID: 0011_xtreamer_community_posts
Revises: 0010_auto_create_studio_controls
Create Date: 2026-04-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011_xtreamer_community_posts"
down_revision = "0010_auto_create_studio_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "communitypost" in tables:
        return

    op.create_table(
        "communitypost",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Text(), nullable=False, unique=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("author_label", sa.Text(), nullable=False, server_default=""),
        sa.Column("author_email", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
    )
    op.create_index("ix_communitypost_tenant_id", "communitypost", ["tenant_id"])
    op.create_index("ix_communitypost_user_id", "communitypost", ["user_id"])
    op.create_index("ix_communitypost_post_id", "communitypost", ["post_id"])
    op.create_index("ix_communitypost_created_at", "communitypost", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "communitypost" not in tables:
        return

    op.drop_index("ix_communitypost_created_at", table_name="communitypost")
    op.drop_index("ix_communitypost_post_id", table_name="communitypost")
    op.drop_index("ix_communitypost_user_id", table_name="communitypost")
    op.drop_index("ix_communitypost_tenant_id", table_name="communitypost")
    op.drop_table("communitypost")
