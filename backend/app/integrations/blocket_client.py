import logging
from typing import Any

from backend.app.schemas.market_comparable import MarketComparable
from backend.app.utils import api_counter
from backend.app.utils.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

MIN_BLOCKET_PRICE_SEK = 300


class BlocketClient:
    """
    Fetches used-market listings from Blocket via the blocket-api package.

    The package makes direct HTTPS requests to Blocket's internal search API —
    no API key required. Results are active (buy-now / Torget) listings only;
    Blocket does not expose sold/completed listings through this endpoint.
    """

    def search(self, query: str) -> list[MarketComparable]:
        cache_key = f"blocket:{query}"
        cached = get_cached(cache_key)
        if cached is not None:
            logger.info("blocket.cache_hit query=%s count=%s", query, len(cached))
            return cached

        try:
            from blocket_api import BlocketAPI  # imported lazily so tests can mock easily
            api = BlocketAPI()
            response = api.search(query)
        except Exception as exc:
            logger.warning("blocket.search_failed query=%s reason=%s", query, exc)
            api_counter.increment_error("blocket")
            return []

        docs: list[dict[str, Any]] = response.get("docs") or []
        results = self._normalize(docs, query)

        logger.info(
            "blocket.results query=%s raw=%s kept=%s",
            query,
            len(docs),
            len(results),
        )
        api_counter.increment("blocket")
        set_cached(cache_key, results)
        return results

    def _normalize(self, docs: list[dict[str, Any]], query: str) -> list[MarketComparable]:
        comparables: list[MarketComparable] = []
        seen_ids: set[str] = set()

        for doc in docs:
            listing_id = str(doc.get("id") or "").strip()
            title = str(doc.get("heading") or "").strip()
            url = doc.get("canonical_url")

            if not listing_id or not title:
                continue

            if listing_id in seen_ids:
                continue

            price_obj = doc.get("price") or {}
            price_raw = price_obj.get("amount")
            try:
                price = float(price_raw)
            except (TypeError, ValueError):
                continue

            if price < MIN_BLOCKET_PRICE_SEK:
                logger.info(
                    "blocket.skip_low_price listing_id=%s price=%.0f title=%r",
                    listing_id,
                    price,
                    title,
                )
                continue

            currency = str(price_obj.get("currency_code") or "SEK").strip() or "SEK"

            seen_ids.add(listing_id)
            comparables.append(
                MarketComparable(
                    source="blocket",
                    listing_id=listing_id,
                    title=title,
                    price=price,
                    currency=currency,
                    status="active",
                    url=url,
                    ended_at=None,
                    shipping_cost=None,
                    condition_hint=None,
                    raw=doc,
                )
            )

        return comparables
