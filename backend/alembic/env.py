import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Ensure the project root is on sys.path so backend.app imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.db.database import Base  # noqa: E402
import backend.app.db.models  # noqa: E402, F401 — registers models on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Allow DATABASE_URL env var to override alembic.ini (use sync psycopg2 URL for migrations)
_db_url = os.getenv("DATABASE_URL", "")
if _db_url:
    # Normalize any async driver to sync psycopg2 for Alembic
    _sync_url = _db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    config.set_main_option("sqlalchemy.url", _sync_url)
else:
    import warnings
    warnings.warn(
        "DATABASE_URL not set — Alembic will use the fallback URL from alembic.ini. "
        "Set DATABASE_URL in your .env for reliable migrations.",
        stacklevel=1,
    )


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
