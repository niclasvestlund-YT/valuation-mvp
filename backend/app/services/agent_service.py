"""Agent service — parses user intent and builds context from own database only.

NEVER calls external APIs (Tradera, Blocket, Serper, etc.).
All data comes from pre-crawled PostgreSQL tables.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func

from backend.app.core.thresholds import (
    AGENT_CONTEXT_MAX_COMPARABLES,
    AGENT_DATA_MAX_AGE_DAYS,
    AGENT_MIN_COMPARABLES_FOR_ESTIMATE,
)
from backend.app.db.database import async_session
from backend.app.db.models import MarketComparable as MarketComparableModel
from backend.app.db.models import NewPriceSnapshot, Product
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AgentIntent:
    product_key: str | None = None
    candidates: list = field(default_factory=list)
    raw_message: str = ""


async def parse_user_intent(user_message: str) -> AgentIntent:
    """Match user message against product table. No LLM call — just DB lookup."""
    normalized = " ".join(user_message.lower().split())
    intent = AgentIntent(raw_message=user_message)

    try:
        async with async_session() as session:
            # Try exact product_key match first
            products = (await session.execute(select(Product))).scalars().all()

            best_match = None
            best_score = 0
            candidates = []

            for p in products:
                brand_lower = (p.brand or "").lower()
                model_lower = (p.model or "").lower()
                key_lower = (p.product_key or "").lower()

                # Exact key in message
                if key_lower in normalized.replace(" ", "-").replace("_", "-"):
                    best_match = p
                    best_score = 100
                    break

                # Count matching tokens
                tokens = set(brand_lower.split() + model_lower.split())
                significant = {t for t in tokens if len(t) >= 3 or any(c.isdigit() for c in t)}
                if not significant:
                    continue

                matches = sum(1 for t in significant if t in normalized)
                score = matches / len(significant) if significant else 0

                if score >= 0.8 and matches >= 2:
                    if score > best_score:
                        best_match = p
                        best_score = score
                elif score >= 0.5 and matches >= 1:
                    candidates.append(p)

            if best_match:
                intent.product_key = best_match.product_key
                logger.info("agent.intent_parsed", extra={
                    "product_key": best_match.product_key,
                    "score": best_score,
                })
            elif candidates:
                # Deduplicate and limit
                seen = set()
                for c in candidates:
                    if c.product_key not in seen:
                        seen.add(c.product_key)
                        intent.candidates.append(c)
                    if len(intent.candidates) >= 5:
                        break
                logger.info("agent.intent_ambiguous", extra={
                    "candidates": len(intent.candidates),
                })
            else:
                logger.info("agent.intent_no_match", extra={"message": normalized[:80]})

    except Exception as exc:
        logger.error("agent.intent_parse_failed", extra={"error": str(exc)})

    return intent


async def build_context_block(product_key: str) -> str:
    """Pre-query ALL relevant data for the product from own database."""
    try:
        async with async_session() as session:
            # Product identity
            product = await session.get(Product, product_key)
            if not product:
                return f"INGEN DATA TILLGÄNGLIG.\nProdukten '{product_key}' finns inte i databasen."

            # Market comparables (last N days, unflagged)
            cutoff = datetime.now(timezone.utc) - timedelta(days=AGENT_DATA_MAX_AGE_DAYS)
            result = await session.execute(
                select(MarketComparableModel)
                .where(
                    MarketComparableModel.product_key == product_key,
                    MarketComparableModel.flagged.is_(False),
                    MarketComparableModel.last_seen >= cutoff,
                )
                .order_by(MarketComparableModel.last_seen.desc())
                .limit(AGENT_CONTEXT_MAX_COMPARABLES)
            )
            comparables = result.scalars().all()

            active = [c for c in comparables if c.is_active]
            sold = [c for c in comparables if c.disappeared_at is not None]

            # Price statistics
            prices = [c.price_sek for c in comparables]
            if prices:
                sorted_prices = sorted(prices)
                median_price = sorted_prices[len(sorted_prices) // 2]
                min_price = sorted_prices[0]
                max_price = sorted_prices[-1]
                p25 = sorted_prices[len(sorted_prices) // 4]
                p75 = sorted_prices[3 * len(sorted_prices) // 4]
            else:
                median_price = min_price = max_price = p25 = p75 = None

            # Sold-only prices
            sold_prices = [c.price_sek for c in sold]

            # New price
            np_result = await session.execute(
                select(NewPriceSnapshot)
                .where(NewPriceSnapshot.product_key == product_key)
                .order_by(NewPriceSnapshot.fetched_at.desc())
                .limit(1)
            )
            new_price = np_result.scalar_one_or_none()

            # Source breakdown
            tradera_count = len([c for c in comparables if "tradera" in (c.source or "").lower()])
            blocket_count = len([c for c in comparables if "blocket" in (c.source or "").lower()])
            other_count = len(comparables) - tradera_count - blocket_count

            # Data freshness
            newest = max((c.last_seen for c in comparables), default=None)
            oldest = min((c.first_seen for c in comparables), default=None)

            # Build context string
            context = f"""PRODUKT: {product.brand} {product.model}
Kategori: {product.category or "Okänd"}
Antal värderingar vi gjort: {product.valuation_count}

BEGAGNATPRISER (senaste {AGENT_DATA_MAX_AGE_DAYS} dagarna):
Antal jämförelseobjekt: {len(comparables)}
  - Tradera: {tradera_count} st
  - Blocket: {blocket_count} st"""

            if other_count > 0:
                context += f"\n  - Övriga: {other_count} st"

            context += f"""
  - Varav aktiva annonser: {len(active)} st
  - Varav troliga försäljningar (försvunna): {len(sold)} st
"""

            if prices:
                context += f"""
Prisstatistik (alla):
  - Lägsta: {min_price} kr
  - Högsta: {max_price} kr
  - Median: {median_price} kr
  - 25:e percentil: {p25} kr
  - 75:e percentil: {p75} kr
"""
            else:
                context += "\nIngen prisdata tillgänglig.\n"

            if sold_prices:
                sold_sorted = sorted(sold_prices)
                sold_median = sold_sorted[len(sold_sorted) // 2]
                context += f"""
Prisstatistik (bara bekräftade försäljningar):
  - Antal: {len(sold_prices)} st
  - Median: {sold_median} kr
  - Lägsta: {min(sold_prices)} kr
  - Högsta: {max(sold_prices)} kr
"""

            if new_price:
                context += f"""
NYPRIS:
  - Lägsta nya pris: {new_price.price_sek} kr
  - Källa: {new_price.source}
  - Hämtat: {new_price.fetched_at.strftime('%Y-%m-%d') if new_price.fetched_at else 'Okänt'}
"""

            context += f"""
DATAFÖRSKHET:
  - Nyaste datapunkt: {newest.strftime('%Y-%m-%d %H:%M') if newest else 'Saknas'}
  - Äldsta datapunkt: {oldest.strftime('%Y-%m-%d') if oldest else 'Saknas'}
"""

            if len(comparables) < AGENT_MIN_COMPARABLES_FOR_ESTIMATE:
                context += f"\nVARNING: Färre än {AGENT_MIN_COMPARABLES_FOR_ESTIMATE} jämförelseobjekt. Begränsad data.\n"

            # Top 5 listings
            ranked = sorted(comparables, key=lambda c: c.relevance_score or 0, reverse=True)[:5]
            if ranked:
                context += "\nTOP 5 JÄMFÖRELSEOBJEKT:\n"
                for c in ranked:
                    status = "SÅLD" if c.disappeared_at else "AKTIV"
                    seen_date = c.last_seen.strftime("%Y-%m-%d") if c.last_seen else "?"
                    context += f"  - [{status}] {c.title} — {c.price_sek} kr ({c.source}, {seen_date})\n"

            return context

    except Exception as exc:
        logger.error("agent.build_context_failed", extra={"product_key": product_key, "error": str(exc)})
        return f"FEL VID DATAHÄMTNING.\nKunde inte hämta data för '{product_key}': {exc}"


async def build_no_data_context(user_message: str, candidates: list | None = None) -> str:
    """Build context when we can't match a product or have no data."""
    if candidates:
        names = "\n".join([f"  - {c.brand} {c.model}" for c in candidates])
        return f"""INGEN EXAKT MATCHNING HITTAD.
Användaren sa: "{user_message}"

Möjliga produkter i vår databas:
{names}

Be användaren förtydliga vilken produkt de menar."""
    else:
        return f"""INGEN DATA TILLGÄNGLIG.
Användaren sa: "{user_message}"

Vi har inte denna produkt i vår databas. Vi kan inte ge ett prisestimat.
Förklara att vi inte har data för denna produkt ännu, och föreslå att
de provar att ladda upp ett foto via huvudflödet istället — det kan
trigga en sökning mot marknadsplatser i realtid."""


async def count_comparables(product_key: str) -> int:
    """Count unflagged comparables for a product."""
    try:
        async with async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(MarketComparableModel)
                .where(
                    MarketComparableModel.product_key == product_key,
                    MarketComparableModel.flagged.is_(False),
                )
            )
            return result.scalar() or 0
    except Exception:
        return 0
