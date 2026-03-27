"""Facebook Marketplace client via DuckDuckGo index.

No API key or FB account needed. Searches DDG for FB Marketplace pages
and extracts prices from snippets. Two strategies:
1. Item searches — individual listings with prices
2. Category aggregate pages — multiple prices in one snippet
"""

import hashlib
import re

from backend.app.schemas.market_comparable import MarketComparable
from backend.app.utils.cache import get_cached, set_cached
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

# FB Marketplace category slugs matching product_knowledge.json
CATEGORY_SLUGS = {
    "headphones": "headphones",
    "smartphone": "cell-phones",
    "laptop": "laptops",
    "camera": "cameras",
    "tablet": "tablets",
    "gaming": "video-games",
    "smartwatch": "smart-watches",
    "speaker": "electronics",
    "appliance": "electronics",
}


def _parse_prices_from_snippet(snippet: str) -> list[int]:
    """Extract SEK prices from FB snippet text.

    Handles: SEK3,900 / SEK3900 / 3 900 kr / 3900:-
    """
    prices: list[int] = []
    # Format: SEK3,900 or SEK3900
    for m in re.finditer(r"SEK\s?(\d[\d,\s]{1,6})", snippet):
        val = int(re.sub(r"[\s,]", "", m.group(1)))
        if 100 < val < 200_000:
            prices.append(val)
    # Format: 3 900 kr or 3900 kr or 3900:-
    for m in re.finditer(r"(\d[\d\s]{2,6})\s?(?:kr|:-)", snippet, re.IGNORECASE):
        val = int(re.sub(r"\s", "", m.group(1)))
        if 100 < val < 200_000:
            prices.append(val)
    return list(set(prices))


def _build_queries(product_name: str, category: str | None) -> list[str]:
    """Build 3 optimized queries for maximum hit volume."""
    slug = CATEGORY_SLUGS.get(category or "", "electronics")
    return [
        # Query 1: item search with product name (individual listings with price)
        f'site:facebook.com/marketplace/item "{product_name}" SEK',
        # Query 2: category page Stockholm (aggregate page with many prices in snippet)
        f"site:facebook.com/marketplace/stockholm/{slug}",
        # Query 3: national category page with product name
        f'site:facebook.com/marketplace "{product_name}" Sweden SEK',
    ]


class FacebookMarketplaceClient:
    """Fetches FB Marketplace prices via DuckDuckGo index. No API key needed."""

    def search(self, product_name: str, category: str | None = None) -> list[MarketComparable]:
        cache_key = f"fb_mp:{product_name}:{category}"
        cached = get_cached(cache_key)
        if cached is not None:
            logger.info("fb_marketplace.cache_hit query=%s count=%s", product_name, len(cached))
            return cached

        queries = _build_queries(product_name, category)
        all_results: list[dict] = []

        try:
            from duckduckgo_search import DDGS

            ddgs = DDGS()
            for q in queries:
                try:
                    hits = ddgs.text(q, region="se-sv", safesearch="off", max_results=5)
                    all_results.extend(hits or [])
                except Exception as exc:
                    logger.warning("fb_marketplace.ddg_query_failed query=%r error=%s", q, exc)
        except Exception as exc:
            logger.error("fb_marketplace.ddg_init_failed error=%s", exc)
            return []

        comparables = self._normalize(all_results, product_name)

        logger.info(
            "fb_marketplace.results query=%s raw=%s kept=%s",
            product_name,
            len(all_results),
            len(comparables),
        )
        set_cached(cache_key, comparables)
        return comparables

    def _normalize(self, results: list[dict], product_name: str) -> list[MarketComparable]:
        comparables: list[MarketComparable] = []
        seen: set[tuple[int, str]] = set()

        for r in results:
            snippet = (r.get("body") or "") + " " + (r.get("title") or "")
            prices = _parse_prices_from_snippet(snippet)
            title = r.get("title") or ""
            url = r.get("href") or ""

            for price in prices:
                dedup_key = (price, url)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                # Generate a stable listing_id from url + price
                listing_id = hashlib.md5(f"{url}:{price}".encode()).hexdigest()[:16]

                comparables.append(
                    MarketComparable(
                        source="Facebook Marketplace",
                        listing_id=listing_id,
                        title=title,
                        price=float(price),
                        currency="SEK",
                        status="active",
                        url=url,
                        ended_at=None,
                        shipping_cost=None,
                        condition_hint="used",
                        raw={
                            "snippet": snippet.strip(),
                            "product_query": product_name,
                        },
                    )
                )

        return comparables
