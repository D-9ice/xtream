"""Add guided workflow schema.

Revision ID: 0004_workflow_upgrade
Revises: 0003_subscription_tenant_user_unique
Create Date: 2026-03-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_workflow_upgrade"
down_revision = "0003_subscription_tenant_user_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("project", sa.Column("idea_prompt", sa.Text(), nullable=True))
    op.add_column("project", sa.Column("genre", sa.String(), nullable=True))
    op.add_column("project", sa.Column("target_duration_minutes", sa.Integer(), nullable=True))
    op.add_column(
        "project",
        sa.Column("workflow_state", sa.String(), nullable=False, server_default="draft"),
    )
    op.add_column("project", sa.Column("script_draft", sa.Text(), nullable=True))
    op.add_column("project", sa.Column("script_approved", sa.Text(), nullable=True))
    op.add_column("project", sa.Column("script_approved_at", sa.DateTime(), nullable=True))
    op.add_column(
        "project",
        sa.Column(
            "character_package_approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "project",
        sa.Column("character_package_approved_at", sa.DateTime(), nullable=True),
    )
    op.add_column("project", sa.Column("selected_character_ids_json", sa.Text(), nullable=True))
    op.add_column("project", sa.Column("production_job_id", sa.String(), nullable=True))
    op.add_column("project", sa.Column("final_video_url", sa.Text(), nullable=True))
    if bind.dialect.name == "sqlite":
        op.add_column("project", sa.Column("updated_at", sa.DateTime(), nullable=True))
    else:
        op.add_column(
            "project",
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    op.create_index("ix_project_workflow_state", "project", ["workflow_state"], unique=False)

    op.create_table(
        "projectscriptversion",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("version_type", sa.String(), nullable=False),
        sa.Column("script_content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_projectscriptversion_tenant_id", "projectscriptversion", ["tenant_id"], unique=False)
    op.create_index("ix_projectscriptversion_version_id", "projectscriptversion", ["version_id"], unique=True)
    op.create_index("ix_projectscriptversion_project_id", "projectscriptversion", ["project_id"], unique=False)
    op.create_index("ix_projectscriptversion_version_type", "projectscriptversion", ["version_type"], unique=False)

    op.create_table(
        "projectcharacterpackage",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("package_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=False),
        sa.Column("selected_character_ids_json", sa.Text(), nullable=False),
        sa.Column("package_snapshot_json", sa.Text(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_projectcharacterpackage_tenant_id",
        "projectcharacterpackage",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_projectcharacterpackage_package_id",
        "projectcharacterpackage",
        ["package_id"],
        unique=True,
    )
    op.create_index(
        "ix_projectcharacterpackage_project_id",
        "projectcharacterpackage",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_projectcharacterpackage_approved_by_user_id",
        "projectcharacterpackage",
        ["approved_by_user_id"],
        unique=False,
    )

    op.create_table(
        "characterprofile",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("role_type", sa.String(), nullable=False, server_default="supporting"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("visual_prompt_base", sa.Text(), nullable=False, server_default=""),
        sa.Column("negative_prompt_base", sa.Text(), nullable=False, server_default=""),
        sa.Column("consistency_seed", sa.String(), nullable=False),
        sa.Column("identity_hash", sa.String(), nullable=False),
        sa.Column("lock_identity", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reference_image_url", sa.Text(), nullable=True),
        sa.Column("canonical_image_url", sa.Text(), nullable=True),
        sa.Column("personality_traits_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("voice_profile", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_characterprofile_tenant_id", "characterprofile", ["tenant_id"], unique=False)
    op.create_index("ix_characterprofile_character_id", "characterprofile", ["character_id"], unique=True)
    op.create_index("ix_characterprofile_role_type", "characterprofile", ["role_type"], unique=False)
    op.create_index(
        "ix_characterprofile_consistency_seed",
        "characterprofile",
        ["consistency_seed"],
        unique=False,
    )
    op.create_index(
        "ix_characterprofile_identity_hash",
        "characterprofile",
        ["identity_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_characterprofile_identity_hash", table_name="characterprofile")
    op.drop_index("ix_characterprofile_consistency_seed", table_name="characterprofile")
    op.drop_index("ix_characterprofile_role_type", table_name="characterprofile")
    op.drop_index("ix_characterprofile_character_id", table_name="characterprofile")
    op.drop_index("ix_characterprofile_tenant_id", table_name="characterprofile")
    op.drop_table("characterprofile")

    op.drop_index("ix_projectcharacterpackage_approved_by_user_id", table_name="projectcharacterpackage")
    op.drop_index("ix_projectcharacterpackage_project_id", table_name="projectcharacterpackage")
    op.drop_index("ix_projectcharacterpackage_package_id", table_name="projectcharacterpackage")
    op.drop_index("ix_projectcharacterpackage_tenant_id", table_name="projectcharacterpackage")
    op.drop_table("projectcharacterpackage")

    op.drop_index("ix_projectscriptversion_version_type", table_name="projectscriptversion")
    op.drop_index("ix_projectscriptversion_project_id", table_name="projectscriptversion")
    op.drop_index("ix_projectscriptversion_version_id", table_name="projectscriptversion")
    op.drop_index("ix_projectscriptversion_tenant_id", table_name="projectscriptversion")
    op.drop_table("projectscriptversion")

    op.drop_index("ix_project_workflow_state", table_name="project")
    op.drop_column("project", "updated_at")
    op.drop_column("project", "final_video_url")
    op.drop_column("project", "production_job_id")
    op.drop_column("project", "selected_character_ids_json")
    op.drop_column("project", "character_package_approved_at")
    op.drop_column("project", "character_package_approved")
    op.drop_column("project", "script_approved_at")
    op.drop_column("project", "script_approved")
    op.drop_column("project", "script_draft")
    op.drop_column("project", "workflow_state")
    op.drop_column("project", "target_duration_minutes")
    op.drop_column("project", "genre")
    op.drop_column("project", "idea_prompt")
