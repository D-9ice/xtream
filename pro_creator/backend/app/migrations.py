from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, inspect, text
from sqlmodel import SQLModel

from app.config import DATABASE_URL, ENVIRONMENT


def _column_names(inspector, table: str) -> set[str]:
    try:
        return {column["name"] for column in inspector.get_columns(table)}
    except Exception:
        return set()


def _infer_existing_revision(inspector) -> str | None:
    tables = set(inspector.get_table_names())
    if "project" not in tables:
        return None

    project_columns = _column_names(inspector, "project")
    if not project_columns:
        return None

    if "archived_at" in project_columns:
        return "0006_workflow_project_archive"

    character_columns = _column_names(inspector, "characterprofile")
    if "reference_image_urls_json" in character_columns:
        return "0005_character_reference_bundles"

    if "workflow_state" in project_columns:
        return "0004_workflow_upgrade"

    tenant_tables = {
        "project",
        "scene",
        "clip",
        "orchestrationjob",
        "orchestrationschedule",
        "subscriptionaccount",
        "creditledgerentry",
    }
    if tenant_tables.issubset(tables) and all(
        "tenant_id" in _column_names(inspector, table) for table in tenant_tables
    ):
        return "0002_add_tenant_id"

    return None


def upgrade_head(engine: Engine) -> None:
    """
    Preferred path: Alembic migrations.

    Fallback path: best-effort schema sync (for restricted/offline dev environments
    where new Python deps cannot be installed).
    """

    try:
        from alembic import command  # type: ignore
        from alembic.config import Config  # type: ignore
    except Exception:
        if ENVIRONMENT == "production":
            raise RuntimeError(
                "Alembic is required in production but is not available. "
                "Install backend dependencies (including alembic) and run migrations."
            )
        _fallback_schema_sync(engine)
        return

    base_dir = Path(__file__).resolve().parents[0]  # backend/app
    backend_dir = base_dir.parent  # backend/
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "alembic_migrations"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

    # Bootstrap legacy databases created before Alembic existed by stamping
    # to the closest baseline revision, then applying forward migrations.
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    inferred_revision = _infer_existing_revision(inspector)
    if "alembic_version" not in tables and "project" in tables:
        command.stamp(cfg, inferred_revision or "0001_initial")
    elif "alembic_version" in tables and inferred_revision:
        with engine.connect() as conn:
            current_revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if current_revision and current_revision != inferred_revision:
            revision_order = {
                "0001_initial": 1,
                "0002_add_tenant_id": 2,
                "0003_subscription_tenant_user_unique": 3,
                "0004_workflow_upgrade": 4,
                "0005_character_reference_bundles": 5,
                "0006_workflow_project_archive": 6,
            }
            if revision_order.get(inferred_revision, 0) > revision_order.get(str(current_revision), 0):
                command.stamp(cfg, inferred_revision)

    command.upgrade(cfg, "head")

    if ENVIRONMENT != "production":
        _fallback_schema_sync(engine)


def _fallback_schema_sync(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    inspector = inspect(engine)

    def _ensure_column(table: str, col: str, ddl: str) -> None:
        try:
            columns = {c["name"] for c in inspector.get_columns(table)}
        except Exception:
            return
        if col in columns:
            return
        with engine.connect() as conn:
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception:
                # Best effort only; schema drift should be fixed by Alembic in real deployments.
                pass

    def _drop_index_if_exists(index_name: str) -> None:
        with engine.connect() as conn:
            try:
                conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                conn.commit()
            except Exception:
                pass

    def _create_unique_index(table: str, index_name: str, cols: list[str]) -> None:
        joined = ", ".join(cols)
        with engine.connect() as conn:
            try:
                conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table} ({joined})"))
                conn.commit()
            except Exception:
                pass

    # Legacy fields previously maintained via ad-hoc alters.
    _ensure_column("orchestrationjob", "task_id", "ALTER TABLE orchestrationjob ADD COLUMN task_id TEXT")
    _ensure_column(
        "subscriptionaccount",
        "credits_reserved",
        "ALTER TABLE subscriptionaccount ADD COLUMN credits_reserved INTEGER DEFAULT 0",
    )

    # Phase 1 tenant-ready columns.
    tenant_tables = [
        "project",
        "scene",
        "clip",
        "orchestrationjob",
        "orchestrationschedule",
        "subscriptionaccount",
        "creditledgerentry",
    ]
    for table in tenant_tables:
        _ensure_column(
            table,
            "tenant_id",
            f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'",
        )

    # Guided workflow project fields.
    _ensure_column("project", "idea_prompt", "ALTER TABLE project ADD COLUMN idea_prompt TEXT")
    _ensure_column("project", "genre", "ALTER TABLE project ADD COLUMN genre TEXT")
    _ensure_column(
        "project",
        "target_duration_minutes",
        "ALTER TABLE project ADD COLUMN target_duration_minutes INTEGER",
    )
    _ensure_column(
        "project",
        "workflow_state",
        "ALTER TABLE project ADD COLUMN workflow_state TEXT NOT NULL DEFAULT 'draft'",
    )
    _ensure_column("project", "script_draft", "ALTER TABLE project ADD COLUMN script_draft TEXT")
    _ensure_column("project", "script_approved", "ALTER TABLE project ADD COLUMN script_approved TEXT")
    _ensure_column(
        "project",
        "script_approved_at",
        "ALTER TABLE project ADD COLUMN script_approved_at DATETIME",
    )
    _ensure_column(
        "project",
        "character_package_approved",
        "ALTER TABLE project ADD COLUMN character_package_approved BOOLEAN NOT NULL DEFAULT 0",
    )
    _ensure_column(
        "project",
        "character_package_approved_at",
        "ALTER TABLE project ADD COLUMN character_package_approved_at DATETIME",
    )
    _ensure_column(
        "project",
        "selected_character_ids_json",
        "ALTER TABLE project ADD COLUMN selected_character_ids_json TEXT",
    )
    _ensure_column(
        "project",
        "production_job_id",
        "ALTER TABLE project ADD COLUMN production_job_id TEXT",
    )
    _ensure_column(
        "project",
        "final_video_url",
        "ALTER TABLE project ADD COLUMN final_video_url TEXT",
    )
    _ensure_column(
        "project",
        "archived_at",
        "ALTER TABLE project ADD COLUMN archived_at DATETIME",
    )
    _ensure_column(
        "project",
        "updated_at",
        "ALTER TABLE project ADD COLUMN updated_at DATETIME",
    )
    _ensure_column(
        "characterprofile",
        "reference_image_urls_json",
        "ALTER TABLE characterprofile ADD COLUMN reference_image_urls_json TEXT NOT NULL DEFAULT '[]'",
    )

    # Newer tenant-aware billing model: one subscription per (tenant_id, user_id).
    _drop_index_if_exists("ix_subscriptionaccount_user_id")
    _drop_index_if_exists("ix_subscriptionaccount_tenant_user_id")
    _create_unique_index(
        "subscriptionaccount",
        "ix_subscriptionaccount_tenant_user_id",
        ["tenant_id", "user_id"],
    )
