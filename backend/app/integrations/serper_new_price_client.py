import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests

from backend.app.core.config import settings
from backend.app.utils.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

SERPER_SHOPPING_ENDPOINT = "https://google.serper.dev/shopping"

UNTRUSTED_SOURCES = {
    "ebay",
    "wish",
    "aliexpress",
    "temu",
    "dhgate",
    "banggood",
    "gearbest",
    "joom",
    "shein",
    "ubuy",
    "fruugo",
    "catchoftheday",
    "onbuy",
    "pricerunner",
    "kelkoo",
}

SWEDISH_HINT_KEYWORDS = {
    "sverige",
    "svensk",
    "sek",
    "kr",
    "fri frakt",
}


@dataclass(frozen=True)
class SerperNewPriceSearchResponse:
    results: list[dict[str, Any]] = field(default_factory=list)
    available: bool = True
    reason: str = "ok"


def _parse_price(price_str: str | None) -> float | None:
    if not price_str:
        return None
    cleaned = (
        str(price_str)
        .replace("\xa0", "")
        .replace("\u00a0", "")
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


def _infer_currency(price_str: str | None) -> str | None:
    if not price_str:
        return None
    normalized = str(price_str).upper()
    if "SEK" in normalized or " KR" in normalized or normalized.endswith("KR"):
        return "SEK"
    if "$" in normalized or "USD" in normalized:
        return "USD"
    if "EUR" in normalized or "€" in normalized:
        return "EUR"
    if "GBP" in normalized or "£" in normalized:
        return "GBP"
    return None


def _infer_domain(url: str | None) -> str | None:
    if not url:
        return None
    hostname = (urlparse(url).hostname or "").lower().strip()
    return hostname or None


def _is_swedish_result(source: str | None, url: str | None, text: str | None) -> bool:
    domain = _infer_domain(url) or ""
    normalized = " ".join((f"{source or ''} {text or ''}").lower().split())

    if domain.endswith(".se"):
        return True
    return any(kw in normalized for kw in SWEDISH_HINT_KEYWORDS)


class SerperNewPriceClient:
    """
    New-price lookup via Serper.dev Google Shopping.

    Primary new-price source — replaces SerpAPI Google Shopping.
    Requires SERPER_DEV_API_KEY in the environment.
    """

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        self.api_key = (api_key or settings.serper_api_key or "").strip() or None
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search(self, *, brand: str, model: str, category: str | None = None) -> SerperNewPriceSearchResponse:
        if not self.is_configured:
            logger.info("serper_new_price.not_configured brand=%s model=%s", brand, model)
            return SerperNewPriceSearchResponse(results=[], available=False, reason="missing_api_key")

        query = self._build_query(brand=brand, model=model, category=category)
        cache_key = f"serper_new_price:{query}"
        cached = get_cached(cache_key)
        if cached is not None:
            logger.info("serper_new_price.cache_hit query=%s count=%s", query, len(cached))
            return SerperNewPriceSearchResponse(results=cached, available=True, reason="cached")

        try:
            response = requests.post(
                SERPER_SHOPPING_ENDPOINT,
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                json={"q": query, "gl": "se", "hl": "sv"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            logger.warning("serper_new_price.request_failed query=%s reason=%s", query, exc)
            return SerperNewPriceSearchResponse(results=[], available=False, reason="request_failed")
        except ValueError as exc:
            logger.warning("serper_new_price.invalid_response query=%s reason=%s", query, exc)
            return SerperNewPriceSearchResponse(results=[], available=False, reason="invalid_response")

        results = self._extract_results(payload)
        logger.info("serper_new_price.results query=%s count=%s", query, len(results))
        set_cached(cache_key, results)
        return SerperNewPriceSearchResponse(results=results, available=True, reason="ok")

    def _build_query(self, *, brand: str, model: str, category: str | None = None) -> str:
        parts = [brand, model]
        if category:
            parts.append(category)
        parts.extend(["pris", "Sverige", "SEK"])
        return " ".join(p for p in parts if p).strip()

    def _extract_results(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        extracted: list[dict[str, Any]] = []
        for item in payload.get("shopping", []):
            normalized = self._normalize_item(item)
            if normalized:
                extracted.append(normalized)
        return extracted

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        title = str(item.get("title") or "").strip()
        price_str = str(item.get("price") or "").strip() or None
        price = _parse_price(price_str)

        if not title or price is None or price <= 0:
            return None

        source = str(item.get("source") or "").strip() or None
        if source and any(u in source.lower() for u in UNTRUSTED_SOURCES):
            return None

        url = item.get("link") or item.get("productLink")
        currency = _infer_currency(price_str) or "SEK"
        combined_text = " ".join(p for p in [title, price_str, source] if p)

        return {
            "title": title,
            "price": price,
            "price_text": price_str,
            "currency": currency,
            "source": source,
            "url": url,
            "snippet": str(item.get("snippet") or "").strip() or None,
            "delivery": str(item.get("delivery") or "").strip() or None,
            "second_hand_condition": str(item.get("condition") or "").strip() or None,
            "is_swedish_result": _is_swedish_result(source, url, combined_text),
            "raw": item,
        }
