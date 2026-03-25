from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.app.core.config import settings
from backend.app.utils.logger import get_logger

_logger = get_logger(__name__)

engine = create_async_engine(settings.database_url, echo=False, pool_size=5, max_overflow=10)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def init_db():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _logger.info("db.init_ok")
    except Exception as exc:
        _logger.warning("db.init_failed — running without database (valuations will not be saved)", extra={"error": str(exc)})
