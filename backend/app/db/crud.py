from backend.app.utils.logger import get_logger

from .database import async_session
from .models import PriceSnapshot, Valuation

logger = get_logger(__name__)

# Only allow known Valuation column names to prevent accidental injection via **data
_VALUATION_FIELDS = frozenset(c.name for c in Valuation.__table__.columns)
_SNAPSHOT_FIELDS = frozenset(c.name for c in PriceSnapshot.__table__.columns)


async def save_valuation(data: dict) -> str | None:
    """Save valuation result. Returns ID or None if failed."""
    try:
        # Strip unknown keys to avoid TypeError on Valuation(**data)
        clean = {k: v for k, v in data.items() if k in _VALUATION_FIELDS}
        async with async_session() as session:
            async with session.begin():
                valuation = Valuation(**clean)
                session.add(valuation)
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
        clean = {k: v for k, v in data.items() if k in _SNAPSHOT_FIELDS}
        async with async_session() as session:
            async with session.begin():
                snapshot = PriceSnapshot(**clean)
                session.add(snapshot)
            logger.debug("db.save_price_snapshot.ok", extra={"product": data.get("product_identifier")})
            return snapshot.id
    except Exception as exc:
        logger.error("db.save_price_snapshot.error", extra={"error": str(exc)})
        return None


async def save_feedback(valuation_id: str, feedback: str, corrected_product: str | None = None) -> bool:
    """Save user feedback on a valuation. Returns True if saved, False if not found or error."""
    try:
        async with async_session() as session:
            val = await session.get(Valuation, valuation_id)
            if not val:
                logger.warning(
                    "db.save_feedback.not_found",
                    extra={"valuation_id": valuation_id, "feedback": feedback},
                )
                return False
            val.feedback = feedback
            val.corrected_product = corrected_product
            await session.commit()
            logger.info("db.save_feedback.ok", extra={"valuation_id": valuation_id, "feedback": feedback})
            return True
    except Exception as exc:
        logger.error("db.save_feedback.error", extra={"valuation_id": valuation_id, "error": str(exc)})
        return False
