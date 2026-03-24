import logging

from .database import async_session
from .models import PriceSnapshot, Valuation

logger = logging.getLogger(__name__)


async def save_valuation(data: dict) -> str | None:
    """Save valuation result. Returns ID or None if failed."""
    try:
        async with async_session() as session:
            valuation = Valuation(**data)
            session.add(valuation)
            await session.commit()
            return valuation.id
    except Exception as e:
        logger.error(f"Failed to save valuation: {e}")
        return None  # NEVER crash the app if DB fails


async def save_price_snapshot(data: dict) -> str | None:
    """Save price snapshot for history tracking."""
    try:
        async with async_session() as session:
            snapshot = PriceSnapshot(**data)
            session.add(snapshot)
            await session.commit()
            return snapshot.id
    except Exception as e:
        logger.error(f"Failed to save snapshot: {e}")
        return None


async def save_feedback(valuation_id: str, feedback: str, corrected_product: str | None = None) -> None:
    """Save user feedback on a valuation."""
    try:
        async with async_session() as session:
            val = await session.get(Valuation, valuation_id)
            if val:
                val.feedback = feedback
                val.corrected_product = corrected_product
                await session.commit()
    except Exception as e:
        logger.error(f"Failed to save feedback: {e}")
