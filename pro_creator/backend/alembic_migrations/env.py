from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlmodel import SQLModel

from app.config import DATABASE_URL
from app import models  # noqa: F401 - ensure SQLModel metadata is populated

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _get_url() -> str:
    # Prefer explicit sqlalchemy.url for CLI runs, otherwise fall back to app config.
    url = config.get_main_option("sqlalchemy.url")
    return url or DATABASE_URL


def run_migrations_offline() -> None:
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _ensure_postgres_version_column_capacity(connection) -> None:
    """Ensure long descriptive Alembic revision IDs fit in PostgreSQL."""
    if connection.dialect.name != "postgresql":
        return

    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(128) NOT NULL PRIMARY KEY)"
        )
    )
    connection.execute(
        text(
            "ALTER TABLE alembic_version "
            "ALTER COLUMN version_num TYPE VARCHAR(128)"
        )
    )
    connection.commit()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _ensure_postgres_version_column_capacity(connection)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
