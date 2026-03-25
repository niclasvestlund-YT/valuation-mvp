"""
Google Custom Search Engine client for new-price lookups.

Queries the Google CSE JSON API (programmablesearchengine.google.com).
Requires GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX in .env.
Free tier: 100 queries/day. Paid: ~$5 per 1 000 queries.

Used as a secondary new-price source alongside Serper.dev.
Results include structured pagemap.offer price data when available,
with a regex fallback on snippet/title for plain-text prices.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

import requests

from backend.app.core.config import settings
from backend.app.utils.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"
TIMEOUT = 15

# Matches "1 299 kr", "1299:-", "1 299 SEK", "SEK 1299", "1299.00 kr"
_PRICE_RE = re.compile(
    r"(?:SEK\s*)?(\d[\d\s]*(?:[.,]\d{1,2})?)\s*(?:kr|:-|SEK)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GoogleCSESearchResponse:
    results: list[dict[str, Any]]
    available: bool
    reason: str


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    m = _PRICE_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _extract_price_from_item(item: dict[str, Any]) -> tuple[float | None, str]:
    """Return (price, currency) from structured pagemap data or snippet."""
    pagemap = item.get("pagemap") or {}

    # Structured offer data (Google Rich Results)
    for offer in pagemap.get("offer") or []:
        raw = str(offer.get("price") or "")
        try:
            price = float(raw.replace(",", ".").replace(" ", ""))
            currency = str(offer.get("pricecurrency") or "SEK").upper()
            if price > 0:
                return price, currency
        except ValueError:
            pass

    # Product structured data
    for product in pagemap.get("product") or []:
        raw = str(product.get("price") or "")
        try:
            price = float(raw.replace(",", ".").replace(" ", ""))
            if price > 0:
                return price, "SEK"
        except ValueError:
            pass

    # Regex fallback on snippet and title
    for field in ("snippet", "title"):
        price = _parse_price(item.get(field))
        if price and price > 0:
            return price, "SEK"

    return None, "SEK"


class GoogleCSEClient:
    @property
    def is_configured(self) -> bool:
        return bool(settings.google_cse_api_key and settings.google_cse_cx)

    def search(
        self, *, brand: str, model: str, category: str | None = None
    ) -> GoogleCSESearchResponse:
        if not self.is_configured:
            return GoogleCSESearchResponse(results=[], available=False, reason="not_configured")

        query = f"{brand} {model} pris köpa Sverige SEK"
        cache_key = f"google_cse:{query}"
        cached = get_cached(cache_key)
        if cached is not None:
            logger.debug("google_cse.cache_hit query=%s", query)
            return GoogleCSESearchResponse(results=cached, available=True, reason="cache_hit")

        try:
            resp = requests.get(
                GOOGLE_CSE_URL,
                params={
                    "key": settings.google_cse_api_key,
                    "cx": settings.google_cse_cx,
                    "q": query,
                    "lr": "lang_sv",
                    "gl": "se",
                    "num": 10,
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("google_cse.request_failed query=%s reason=%s", query, exc)
            return GoogleCSESearchResponse(results=[], available=False, reason=str(exc))

        data = resp.json()
        items = data.get("items") or []
        results = [self._normalize(item) for item in items]
        set_cached(cache_key, results)

        logger.info("google_cse.results query=%s count=%d", query, len(results))
        return GoogleCSESearchResponse(results=results, available=True, reason="ok")

    def _normalize(self, item: dict[str, Any]) -> dict[str, Any]:
        price, currency = _extract_price_from_item(item)
        return {
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "url": item.get("link"),
            "source": item.get("displayLink"),
            "price": price,
            "currency": currency,
            "is_swedish_result": True,
            "second_hand_condition": None,
            "delivery": None,
            "raw": item,
        }
