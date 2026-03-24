import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

SWEDISH_HINT_KEYWORDS = {
    "sverige",
    "svensk",
    "sek",
    "kr",
    "fri frakt",
}


@dataclass(frozen=True)
class NewPriceSearchResponse:
    results: list[dict[str, Any]] = field(default_factory=list)
    available: bool = True
    reason: str = "ok"


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def infer_currency(price_text: str | None) -> str | None:
    if not price_text:
        return None

    normalized = price_text.upper()
    if "SEK" in normalized or " KR" in normalized or normalized.endswith("KR"):
        return "SEK"
    if "$" in normalized or "USD" in normalized:
        return "USD"
    if "EUR" in normalized or "€" in normalized:
        return "EUR"
    if "GBP" in normalized or "£" in normalized:
        return "GBP"
    return None


def infer_domain(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().strip()
    return hostname or None


def is_swedish_result(source: str | None, url: str | None, text: str | None) -> bool:
    domain = infer_domain(url) or ""
    normalized_source = normalize_text(source)
    normalized_text = normalize_text(text)

    if domain.endswith(".se"):
        return True

    if any(keyword in normalized_source for keyword in SWEDISH_HINT_KEYWORDS):
        return True

    if any(keyword in normalized_text for keyword in SWEDISH_HINT_KEYWORDS):
        return True

    return False


class NewPriceSearchClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        engine: str | None = None,
        location: str | None = None,
        gl: str | None = None,
        hl: str | None = None,
    ) -> None:
        self.api_key = (api_key or settings.serpapi_api_key or "").strip() or None
        self.base_url = base_url or settings.serpapi_base_url
        self.timeout_seconds = timeout_seconds or settings.serpapi_timeout_seconds
        self.engine = engine or settings.serpapi_engine
        self.location = location if location is not None else settings.serpapi_location
        self.gl = gl if gl is not None else settings.serpapi_gl
        self.hl = hl if hl is not None else settings.serpapi_hl

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search(self, *, brand: str, model: str, category: str | None = None) -> NewPriceSearchResponse:
        query = self._build_query(brand=brand, model=model, category=category)
        if not query:
            return NewPriceSearchResponse(results=[], available=True, reason="empty_query")

        if not self.is_configured:
            logger.info("new_price_search.not_configured query=%s", query)
            return NewPriceSearchResponse(results=[], available=False, reason="missing_api_key")

        params = {
            "api_key": self.api_key,
            "engine": self.engine,
            "q": query,
        }
        if self.location:
            params["location"] = self.location
        if self.gl:
            params["gl"] = self.gl
        if self.hl:
            params["hl"] = self.hl

        try:
            response = requests.get(self.base_url, params=params, timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            logger.warning("new_price_search.request_failed query=%s reason=%s", query, exc)
            return NewPriceSearchResponse(results=[], available=False, reason="request_failed")
        except ValueError as exc:
            logger.warning("new_price_search.invalid_response query=%s reason=%s", query, exc)
            return NewPriceSearchResponse(results=[], available=False, reason="invalid_response")

        results = self._extract_results(payload)
        return NewPriceSearchResponse(results=results, available=True, reason="ok")

    def _build_query(self, *, brand: str, model: str, category: str | None = None) -> str:
        query_parts = [brand, model]
        if category:
            query_parts.append(category)
        if (self.gl or "").lower() == "se":
            query_parts.extend(["pris", "Sverige", "SEK"])
        return " ".join(" ".join((part or "").split()) for part in query_parts if part).strip()

    def _extract_results(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        extracted: list[dict[str, Any]] = []
        for item in payload.get("shopping_results", []):
            normalized = self._normalize_result(item)
            if normalized:
                extracted.append(normalized)

        for item in payload.get("inline_shopping_results", []):
            normalized = self._normalize_result(item)
            if normalized:
                extracted.append(normalized)

        return extracted

    def _normalize_result(self, item: dict[str, Any]) -> dict[str, Any] | None:
        title = str(item.get("title") or "").strip()
        price = item.get("extracted_price")
        if not title or price is None:
            return None

        price_text = str(item.get("price") or "").strip() or None
        source = str(item.get("source") or item.get("seller") or "").strip() or None
        url = item.get("product_link") or item.get("link") or item.get("serpapi_link")
        snippet = str(item.get("snippet") or "").strip() or None
        delivery = str(item.get("delivery") or "").strip() or None
        second_hand_condition = str(item.get("second_hand_condition") or "").strip() or None
        combined_text = " ".join(part for part in [title, snippet, delivery, price_text, source] if part)

        return {
            "title": title,
            "price": float(price),
            "price_text": price_text,
            "currency": infer_currency(price_text),
            "source": source,
            "url": url,
            "snippet": snippet,
            "delivery": delivery,
            "second_hand_condition": second_hand_condition,
            "is_swedish_result": is_swedish_result(source, url, combined_text),
            "raw": item,
        }
