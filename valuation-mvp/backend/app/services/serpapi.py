import logging
import statistics
import httpx
from ..models import MarketListing

logger = logging.getLogger(__name__)

SERPAPI_ENDPOINT = "https://serpapi.com/search"

# Sources that are NOT trustworthy for new-price reference
UNTRUSTED_SOURCES = {
    "ebay", "wish", "aliexpress", "temu", "dhgate", "banggood",
    "gearbest", "joom", "shein",
}

# Preferred official retailers for new-price (higher priority)
TRUSTED_RETAILERS = {
    "webhallen", "elgiganten", "mediamarkt", "media markt",
    "amazon", "amazon.se", "prisjakt", "inet", "dustin",
    "komplett", "power", "apple", "samsung", "sony",
}

MIN_ELECTRONICS_PRICE = 500  # kr — anything below is likely an accessory or junk listing


async def search_market_data(query: str, api_key: str) -> list[MarketListing]:
    params = {
        "engine": "google_shopping",
        "q": f"{query} begagnad used",
        "gl": "se",
        "hl": "sv",
        "api_key": api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(SERPAPI_ENDPOINT, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning(f"SerpApi market data error: {e}")
        return []

    listings = []
    for result in data.get("shopping_results", []):
        price = _parse_price(result.get("price", ""))
        if price and price > 0:
            listings.append(MarketListing(
                title=result.get("title", ""),
                price=price,
                source="google_shopping",
                url=result.get("link"),
                status="active",
            ))
    return listings


async def search_new_price(query: str, api_key: str) -> tuple[float | None, str | None]:
    params = {
        "engine": "google_shopping",
        "q": query,
        "gl": "se",
        "hl": "sv",
        "api_key": api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(SERPAPI_ENDPOINT, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning(f"SerpApi new price error: {e}")
        return None, None

    trusted: list[tuple[float, str]] = []
    fallback: list[tuple[float, str]] = []

    for result in data.get("shopping_results", []):
        price = _parse_price(result.get("price", ""))
        if not price or price < MIN_ELECTRONICS_PRICE:
            continue

        source_name = result.get("source") or ""
        source_lower = source_name.lower()

        # Skip known junk marketplaces
        if any(u in source_lower for u in UNTRUSTED_SOURCES):
            logger.debug(f"Skipping untrusted new-price source: {source_name} ({price} kr)")
            continue

        if any(t in source_lower for t in TRUSTED_RETAILERS):
            trusted.append((price, source_name))
        else:
            fallback.append((price, source_name))

    candidates = trusted if trusted else fallback
    if not candidates:
        logger.info(f"No trustworthy new-price results for: {query}")
        return None, None

    # Use median of the 3 lowest trusted prices to avoid outliers
    candidates.sort(key=lambda x: x[0])
    top3 = candidates[:3]
    median_price = statistics.median(p for p, _ in top3)
    # Source = the one closest to the median
    best_source = min(top3, key=lambda x: abs(x[0] - median_price))[1]

    return round(median_price), best_source


async def search_blocket(query: str, api_key: str) -> list[MarketListing]:
    params = {
        "engine": "google",
        "q": f"site:blocket.se {query}",
        "gl": "se",
        "hl": "sv",
        "api_key": api_key,
        "num": 10,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(SERPAPI_ENDPOINT, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning(f"SerpApi Blocket error: {e}")
        return []

    listings = []
    for result in data.get("organic_results", []):
        snippet = result.get("snippet", "")
        price = _extract_price_from_text(snippet)
        if price and price > 0:
            listings.append(MarketListing(
                title=result.get("title", ""),
                price=price,
                source="blocket",
                url=result.get("link"),
                status="active",
            ))
    return listings


async def search_facebook_marketplace(query: str, api_key: str) -> list[MarketListing]:
    params = {
        "engine": "google",
        "q": f"site:facebook.com/marketplace {query}",
        "gl": "se",
        "hl": "sv",
        "api_key": api_key,
        "num": 10,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(SERPAPI_ENDPOINT, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning(f"SerpApi Facebook error: {e}")
        return []

    listings = []
    for result in data.get("organic_results", []):
        snippet = result.get("snippet", "")
        price = _extract_price_from_text(snippet)
        if price and price > 0:
            listings.append(MarketListing(
                title=result.get("title", ""),
                price=price,
                source="facebook_marketplace",
                url=result.get("link"),
                status="active",
            ))
    return listings


async def search_price_history(query: str, api_key: str) -> list[dict]:
    """Search for price history via Google Shopping over time."""
    params = {
        "engine": "google_shopping",
        "q": query,
        "gl": "se",
        "hl": "sv",
        "api_key": api_key,
        "tbs": "qdr:m6",  # last 6 months
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(SERPAPI_ENDPOINT, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning(f"SerpApi price history error: {e}")
        return []

    results = []
    for result in data.get("shopping_results", []):
        price = _parse_price(result.get("price", ""))
        if price and price > 0:
            results.append({"price": price, "source": result.get("source", "Google Shopping")})
    return results


def _parse_price(price_str: str) -> float | None:
    if not price_str:
        return None
    cleaned = (
        price_str.replace("\xa0", "")
        .replace(" ", "")
        .replace(",", ".")
        .replace("SEK", "")
        .replace("kr", "")
        .replace(":-", "")
        .strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_price_from_text(text: str) -> float | None:
    import re
    patterns = [
        r"(\d[\d\s]*)\s*kr",
        r"(\d[\d\s]*)\s*SEK",
        r"(\d[\d\s,]*)\s*:-",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(" ", "").replace(",", ".")
            try:
                return float(price_str)
            except ValueError:
                continue
    return None
