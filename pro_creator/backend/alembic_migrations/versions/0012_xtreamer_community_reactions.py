"""add applause count to community posts

Revision ID: 0012_xtreamer_community_reactions
Revises: 0011_xtreamer_community_posts
Create Date: 2026-04-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_xtreamer_community_reactions"
down_revision = "0011_xtreamer_community_posts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("communitypost")}
    if "applause_count" not in columns:
        op.add_column(
            "communitypost",
            sa.Column("applause_count", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_column("communitypost", "applause_count")
