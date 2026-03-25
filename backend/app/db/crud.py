from backend.app.utils.logger import get_logger

from .database import async_session
from .models import PriceSnapshot, Valuation

logger = get_logger(__name__)


async def save_valuation(data: dict) -> str | None:
    """Save valuation result. Returns ID or None if failed."""
    try:
        async with async_session() as session:
            valuation = Valuation(**data)
            session.add(valuation)
            await session.commit()
            logger.info("db.save_valuation.ok", extra={"valuation_id": data.get("id")})
            return valuation.id
    except Exception as exc:
        logger.error("db.save_valuation.error", extra={
            "valuation_id": data.get("id"),
            "error": str(exc),
        })
        return None  # NEVER crash the app if DB fails


async def save_price_snapshot(data: dict) -> str | None:
    """Save price snapshot for history tracking."""
    try:
        async with async_session() as session:
            snapshot = PriceSnapshot(**data)
            session.add(snapshot)
            await session.commit()
            logger.debug("db.save_price_snapshot.ok", extra={"product": data.get("product_identifier")})
            return snapshot.id
    except Exception as exc:
        logger.error("db.save_price_snapshot.error", extra={"error": str(exc)})
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
                logger.info("db.save_feedback.ok", extra={"valuation_id": valuation_id, "feedback": feedback})
    except Exception as exc:
        logger.error("db.save_feedback.error", extra={"valuation_id": valuation_id, "error": str(exc)})
