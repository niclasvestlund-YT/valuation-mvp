from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from backend.app.services.data_validator import validate_comparable
from backend.app.utils.logger import get_logger

from .database import async_session
from .models import MarketComparable, NewPriceSnapshot, PriceSnapshot, Product, Valuation

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


async def upsert_product(product_key: str, brand: str, model: str, category: str | None = None) -> bool:
    """Create or update product entry. Increment valuation_count."""
    try:
        async with async_session() as session:
            product = await session.get(Product, product_key)
            now = datetime.now(timezone.utc)
            if product:
                product.valuation_count = (product.valuation_count or 0) + 1
                product.last_seen = now
                if category and not product.category:
                    product.category = category
            else:
                product = Product(
                    product_key=product_key,
                    brand=brand,
                    model=model,
                    category=category,
                    valuation_count=1,
                    first_seen=now,
                    last_seen=now,
                )
                session.add(product)
            await session.commit()
            return True
    except Exception as exc:
        logger.error("db.upsert_product.error", extra={"product_key": product_key, "error": str(exc)})
        return False


async def upsert_comparables(
    product_key: str,
    comparables: list[dict],
    source: str,
) -> dict:
    """Validate and upsert comparables. Returns counts dict."""
    counts = {"inserted": 0, "updated": 0, "rejected": 0, "flagged": 0}
    try:
        async with async_session() as session:
            # Get existing median for outlier detection
            existing = await session.execute(
                select(MarketComparable.price_sek).where(
                    MarketComparable.product_key == product_key,
                    MarketComparable.is_active.is_(True),
                )
            )
            existing_prices = [row[0] for row in existing]
            existing_median = sorted(existing_prices)[len(existing_prices) // 2] if existing_prices else None

            seen_urls = set()
            now = datetime.now(timezone.utc)

            for comp in comparables:
                url = comp.get("url") or comp.get("listing_url") or ""
                title = comp.get("title") or ""
                price = int(comp.get("price") or comp.get("price_sek") or 0)

                if not url:
                    counts["rejected"] += 1
                    continue

                result = validate_comparable(title, price, product_key, existing_median)
                if not result.valid:
                    counts["rejected"] += 1
                    continue

                seen_urls.add(url)

                # Check if exists
                row = await session.execute(
                    select(MarketComparable).where(MarketComparable.listing_url == url)
                )
                existing_comp = row.scalar_one_or_none()

                flagged = bool(result.warnings)
                flag_reason = ", ".join(result.warnings) if result.warnings else None

                if existing_comp:
                    existing_comp.last_seen = now
                    existing_comp.price_sek = price
                    existing_comp.is_active = True
                    existing_comp.disappeared_at = None
                    if flagged:
                        existing_comp.flagged = True
                        existing_comp.flag_reason = flag_reason
                    counts["updated"] += 1
                else:
                    new_comp = MarketComparable(
                        product_key=product_key,
                        source=source,
                        listing_url=url,
                        title=title,
                        price_sek=price,
                        condition=comp.get("condition"),
                        relevance_score=comp.get("relevance_score"),
                        is_active=True,
                        flagged=flagged,
                        flag_reason=flag_reason,
                        first_seen=now,
                        last_seen=now,
                    )
                    session.add(new_comp)
                    counts["inserted"] += 1

                if flagged:
                    counts["flagged"] += 1

            # Mark disappeared listings
            if seen_urls:
                await session.execute(
                    update(MarketComparable)
                    .where(
                        MarketComparable.product_key == product_key,
                        MarketComparable.source == source,
                        MarketComparable.is_active.is_(True),
                        MarketComparable.listing_url.not_in(seen_urls),
                    )
                    .values(is_active=False, disappeared_at=now)
                )

            await session.commit()
            logger.info("db.upsert_comparables.ok", extra={
                "product_key": product_key, "source": source, **counts,
            })
    except Exception as exc:
        logger.error("db.upsert_comparables.error", extra={"product_key": product_key, "error": str(exc)})
    return counts


async def get_cached_comparables(product_key: str, max_age_hours: int = 48) -> list[dict]:
    """Return cached comparables seen within max_age_hours."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        async with async_session() as session:
            result = await session.execute(
                select(MarketComparable).where(
                    MarketComparable.product_key == product_key,
                    MarketComparable.last_seen >= cutoff,
                )
            )
            rows = result.scalars().all()
            return [
                {
                    "title": r.title,
                    "price": r.price_sek,
                    "price_sek": r.price_sek,
                    "url": r.listing_url,
                    "source": r.source,
                    "condition": r.condition,
                    "relevance_score": r.relevance_score,
                    "is_active": r.is_active,
                    "disappeared_at": r.disappeared_at.isoformat() if r.disappeared_at else None,
                }
                for r in rows
            ]
    except Exception as exc:
        logger.error("db.get_cached_comparables.error", extra={"product_key": product_key, "error": str(exc)})
        return []


async def upsert_new_price(
    product_key: str,
    price_sek: int,
    source: str,
    currency: str = "SEK",
    url: str | None = None,
    title: str | None = None,
) -> bool:
    """Store new price snapshot."""
    try:
        async with async_session() as session:
            snapshot = NewPriceSnapshot(
                product_key=product_key,
                source=source,
                price_sek=price_sek,
                currency=currency,
                url=url,
                title=title,
            )
            session.add(snapshot)
            await session.commit()
            return True
    except Exception as exc:
        logger.error("db.upsert_new_price.error", extra={"product_key": product_key, "error": str(exc)})
        return False


async def get_latest_new_price(product_key: str) -> dict | None:
    """Return most recent new price for product, or None."""
    try:
        async with async_session() as session:
            result = await session.execute(
                select(NewPriceSnapshot)
                .where(NewPriceSnapshot.product_key == product_key)
                .order_by(NewPriceSnapshot.fetched_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            return {
                "price_sek": row.price_sek,
                "currency": row.currency,
                "source": row.source,
                "url": row.url,
                "title": row.title,
                "fetched_at": row.fetched_at,
            }
    except Exception as exc:
        logger.error("db.get_latest_new_price.error", extra={"product_key": product_key, "error": str(exc)})
        return None
