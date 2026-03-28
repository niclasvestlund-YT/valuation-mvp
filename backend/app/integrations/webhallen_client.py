"""Webhallen new-price client — free Swedish retailer JSON API.

Endpoint: GET /api/productdiscovery/autocomplete/{query}

Observed response shape (2026-03-28):
    {
      "products": [
        {
          "name": "Sony WH-1000XM4 - Svart (Fyndvara klass 2)",
          "price": {
            "price": "1990.00",
            "currency": "SEK",
            ...
          },
          "regularPrice": {
            "price": "3290.00",
            "currency": "SEK",
            ...
          },
          "section": {"name": "Fyndvaror", ...},
          ...
        }
      ],
      "phrases": [...]
    }

Price is nested: product["price"]["price"] (string).
regularPrice holds the non-sale / list price.
section.name == "Fyndvaror" indicates refurbished / returned items.
"""

import time
from typing import Optional

import requests

from backend.app.utils.cache import get_cached, set_cached
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

_AUTOCOMPLETE_URL = "https://www.webhallen.com/api/productdiscovery/autocomplete/"
_REQUEST_TIMEOUT = 10
_RATE_LIMIT_SECONDS = 5

_last_request_time: float = 0.0


def _extract_price(product: dict) -> Optional[float]:
    """Extract the current SEK price from a Webhallen product dict.

    Handles:
      - nested: {"price": {"price": "3990.00", "currency": "SEK"}}
      - flat:   {"price": 3990} or {"price": "3990.00"}
      - lowestPrice / currentPrice as fallbacks
    """
    price_field = product.get("price")

    if isinstance(price_field, dict):
        raw = price_field.get("price")
    else:
        raw = price_field

    if raw is None:
        # Try fallback fields
        raw = product.get("lowestPrice") or product.get("currentPrice")

    if raw is None:
        return None

    try:
        value = float(str(raw).replace(",", ".").strip())
        return value if value > 0 else None
    except (ValueError, TypeError):
        return None


def get_new_price_sek(product_query: str) -> Optional[float]:
    """Search Webhallen for a product and return the lowest SEK price, or None.

    Uses 1h in-memory cache and 5s rate limiting between requests.
    Never raises — all errors are caught and logged.
    """
    global _last_request_time

    if not product_query or not product_query.strip():
        return None

    query = product_query.strip()
    cache_key = f"webhallen:{query}"
    cached = get_cached(cache_key)
    if cached is not None:
        logger.info("webhallen.cache_hit query=%s", query)
        return cached

    # Rate limiting
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)

    try:
        _last_request_time = time.monotonic()
        response = requests.get(
            f"{_AUTOCOMPLETE_URL}{query}",
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; price-check)",
                "Accept": "application/json",
            },
            timeout=_REQUEST_TIMEOUT,
        )

        if response.status_code != 200:
            logger.warning("webhallen.http_error query=%s status=%s", query, response.status_code)
            return None

        data = response.json()
    except requests.RequestException as exc:
        logger.warning("webhallen.request_failed query=%s reason=%s", query, exc)
        return None
    except (ValueError, KeyError) as exc:
        logger.warning("webhallen.parse_failed query=%s reason=%s", query, exc)
        return None

    products = data.get("products") or []
    if not products:
        logger.info("webhallen.no_products query=%s", query)
        return None

    prices: list[float] = []
    for product in products:
        price = _extract_price(product)
        if price is not None and 100 < price < 200_000:
            prices.append(price)

    if not prices:
        logger.info("webhallen.no_valid_prices query=%s", query)
        return None

    result = min(prices)
    set_cached(cache_key, result)
    logger.info("webhallen.price_found query=%s price=%s count=%s", query, result, len(prices))
    return result
