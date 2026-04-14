"""add hidden receipt table

Revision ID: 0014_hidden_receipts
Revises: 0013_factory_mode_access
Create Date: 2026-04-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_hidden_receipts"
down_revision = "0013_factory_mode_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "hiddenreceipt" in set(inspector.get_table_names()):
        return
    op.create_table(
        "hiddenreceipt",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ledger_entry_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", "ledger_entry_id", name="uq_hiddenreceipt_tenant_user_ledger"),
        sa.ForeignKeyConstraint(["ledger_entry_id"], ["creditledgerentry.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
    )
    op.create_index(op.f("ix_hiddenreceipt_tenant_id"), "hiddenreceipt", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_hiddenreceipt_user_id"), "hiddenreceipt", ["user_id"], unique=False)
    op.create_index(op.f("ix_hiddenreceipt_ledger_entry_id"), "hiddenreceipt", ["ledger_entry_id"], unique=False)
    op.create_index(op.f("ix_hiddenreceipt_created_at"), "hiddenreceipt", ["created_at"], unique=False)
    

def downgrade() -> None:
    op.drop_index(op.f("ix_hiddenreceipt_created_at"), table_name="hiddenreceipt")
    op.drop_index(op.f("ix_hiddenreceipt_ledger_entry_id"), table_name="hiddenreceipt")
    op.drop_index(op.f("ix_hiddenreceipt_user_id"), table_name="hiddenreceipt")
    op.drop_index(op.f("ix_hiddenreceipt_tenant_id"), table_name="hiddenreceipt")
    op.drop_table("hiddenreceipt")
