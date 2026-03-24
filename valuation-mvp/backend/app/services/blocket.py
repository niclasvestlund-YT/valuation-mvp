import asyncio
import logging
from ..models import MarketListing
from . import cache as _cache

logger = logging.getLogger(__name__)

CACHE_PREFIX = "blocket:"
MIN_PRICE_SEK = 500


async def search_listings(query: str) -> list[MarketListing]:
    cached = _cache.get_cached(f"{CACHE_PREFIX}{query}")
    if cached is not None:
        logger.info(f"Blocket cache hit for {query!r} ({len(cached)} results)")
        return cached

    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(_fetch, query),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        logger.warning(f"Blocket search timed out for {query!r}")
        return []
    except Exception as e:
        logger.warning(f"Blocket search error: {e}")
        return []

    _cache.set_cached(f"{CACHE_PREFIX}{query}", results)
    logger.info(f"Blocket: {len(results)} listings for {query!r}")
    return results


def _fetch(query: str) -> list[MarketListing]:
    from blocket_api import BlocketAPI  # imported here to isolate any import errors

    api = BlocketAPI()
    data = api.search(query)
    docs = data.get("docs", [])

    listings: list[MarketListing] = []
    for doc in docs:
        price_info = doc.get("price") or {}
        amount = price_info.get("amount")
        if not amount or amount < MIN_PRICE_SEK:
            continue
        title = doc.get("heading", "")
        url = doc.get("canonical_url")
        listings.append(MarketListing(
            title=title,
            price=float(amount),
            source="blocket",
            url=url,
            status="active",
        ))

    return listings
