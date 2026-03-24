import logging
import statistics
import httpx
from ..models import MarketListing

logger = logging.getLogger(__name__)

SERPER_SHOPPING_ENDPOINT = "https://google.serper.dev/shopping"

UNTRUSTED_SOURCES = {
    "ebay", "wish", "aliexpress", "temu", "dhgate", "banggood",
    "gearbest", "joom", "shein",
}

# Swedish and international retailers known to sell new electronics at retail price
TRUSTED_RETAILERS = {
    # Swedish brick-and-mortar / large e-commerce
    "webhallen", "elgiganten", "mediamarkt", "media markt",
    "inet", "dustin", "komplett", "power", "onoff", "euronics",
    "netonnet", "kjell", "cdon", "fyndiq", "gameshop", "coolshop",
    "pricerunner", "prisjakt",
    # Brand own stores
    "apple", "samsung", "sony",
    # International but reliable
    "amazon", "amazon.se",
}

# Minimum price for a new electronics product listing.
# Accessories and parts are often 100–700 kr — this filters them from new-price candidates.
MIN_NEW_PRICE_SEK = 1000  # kr


async def search_market_data(query: str, api_key: str) -> list[MarketListing]:
    payload = {
        "q": f"{query} begagnad used",
        "gl": "se",
        "hl": "sv",
    }
    logger.info(f"Serper market data query: {payload['q']!r}")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                SERPER_SHOPPING_ENDPOINT,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json=payload,
            )
            logger.info(f"Serper market data response: HTTP {r.status_code} — {r.text[:500]}")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning(f"Serper market data error: {e}")
        return []

    listings = []
    for result in data.get("shopping", []):
        price = _parse_price(result.get("price", ""))
        if price and price > 0:
            listings.append(MarketListing(
                title=result.get("title", ""),
                price=price,
                source="google_shopping",
                url=result.get("link"),
                status="active",
            ))
    logger.info(f"Serper market data parsed {len(listings)} listings for {query!r}")
    return listings


async def search_new_price(query: str, api_key: str) -> tuple[float | None, str | None]:
    payload = {
        "q": query,
        "gl": "se",
        "hl": "sv",
    }
    logger.info(f"Serper new price query: {query!r}")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                SERPER_SHOPPING_ENDPOINT,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json=payload,
            )
            logger.info(f"Serper new price response: HTTP {r.status_code} — {r.text[:500]}")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning(f"Serper new price error: {e}")
        return None, None

    trusted: list[tuple[float, str]] = []
    fallback: list[tuple[float, str]] = []

    for result in data.get("shopping", []):
        price = _parse_price(result.get("price", ""))
        if not price or price < MIN_NEW_PRICE_SEK:
            logger.debug(f"Skipping low-price new-price result: {result.get('title','')[:40]} ({price} kr)")
            continue

        source_name = result.get("source") or ""
        source_lower = source_name.lower()

        if any(u in source_lower for u in UNTRUSTED_SOURCES):
            logger.debug(f"Skipping untrusted new-price source: {source_name} ({price} kr)")
            continue

        if any(t in source_lower for t in TRUSTED_RETAILERS):
            trusted.append((price, source_name))
        else:
            fallback.append((price, source_name))

    logger.info(f"Serper new price candidates: {len(trusted)} trusted, {len(fallback)} fallback")
    for p, s in sorted(trusted)[:5]:
        logger.info(f"  trusted  {p:.0f} kr  {s}")
    for p, s in sorted(fallback)[:5]:
        logger.info(f"  fallback {p:.0f} kr  {s}")

    # Prefer trusted retailers; fall back to non-untrusted if none found
    candidates = trusted if trusted else fallback
    if not candidates:
        logger.info(f"No trustworthy new-price results for: {query}")
        return None, None

    # Use median of ALL candidates (not just cheapest 3) — more robust against outliers
    median_price = statistics.median(p for p, _ in candidates)
    best_source = min(candidates, key=lambda x: abs(x[0] - median_price))[1]

    logger.info(f"Serper new price result: {round(median_price)} kr from {best_source!r} (median of {len(candidates)} candidates)")
    return round(median_price), best_source


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
