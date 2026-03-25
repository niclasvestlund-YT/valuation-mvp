from statistics import median
from typing import Any

from backend.app.integrations.google_cse_client import GoogleCSEClient
from backend.app.integrations.new_price_search_client import NewPriceSearchClient, normalize_text
from backend.app.integrations.serper_new_price_client import SerperNewPriceClient
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

USED_KEYWORDS = {
    "used",
    "begagnad",
    "pre-owned",
}

REFURBISHED_KEYWORDS = {
    "refurbished",
    "rekonditionerad",
    "renewed",
}

ACCESSORY_ONLY_KEYWORDS = {
    "charger",
    "cable",
    "case",
    "cover",
    "adapter",
    "strap",
    "band",
    "replacement parts",
    "replacement part",
    "spare part",
    "spare parts",
}

CATEGORY_MINIMUM_PRICE_BY_CURRENCY = {
    "SEK": {
        "smartphone": 500.0,
        "tablet": 700.0,
        "laptop": 2500.0,
        "headphones": 250.0,
        "camera": 1500.0,
        "smartwatch": 400.0,
        "router": 150.0,
        "accessory": 100.0,
        "unknown": 150.0,
    },
    "USD": {
        "smartphone": 50.0,
        "tablet": 70.0,
        "laptop": 200.0,
        "headphones": 25.0,
        "camera": 150.0,
        "smartwatch": 35.0,
        "router": 15.0,
        "accessory": 10.0,
        "unknown": 15.0,
    },
    "EUR": {
        "smartphone": 45.0,
        "tablet": 65.0,
        "laptop": 180.0,
        "headphones": 25.0,
        "camera": 140.0,
        "smartwatch": 30.0,
        "router": 15.0,
        "accessory": 10.0,
        "unknown": 15.0,
    },
    "GBP": {
        "smartphone": 40.0,
        "tablet": 60.0,
        "laptop": 160.0,
        "headphones": 20.0,
        "camera": 125.0,
        "smartwatch": 30.0,
        "router": 15.0,
        "accessory": 10.0,
        "unknown": 15.0,
    },
}


def significant_model_tokens(model: str) -> list[str]:
    tokens = normalize_text(model).split()
    return [token for token in tokens if len(token) >= 3 or any(char.isdigit() for char in token)]


def minimum_plausible_price(category: str | None, currency: str | None) -> float:
    normalized_category = normalize_text(category) or "unknown"
    normalized_currency = (currency or "").upper() or "SEK"
    category_prices = CATEGORY_MINIMUM_PRICE_BY_CURRENCY.get(
        normalized_currency,
        CATEGORY_MINIMUM_PRICE_BY_CURRENCY["SEK"],
    )
    return category_prices.get(normalized_category, category_prices["unknown"])


def should_reject_candidate(
    candidate: dict[str, Any],
    *,
    brand: str,
    model: str,
    category: str | None,
) -> tuple[bool, str | None]:
    haystack = normalize_text(
        " ".join(
            str(value)
            for value in [
                candidate.get("title"),
                candidate.get("snippet"),
                candidate.get("source"),
                candidate.get("delivery"),
                candidate.get("second_hand_condition"),
            ]
            if value
        )
    )

    if any(keyword in haystack for keyword in USED_KEYWORDS):
        return True, "used_or_begagnad"

    if any(keyword in haystack for keyword in REFURBISHED_KEYWORDS):
        return True, "refurbished_or_rekonditionerad"

    if any(keyword in haystack for keyword in ACCESSORY_ONLY_KEYWORDS):
        return True, "accessory_only"

    normalized_brand = normalize_text(brand)
    if normalized_brand and normalized_brand not in haystack:
        return True, "brand_mismatch"

    model_tokens = significant_model_tokens(model)
    if model_tokens and not all(token in haystack for token in model_tokens):
        return True, "model_mismatch"

    category_floor = minimum_plausible_price(category, candidate.get("currency"))
    price = float(candidate.get("price") or 0.0)
    if price < category_floor:
        return True, "implausibly_low_price"

    return False, None


def choose_preferred_currency(candidates: list[dict[str, Any]]) -> str | None:
    currencies = [str(candidate.get("currency")).upper() for candidate in candidates if candidate.get("currency")]
    if not currencies:
        return None

    if "SEK" in currencies:
        return "SEK"

    ranked = sorted({currency: currencies.count(currency) for currency in set(currencies)}.items(), key=lambda item: (-item[1], item[0]))
    return ranked[0][0] if ranked else None


def choose_preferred_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    swedish_sek_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("is_swedish_result") and (candidate.get("currency") or "").upper() == "SEK"
    ]
    if swedish_sek_candidates:
        return swedish_sek_candidates

    sek_candidates = [candidate for candidate in candidates if (candidate.get("currency") or "").upper() == "SEK"]
    if sek_candidates:
        return sek_candidates

    swedish_candidates = [candidate for candidate in candidates if candidate.get("is_swedish_result")]
    if swedish_candidates:
        return swedish_candidates

    return candidates


def build_unavailable_result(method: str = "unavailable") -> dict[str, Any]:
    return {
        "estimated_new_price": None,
        "currency": None,
        "confidence": 0.0,
        "source_count": 0,
        "sources": [],
        "method": method,
        "price": 0.0,
        "source": method,
    }


class NewPriceService:
    def __init__(
        self,
        search_client: NewPriceSearchClient | None = None,
        serper_client: SerperNewPriceClient | None = None,
        google_cse_client: GoogleCSEClient | None = None,
    ) -> None:
        self.serper_client = serper_client or SerperNewPriceClient()
        self.google_cse_client = google_cse_client or GoogleCSEClient()
        self.search_client = search_client or NewPriceSearchClient()

    def get_new_price(self, brand: str, model: str, category: str | None = None) -> dict[str, Any]:
        serper_failed = False

        # Try Serper.dev first (primary — no SerpAPI quota consumed)
        if self.serper_client.is_configured:
            response = self.serper_client.search(brand=brand, model=model, category=category)
            if response.available:
                # Serper reached the network; return whatever it found (even no_trustworthy_candidates)
                result = self._process_candidates(
                    response.results,
                    brand=brand,
                    model=model,
                    category=category,
                    method_label="serper_google_shopping_median",
                    source_label="Serper.dev Google Shopping",
                )
                logger.info(
                    "new_price.serper_done brand=%s model=%s method=%s",
                    brand,
                    model,
                    result.get("method"),
                )
                return result
            else:
                # Network/config failure — fall through to SerpAPI
                serper_failed = True
                logger.info(
                    "new_price.serper_failed brand=%s model=%s reason=%s",
                    brand,
                    model,
                    response.reason,
                )

        # Google CSE fallback — tried when Serper.dev had a hard failure or is unconfigured.
        if (not self.serper_client.is_configured or serper_failed) and self.google_cse_client.is_configured:
            logger.info("new_price.google_cse_fallback brand=%s model=%s", brand, model)
            cse_response = self.google_cse_client.search(brand=brand, model=model, category=category)
            if cse_response.available:
                result = self._process_candidates(
                    cse_response.results,
                    brand=brand,
                    model=model,
                    category=category,
                    method_label="google_cse_median",
                    source_label="Google Custom Search",
                )
                logger.info(
                    "new_price.google_cse_done brand=%s model=%s method=%s",
                    brand,
                    model,
                    result.get("method"),
                )
                return result

        # SerpAPI fallback — only called when all above failed or are unconfigured.
        # Skipped entirely when SERPAPI_API_KEY is absent (search_client returns available=False immediately).
        if not self.serper_client.is_configured or serper_failed:
            logger.info("new_price.serpapi_fallback brand=%s model=%s", brand, model)

        response = self.search_client.search(brand=brand, model=model, category=category)
        if not response.available:
            return build_unavailable_result(method="unavailable")

        return self._process_candidates(
            response.results,
            brand=brand,
            model=model,
            category=category,
            method_label="serpapi_google_shopping_median",
            source_label="SerpApi Google Shopping",
        )

    def _process_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        brand: str,
        model: str,
        category: str | None,
        method_label: str,
        source_label: str,
    ) -> dict[str, Any]:
        valid_candidates: list[dict[str, Any]] = []
        for candidate in candidates:
            rejected, _reason = should_reject_candidate(
                candidate,
                brand=brand,
                model=model,
                category=category,
            )
            if not rejected:
                valid_candidates.append(candidate)

        if not valid_candidates:
            logger.info("new_price.no_trustworthy_candidates brand=%s model=%s category=%s", brand, model, category)
            return build_unavailable_result(method="no_trustworthy_candidates")

        preferred_candidates = choose_preferred_candidates(valid_candidates)
        preferred_currency = choose_preferred_currency(preferred_candidates)
        same_currency_candidates = [
            candidate
            for candidate in preferred_candidates
            if (candidate.get("currency") or "").upper() == (preferred_currency or "").upper()
        ] or preferred_candidates

        source_records = [
            {
                "source": candidate.get("source"),
                "title": candidate.get("title"),
                "price": candidate.get("price"),
                "currency": candidate.get("currency"),
                "url": candidate.get("url"),
            }
            for candidate in same_currency_candidates
        ]

        if len(same_currency_candidates) < 2:
            return {
                "estimated_new_price": None,
                "currency": preferred_currency,
                "confidence": 0.2,
                "source_count": len(same_currency_candidates),
                "sources": source_records,
                "method": "single_source_insufficient",
                "price": 0.0,
                "source": source_records[0]["source"] if source_records else "single_source_insufficient",
            }

        prices = [float(candidate["price"]) for candidate in same_currency_candidates]
        estimated_price = round(float(median(prices)), 2)
        confidence = 0.45 if len(same_currency_candidates) == 2 else 0.65
        if preferred_currency == "SEK":
            confidence = min(0.8, confidence + 0.1)

        return {
            "estimated_new_price": estimated_price,
            "currency": preferred_currency,
            "confidence": round(confidence, 2),
            "source_count": len(same_currency_candidates),
            "sources": source_records,
            "method": method_label,
            "price": estimated_price,
            "source": source_label,
        }
