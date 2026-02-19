from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, inspect, text
from sqlmodel import SQLModel

from app.config import DATABASE_URL, ENVIRONMENT


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
    if "alembic_version" not in tables and "project" in tables:
        command.stamp(cfg, "0001_initial")

    command.upgrade(cfg, "head")


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

    # Newer tenant-aware billing model: one subscription per (tenant_id, user_id).
    _drop_index_if_exists("ix_subscriptionaccount_user_id")
    _drop_index_if_exists("ix_subscriptionaccount_tenant_user_id")
    _create_unique_index(
        "subscriptionaccount",
        "ix_subscriptionaccount_tenant_user_id",
        ["tenant_id", "user_id"],
    )
