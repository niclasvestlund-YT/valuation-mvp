from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.app.core.config import settings
from backend.app.utils.logger import get_logger

_logger = get_logger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,          # detect stale connections after PG restart
    pool_recycle=1800,            # recycle connections every 30 min
)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def init_db():
    """Verify database connectivity on startup.

    Tables are managed exclusively by Alembic migrations.
    We no longer call Base.metadata.create_all() because it
    bypasses migration history and causes "column already exists"
    or "column does not exist" errors when the model and migration
    drift apart.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        _logger.info("db.init_ok")
    except Exception as exc:
        _logger.warning(
            "db.init_failed — running without database (valuations will not be saved)",
            extra={"error": str(exc)},
        )


async def dispose_engine():
    """Dispose the engine's connection pool.  Call on shutdown."""
    await engine.dispose()
    _logger.info("db.engine_disposed")
