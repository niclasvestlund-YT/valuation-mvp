"""Vinted client — fetches used-market listings from vinted.se.

Uses curl_cffi to impersonate a real browser (bypasses bot detection).
Prices are in EUR, converted to SEK with a fixed rate.
"""

import asyncio
import hashlib
import logging
from typing import Any

from backend.app.schemas.market_comparable import MarketComparable
from backend.app.utils import api_counter
from backend.app.utils.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

VINTED_BASE_URL = "https://www.vinted.se"
VINTED_SEARCH_URL = "https://www.vinted.se/api/v2/catalog/items"
VINTED_EUR_TO_SEK: float = 11.5
VINTED_PER_PAGE: int = 20
VINTED_REQUEST_TIMEOUT: float = 8.0
VINTED_TOTAL_TIMEOUT: float = 10.0
VINTED_CACHE_TTL: int = 3600
VINTED_MIN_PRICE_SEK: float = 100.0
VINTED_MAX_PRICE_SEK: float = 200_000.0


def _fetch_sync(product_name: str) -> list[dict]:
    """Synchronous helper — fetches Vinted listings via curl_cffi."""
    from curl_cffi import requests as cf_requests

    session = cf_requests.Session()
    # Step 1: fetch session cookie
    session.get(VINTED_BASE_URL, impersonate="chrome", timeout=VINTED_REQUEST_TIMEOUT)
    # Step 2: search listings
    response = session.get(
        VINTED_SEARCH_URL,
        params={"search_text": product_name, "per_page": VINTED_PER_PAGE},
        impersonate="chrome",
        timeout=VINTED_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    items = response.json().get("items") or []

    results: list[dict] = []
    for item in items:
        try:
            price_eur = float(item.get("price") or item.get("total_item_price") or 0)
        except (TypeError, ValueError):
            continue
        if price_eur <= 0:
            continue
        title = str(item.get("title") or "").strip()
        url = item.get("url") or ""
        if url and not url.startswith("http"):
            url = f"{VINTED_BASE_URL}{url}"
        results.append({
            "title": title,
            "price_eur": price_eur,
            "url": url,
            "raw": item,
        })
    return results


async def fetch_vinted(
    product_name: str,
    category: str | None = None,
) -> list[MarketComparable]:
    """Fetch Vinted listings. Returns [] on any error — never raises."""
    cache_key = f"vinted:{product_name.lower().strip()}"
    cached = get_cached(cache_key)
    if cached is not None:
        logger.info("vinted.cache_hit query=%s count=%s", product_name, len(cached))
        return cached

    try:
        loop = asyncio.get_running_loop()
        raw = await asyncio.wait_for(
            loop.run_in_executor(None, _fetch_sync, product_name),
            timeout=VINTED_TOTAL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("vinted.timeout query=%s", product_name)
        api_counter.increment_error("vinted")
        return []
    except Exception as exc:
        if "403" in str(exc):
            logger.warning("Vinted: 403 — Railway-IP troligen flaggad av Datadome")
        else:
            logger.warning("vinted.fetch_failed query=%s error=%s", product_name, exc)
        api_counter.increment_error("vinted")
        return []

    # Convert EUR → SEK, filter, build MarketComparable
    comparables: list[MarketComparable] = []
    seen: set[tuple[int, str]] = set()

    for item in raw:
        price_sek = round(item["price_eur"] * VINTED_EUR_TO_SEK)
        if price_sek < VINTED_MIN_PRICE_SEK or price_sek > VINTED_MAX_PRICE_SEK:
            continue

        title = item.get("title") or ""
        dedup_key = (price_sek, title[:30])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        url = item.get("url") or ""
        listing_id = hashlib.md5(f"{url}:{price_sek}".encode()).hexdigest()[:16]

        comparables.append(
            MarketComparable(
                source="Vinted",
                listing_id=listing_id,
                title=title,
                price=float(price_sek),
                currency="SEK",
                status="active",
                url=url,
                ended_at=None,
                shipping_cost=None,
                condition_hint=None,
                raw=item.get("raw") or {},
            )
        )

    logger.info("Vinted: %d träffar för '%s'", len(comparables), product_name)
    api_counter.increment("vinted")
    set_cached(cache_key, comparables)
    return comparables
