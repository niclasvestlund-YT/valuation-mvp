import logging
import re
from typing import Any
from urllib.parse import urlparse

import requests

from backend.app.core.config import settings
from backend.app.schemas.market_comparable import MarketComparable
from backend.app.utils import api_counter

logger = logging.getLogger(__name__)

ACCESSORY_KEYWORDS = {
    "case",
    "cover",
    "mount",
    "battery",
    "laddare",
    "charger",
    "cable",
    "kabel",
    "mic",
    "mikrofon",
    "tripod",
    "stativ",
    "housing",
    "remote",
    "fäste",
    "accessory",
    "tillbehör",
}

BUNDLE_KEYWORDS = {
    "adventure",
    "bundle",
    "combo",
    "kit",
    "pack",
    "creator",
}

BROKEN_OR_PARTS_KEYWORDS = {
    "for parts",
    "parts only",
    "broken",
    "defect",
    "defekt",
    "trasig",
    "repair",
    "reparation",
    "spare part",
    "reservdel",
    "låst",
    "locked",
}

COMPLETED_KEYWORDS = {
    "såld",
    "sold",
    "slut",
    "slutsåld",
    "avslutad",
    "ended",
    "utgången",
}

ACTIVE_KEYWORDS = {
    "köp nu",
    "buy now",
    "aktiv",
    "active",
    "available",
    "till salu",
}

SUPPORTED_MARKETPLACES = {
    "tradera.com": {
        "source": "tradera_serpapi",
        "listing_path_fragments": ["/item/"],
    },
    "blocket.se": {
        "source": "blocket_serpapi",
        "listing_path_fragments": ["/annons/", "/recommerce/forsale/item/"],
    },
}
SHIPPING_KEYWORDS = {
    "frakt",
    "shipping",
    "postnord",
}
VERSION_HINT_KEYWORDS = {
    "gen",
    "generation",
    "mark",
    "mk",
    "mini",
    "plus",
    "pro",
    "ultra",
    "max",
}
FALLBACK_SOURCE_QUALITY_RANK = {
    "fallback_exactish": 3,
    "fallback_broad_match": 2,
    "fallback_low_exactness": 1,
}
GENERIC_PAGE_KEYWORDS = {
    "annonser",
    "hela sverige",
    "kop salj",
    "köp sälj",
    "sokresultat",
    "sökresultat",
    "kategori",
}
MINIMUM_USED_MARKET_PRICE_BY_CURRENCY = {
    "SEK": {
        "smartphone": 250.0,
        "tablet": 350.0,
        "laptop": 1200.0,
        "headphones": 120.0,
        "camera": 300.0,
        "smartwatch": 150.0,
        "router": 100.0,
        "accessory": 50.0,
        "unknown": 100.0,
    },
    "USD": {
        "smartphone": 25.0,
        "tablet": 35.0,
        "laptop": 120.0,
        "headphones": 12.0,
        "camera": 30.0,
        "smartwatch": 15.0,
        "router": 10.0,
        "accessory": 5.0,
        "unknown": 10.0,
    },
    "EUR": {
        "smartphone": 25.0,
        "tablet": 35.0,
        "laptop": 110.0,
        "headphones": 12.0,
        "camera": 28.0,
        "smartwatch": 15.0,
        "router": 10.0,
        "accessory": 5.0,
        "unknown": 10.0,
    },
}


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def tokenize(value: str | None) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize_text(value))


def significant_model_tokens(model: str) -> list[str]:
    tokens = tokenize(model)
    return [token for token in tokens if len(token) >= 3 or any(character.isdigit() for character in token)]


def build_model_aliases(model: str) -> list[str]:
    normalized = normalize_text(model)
    aliases: list[str] = []

    if "osmo action" in normalized:
        aliases.append(normalized.replace("osmo ", "", 1))
    elif normalized.startswith("action "):
        aliases.append(f"osmo {normalized}")

    deduped: list[str] = []
    seen: set[str] = {normalized}
    for alias in aliases:
        alias_value = normalize_text(alias)
        if not alias_value or alias_value in seen:
            continue
        seen.add(alias_value)
        deduped.append(alias_value)

    return deduped


def extract_version_tokens(value: str | None) -> set[str]:
    version_tokens: set[str] = set()
    for token in tokenize(value):
        if any(character.isdigit() for character in token) or token in VERSION_HINT_KEYWORDS:
            version_tokens.add(token)

    return version_tokens


def keyword_hits(text: str, keywords: set[str]) -> list[str]:
    return sorted(keyword for keyword in keywords if re.search(r"\b" + re.escape(keyword) + r"\b", text))


def infer_currency(value: str | None) -> str | None:
    normalized = (value or "").upper()
    if "SEK" in normalized or " KR" in normalized or normalized.endswith("KR"):
        return "SEK"
    if "USD" in normalized or "$" in normalized:
        return "USD"
    if "EUR" in normalized or "€" in normalized:
        return "EUR"
    return None


def infer_status(text: str) -> str:
    if any(keyword in text for keyword in COMPLETED_KEYWORDS):
        return "completed"
    if any(keyword in text for keyword in ACTIVE_KEYWORDS):
        return "active"
    return "unknown"


def minimum_used_market_price(category: str | None, currency: str | None) -> float:
    normalized_category = normalize_text(category) or "unknown"
    normalized_currency = (currency or "").upper() or "SEK"
    category_prices = MINIMUM_USED_MARKET_PRICE_BY_CURRENCY.get(
        normalized_currency,
        MINIMUM_USED_MARKET_PRICE_BY_CURRENCY["SEK"],
    )
    return category_prices.get(normalized_category, category_prices["unknown"])


def extract_domain(url: str | None) -> str:
    if not url:
        return ""
    return (urlparse(url).hostname or "").lower().strip()


def extract_price_from_text(text: str | None) -> tuple[float | None, str | None]:
    normalized_text = text or ""
    for match in re.finditer(r"(\d[\d\s.,]{1,12})\s*(kr|sek)\b", normalized_text, flags=re.IGNORECASE):
        context_start = max(0, match.start() - 16)
        context_end = min(len(normalized_text), match.end() + 16)
        context = normalize_text(normalized_text[context_start:context_end])
        if any(keyword in context for keyword in SHIPPING_KEYWORDS):
            continue

        raw_amount = (
            match.group(1)
            .replace("\xa0", " ")
            .replace(" ", "")
            .replace(",", ".")
            .strip()
        )
        try:
            return float(raw_amount), "SEK"
        except ValueError:
            continue

    return None, None


def extract_price(candidate: dict[str, Any]) -> tuple[float | None, str | None]:
    direct_price = candidate.get("price") or candidate.get("extracted_price")
    if isinstance(direct_price, (int, float)) and direct_price > 0:
        currency = infer_currency(str(candidate.get("price"))) or "SEK"
        return float(direct_price), currency

    rich_snippet = candidate.get("rich_snippet") or {}
    for section_name in ("top", "bottom"):
        section = rich_snippet.get(section_name) or {}
        detected_extensions = section.get("detected_extensions") or {}
        detected_price = detected_extensions.get("price")
        if isinstance(detected_price, (int, float)) and detected_price > 0:
            return float(detected_price), "SEK"

    candidate_texts = [
        candidate.get("title"),
        candidate.get("snippet"),
        str(rich_snippet) if rich_snippet else None,
    ]
    for text in candidate_texts:
        price, currency = extract_price_from_text(text)
        if price is not None:
            return price, currency

    return None, None


class SerpApiUsedMarketClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        location: str | None = None,
        gl: str | None = None,
        hl: str | None = None,
    ) -> None:
        self.api_key = (api_key or settings.serpapi_api_key or "").strip() or None
        self.base_url = base_url or settings.serpapi_base_url
        self.timeout_seconds = timeout_seconds or settings.serpapi_timeout_seconds
        self.location = location if location is not None else settings.serpapi_location
        self.gl = gl if gl is not None else settings.serpapi_gl
        self.hl = hl if hl is not None else settings.serpapi_hl

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search(
        self,
        *,
        brand: str,
        model: str,
        category: str | None = None,
    ) -> list[MarketComparable]:
        if not self.is_configured:
            logger.info("serpapi_used_market.not_configured brand=%s model=%s", brand, model)
            return []

        queries = self._build_queries(brand=brand, model=model)

        comparables: list[MarketComparable] = []
        seen_candidates: set[tuple[str, str]] = set()

        for query in queries:
            for candidate in self._search_query(query):
                comparable = self._normalize_candidate(
                    candidate,
                    brand=brand,
                    model=model,
                    category=category,
                )
                if comparable is None:
                    continue

                identity = (
                    str(comparable.source),
                    str(comparable.url or comparable.listing_id),
                )
                if identity in seen_candidates:
                    continue

                seen_candidates.add(identity)
                comparables.append(comparable)

        logger.info(
            "serpapi_used_market.results brand=%s model=%s category=%s count=%s",
            brand,
            model,
            category,
            len(comparables),
        )
        api_counter.increment("serpapi_used")
        return comparables

    def _build_queries(self, *, brand: str, model: str) -> list[str]:
        model_tokens = significant_model_tokens(model)
        family = " ".join(model_tokens[:2]).strip()
        model_variants = [normalize_text(model), *build_model_aliases(model)]

        queries: list[str] = []
        for model_variant in model_variants:
            variant_query = f"{brand} {model_variant}".strip()
            queries.extend([
                f"{variant_query} site:tradera.com".strip(),
                f"{variant_query} site:blocket.se".strip(),
                f"{variant_query} blocket".strip(),
                f"{variant_query} begagnad".strip(),
            ])

        if family:
            queries.append(f"{brand} {family} site:blocket.se".strip())

        deduped_queries: list[str] = []
        seen_queries: set[str] = set()
        for query in queries:
            normalized_query = query.strip()
            if not normalized_query or normalized_query in seen_queries:
                continue
            seen_queries.add(normalized_query)
            deduped_queries.append(normalized_query)

        return deduped_queries

    def _search_query(self, query: str) -> list[dict[str, Any]]:
        params = {
            "api_key": self.api_key,
            "engine": "google",
            "q": query,
            "num": 10,
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
            logger.warning("serpapi_used_market.request_failed query=%s reason=%s", query, exc)
            api_counter.increment_error("serpapi_used")
            return []
        except ValueError as exc:
            logger.warning("serpapi_used_market.invalid_response query=%s reason=%s", query, exc)
            api_counter.increment_error("serpapi_used")
            return []

        results = payload.get("organic_results", []) or []
        logger.info("serpapi_used_market.raw_results query=%s count=%s", query, len(results))
        return [result for result in results if isinstance(result, dict)]

    def _normalize_candidate(
        self,
        candidate: dict[str, Any],
        *,
        brand: str,
        model: str,
        category: str | None = None,
    ) -> MarketComparable | None:
        title = str(candidate.get("title") or "").strip()
        url = candidate.get("link")
        snippet = str(candidate.get("snippet") or "").strip()
        combined_text = normalize_text(" ".join(part for part in [title, snippet, category] if part))
        normalized_title = normalize_text(title)

        if not title or not url:
            return None

        domain = extract_domain(url)
        marketplace = self._resolve_marketplace(domain)
        if marketplace is None:
            return None

        if self._looks_like_generic_market_page(domain=domain, url=url, text=combined_text):
            return None

        match_metadata = self._build_match_metadata(
            text=combined_text,
            title_text=normalized_title,
            brand=brand,
            model=model,
            domain=domain,
            listing_page_confidence=self._listing_page_confidence(domain=domain, url=url),
        )
        if match_metadata["hard_reject"]:
            return None

        price, currency = extract_price(candidate)
        if price is None:
            return None
        if price < minimum_used_market_price(category, currency):
            return None

        listing_id = str(candidate.get("result_id") or candidate.get("position") or url).strip()
        status = infer_status(combined_text)

        return MarketComparable(
            source=marketplace["source"],
            listing_id=listing_id,
            title=title,
            price=price,
            currency=currency or "SEK",
            status=status,
            url=url,
            ended_at=None,
            shipping_cost=None,
            condition_hint=None,
            raw={
                **candidate,
                "_fallback_metadata": match_metadata,
            },
        )

    def _resolve_marketplace(self, domain: str) -> dict[str, Any] | None:
        for fragment, marketplace in SUPPORTED_MARKETPLACES.items():
            if fragment in domain:
                return marketplace
        return None

    def _listing_page_confidence(self, *, domain: str, url: str) -> str:
        marketplace = self._resolve_marketplace(domain)
        if marketplace is None:
            return "unknown"

        path = (urlparse(url).path or "").lower()
        if any(fragment in path for fragment in marketplace["listing_path_fragments"]):
            return "high"
        return "low"

    def _looks_like_generic_market_page(self, *, domain: str, url: str, text: str) -> bool:
        listing_confidence = self._listing_page_confidence(domain=domain, url=url)
        if listing_confidence == "high":
            return False

        path = (urlparse(url).path or "").lower()
        if "/annonser/" in path and "/annons/" not in path:
            return True
        if "/recommerce/forsale/search" in path:
            return True

        return any(keyword in text for keyword in GENERIC_PAGE_KEYWORDS)

    def _build_match_metadata(
        self,
        *,
        text: str,
        title_text: str,
        brand: str,
        model: str,
        domain: str,
        listing_page_confidence: str,
    ) -> dict[str, Any]:
        normalized_brand = normalize_text(brand)
        target_tokens = significant_model_tokens(model)
        target_version_tokens = extract_version_tokens(model)
        result_version_tokens = extract_version_tokens(title_text)
        accessory_hits = keyword_hits(title_text, ACCESSORY_KEYWORDS)
        bundle_hits = keyword_hits(title_text, BUNDLE_KEYWORDS)
        broken_or_parts_hits = keyword_hits(text, BROKEN_OR_PARTS_KEYWORDS)
        reasons: list[str] = []
        flags: list[str] = []

        if normalized_brand and normalized_brand not in text:
            return self._fallback_metadata(
                reasons=["missing_brand"],
                flags=["irrelevant_result"],
                hard_reject=True,
                source_quality="fallback_low_exactness",
                exactness_confidence=0.0,
                target_model_is_broad=not bool(target_version_tokens),
                target_version_tokens=sorted(target_version_tokens),
                result_version_tokens=sorted(result_version_tokens),
                bundle_hits=bundle_hits,
                accessory_hits=accessory_hits,
                marketplace_domain=domain,
                listing_page_confidence=listing_page_confidence,
            )

        if target_tokens and not all(token in text for token in target_tokens):
            return self._fallback_metadata(
                reasons=["missing_model_tokens"],
                flags=["irrelevant_result"],
                hard_reject=True,
                source_quality="fallback_low_exactness",
                exactness_confidence=0.0,
                target_model_is_broad=not bool(target_version_tokens),
                target_version_tokens=sorted(target_version_tokens),
                result_version_tokens=sorted(result_version_tokens),
                bundle_hits=bundle_hits,
                accessory_hits=accessory_hits,
                marketplace_domain=domain,
                listing_page_confidence=listing_page_confidence,
            )

        if broken_or_parts_hits:
            return self._fallback_metadata(
                reasons=["broken_or_parts_listing"],
                flags=broken_or_parts_hits,
                hard_reject=True,
                source_quality="fallback_low_exactness",
                exactness_confidence=0.0,
                target_model_is_broad=not bool(target_version_tokens),
                target_version_tokens=sorted(target_version_tokens),
                result_version_tokens=sorted(result_version_tokens),
                bundle_hits=bundle_hits,
                accessory_hits=accessory_hits,
                marketplace_domain=domain,
                listing_page_confidence=listing_page_confidence,
            )

        if accessory_hits and not bundle_hits:
            return self._fallback_metadata(
                reasons=["accessory_heavy_listing"],
                flags=accessory_hits,
                hard_reject=True,
                source_quality="fallback_low_exactness",
                exactness_confidence=0.0,
                target_model_is_broad=not bool(target_version_tokens),
                target_version_tokens=sorted(target_version_tokens),
                result_version_tokens=sorted(result_version_tokens),
                bundle_hits=bundle_hits,
                accessory_hits=accessory_hits,
                marketplace_domain=domain,
                listing_page_confidence=listing_page_confidence,
            )

        if len(accessory_hits) >= 2:
            return self._fallback_metadata(
                reasons=["accessory_heavy_listing"],
                flags=accessory_hits,
                hard_reject=True,
                source_quality="fallback_low_exactness",
                exactness_confidence=0.0,
                target_model_is_broad=not bool(target_version_tokens),
                target_version_tokens=sorted(target_version_tokens),
                result_version_tokens=sorted(result_version_tokens),
                bundle_hits=bundle_hits,
                accessory_hits=accessory_hits,
                marketplace_domain=domain,
                listing_page_confidence=listing_page_confidence,
            )

        target_model_is_broad = not bool(target_version_tokens)
        extra_result_versions = sorted(result_version_tokens - target_version_tokens)
        version_mismatch = bool(target_version_tokens) and bool(result_version_tokens) and not target_version_tokens.issubset(result_version_tokens)

        if version_mismatch:
            return self._fallback_metadata(
                reasons=["generation_or_version_mismatch"],
                flags=extra_result_versions or sorted(result_version_tokens),
                hard_reject=True,
                source_quality="fallback_low_exactness",
                exactness_confidence=0.0,
                target_model_is_broad=target_model_is_broad,
                target_version_tokens=sorted(target_version_tokens),
                result_version_tokens=sorted(result_version_tokens),
                bundle_hits=bundle_hits,
                accessory_hits=accessory_hits,
                marketplace_domain=domain,
                listing_page_confidence=listing_page_confidence,
            )

        source_quality = "fallback_exactish"
        exactness_confidence = 0.82
        reasons.append("all_model_tokens_present")

        if target_model_is_broad:
            source_quality = "fallback_broad_match"
            exactness_confidence = 0.55
            reasons.append("target_model_is_broad")
            flags.append("lower_exactness_broad_target")
            if extra_result_versions:
                flags.extend(f"result_version:{token}" for token in extra_result_versions)
                reasons.append("result_includes_specific_generation")

        if bundle_hits:
            reasons.append("bundle_variant_listing")
            flags.extend(f"bundle:{token}" for token in bundle_hits)
            exactness_confidence = min(exactness_confidence, 0.62 if target_model_is_broad else 0.74)
            if source_quality == "fallback_exactish":
                source_quality = "fallback_broad_match"

        if accessory_hits:
            reasons.append("includes_accessory_terms")
            flags.extend(f"accessory:{token}" for token in accessory_hits)
            exactness_confidence = min(exactness_confidence, 0.6)
            source_quality = "fallback_low_exactness"

        if listing_page_confidence == "low":
            reasons.append("listing_page_shape_unclear")
            exactness_confidence = min(exactness_confidence, 0.58)
            if source_quality == "fallback_exactish":
                source_quality = "fallback_broad_match"

        return self._fallback_metadata(
            reasons=reasons,
            flags=flags,
            hard_reject=False,
            source_quality=source_quality,
            exactness_confidence=exactness_confidence,
            target_model_is_broad=target_model_is_broad,
            target_version_tokens=sorted(target_version_tokens),
            result_version_tokens=sorted(result_version_tokens),
            bundle_hits=bundle_hits,
            accessory_hits=accessory_hits,
            marketplace_domain=domain,
            listing_page_confidence=listing_page_confidence,
        )

    def _fallback_metadata(
        self,
        *,
        reasons: list[str],
        flags: list[str],
        hard_reject: bool,
        source_quality: str,
        exactness_confidence: float,
        target_model_is_broad: bool,
        target_version_tokens: list[str],
        result_version_tokens: list[str],
        bundle_hits: list[str],
        accessory_hits: list[str],
        marketplace_domain: str,
        listing_page_confidence: str,
    ) -> dict[str, Any]:
        deduped_flags = list(dict.fromkeys(flags))
        deduped_reasons = list(dict.fromkeys(reasons))
        return {
            "provider": "serpapi_used_market",
            "marketplace_domain": marketplace_domain,
            "listing_page_confidence": listing_page_confidence,
            "source_quality": source_quality,
            "source_quality_rank": FALLBACK_SOURCE_QUALITY_RANK[source_quality],
            "exactness_confidence": exactness_confidence,
            "target_model_is_broad": target_model_is_broad,
            "target_version_tokens": target_version_tokens,
            "result_version_tokens": result_version_tokens,
            "bundle_hits": bundle_hits,
            "accessory_hits": accessory_hits,
            "flags": deduped_flags,
            "reasons": deduped_reasons,
            "hard_reject": hard_reject,
        }
