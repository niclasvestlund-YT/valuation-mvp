import re
from datetime import UTC, datetime

import asyncio

from backend.app.integrations.blocket_client import BlocketClient
from backend.app.integrations.serpapi_used_market_client import SerpApiUsedMarketClient
from backend.app.integrations.tradera_client import TraderaClient
from backend.app.integrations.vinted_client import fetch_vinted
from backend.app.schemas.market_comparable import MarketComparable
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

_COLOR_WORDS = {
    "black", "white", "silver", "gold", "blue", "red", "green", "pink",
    "graphite", "platinum", "midnight", "starlight", "natural", "titanium",
    "svart", "vit", "silver", "guld", "blå", "röd", "grön",
}


def strip_color_words(model: str | None) -> str:
    if not model:
        return ""
    tokens = model.split()
    return " ".join(t for t in tokens if t.lower() not in _COLOR_WORDS).strip()


def build_search_query(*parts: str | None) -> str:
    return " ".join(" ".join((part or "").split()) for part in parts if part).strip()


def normalize_query_text(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def build_model_aliases(model: str | None) -> list[str]:
    normalized = normalize_query_text(model)
    aliases: list[str] = []

    if "osmo action" in normalized:
        aliases.append(normalized.replace("osmo ", "", 1))
    elif normalized.startswith("action "):
        aliases.append(f"osmo {normalized}")

    deduped: list[str] = []
    seen: set[str] = {normalized}
    for alias in aliases:
        if not alias or alias in seen:
            continue
        seen.add(alias)
        deduped.append(alias)

    return deduped


def tokenize_query_part(value: str | None) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", value or "")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)

    return parsed


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None

    cleaned = (
        value.replace("SEK", "")
        .replace("kr", "")
        .replace(",", ".")
        .strip()
    )
    if not cleaned:
        return None

    try:
        return float(cleaned)
    except ValueError:
        return None


class MarketDataService:
    def __init__(
        self,
        tradera_client: TraderaClient | None = None,
        blocket_client: BlocketClient | None = None,
        serpapi_used_market_client: SerpApiUsedMarketClient | None = None,
    ) -> None:
        self.tradera_client = tradera_client or TraderaClient()
        self.blocket_client = blocket_client or BlocketClient()
        self.serpapi_used_market_client = serpapi_used_market_client or SerpApiUsedMarketClient()

    def get_comparables(
        self,
        *,
        brand: str,
        model: str,
        category: str | None = None,
    ) -> list[MarketComparable]:
        clean_model = strip_color_words(model)
        exact_query = build_search_query(brand, clean_model)
        exact_query_aliases = [build_search_query(brand, alias) for alias in build_model_aliases(clean_model)]
        fallback_queries = self._build_fallback_queries(
            brand=brand,
            model=clean_model,
            category=category,
        )

        if not exact_query:
            return []

        # ── Blocket (primary, always available — no API key required) ──────────
        blocket_results = self.blocket_client.search(exact_query)
        logger.info(
            "market_data.blocket.results brand=%s model=%s count=%s",
            brand,
            model,
            len(blocket_results),
        )

        # ── Vinted (no API key, uses curl_cffi browser impersonation) ─────────
        vinted_results: list[MarketComparable] = []
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    vinted_results = pool.submit(
                        asyncio.run, fetch_vinted(exact_query, category=category)
                    ).result(timeout=12)
            else:
                vinted_results = asyncio.run(fetch_vinted(exact_query, category=category))
            logger.info(
                "market_data.vinted.results brand=%s model=%s count=%s",
                brand,
                model,
                len(vinted_results),
            )
        except Exception as exc:
            logger.warning(
                "market_data.vinted.failed brand=%s model=%s error=%s",
                brand,
                model,
                exc,
            )

        # ── Tradera (primary, requires credentials) ───────────────────────────
        # Progressive fallback: each tier only runs if the previous returned < 5 results.
        # This prevents broad fallback queries ("DJI Osmo", "DJI camera") from flooding
        # results when the exact query already found enough listings.
        _TRADERA_SUFFICIENT = 5
        tradera_results: list[MarketComparable] = []
        if self.tradera_client.is_configured:
            staged: list[MarketComparable] = []
            queries_run: list[str] = []

            def _run_tradera_query(q: str) -> None:
                normalized = self._normalize_results(self.tradera_client.search(q))
                staged.extend(self._filter_by_status(normalized, "completed"))
                staged.extend(self._filter_by_status(normalized, "active"))
                queries_run.append(q)

            _run_tradera_query(exact_query)
            for alias_query in exact_query_aliases:
                if len(self._dedupe_by_listing_id(staged)) >= _TRADERA_SUFFICIENT:
                    break
                _run_tradera_query(alias_query)
            if len(self._dedupe_by_listing_id(staged)) < _TRADERA_SUFFICIENT:
                for fallback_query in fallback_queries:
                    if len(self._dedupe_by_listing_id(staged)) >= _TRADERA_SUFFICIENT:
                        break
                    _run_tradera_query(fallback_query)

            tradera_results = self._dedupe_by_listing_id(staged)
            logger.info(
                "market_data.tradera.results queries_run=%s count=%s",
                queries_run,
                len(tradera_results),
            )
        else:
            logger.info(
                "market_data.tradera.not_configured brand=%s model=%s",
                brand,
                model,
            )

        # ── Merge primary sources ─────────────────────────────────────────────
        deduped_results = self._dedupe_by_listing_id([*tradera_results, *blocket_results, *vinted_results])

        # ── SerpAPI fallback — only when primary sources returned nothing ────
        # Skipped entirely when SERPAPI_API_KEY is absent.
        if not deduped_results and self.serpapi_used_market_client.is_configured:
            logger.info(
                "market_data.serpapi_fallback brand=%s model=%s reason=primary_sources_empty",
                brand,
                model,
            )
            serpapi_results = self.serpapi_used_market_client.search(
                brand=brand,
                model=model,
                category=category,
            )
            if serpapi_results:
                deduped_results = self._dedupe_by_listing_id(
                    self._sort_fallback_results(serpapi_results)
                )

        logger.info(
            "market_data.total brand=%s model=%s count=%s",
            brand,
            model,
            len(deduped_results),
        )
        return deduped_results

    def _normalize_results(self, raw_results: list[dict]) -> list[MarketComparable]:
        normalized: list[MarketComparable] = []

        for raw in raw_results:
            listing_id = str(raw.get("ItemId") or raw.get("Id") or raw.get("ItemURL") or raw.get("ShortDescription") or "").strip()
            title = str(
                raw.get("ShortDescription")
                or raw.get("Description")
                or raw.get("Title")
                or raw.get("Name")
                or ""
            ).strip()
            price = (
                parse_float(raw.get("MaxBid"))
                or parse_float(raw.get("CurrentPrice"))
                or parse_float(raw.get("BuyItNowPrice"))
                or parse_float(raw.get("Price"))
            )

            if not listing_id or not title or price is None:
                continue

            ended_at = parse_datetime(raw.get("EndDate") or raw.get("EndedAt"))
            status = self._normalize_status(raw.get("ItemStatus") or raw.get("Status"), ended_at)

            normalized.append(
                MarketComparable(
                    source="Tradera",
                    listing_id=listing_id,
                    title=title,
                    price=price,
                    currency=str(raw.get("Currency") or "SEK").strip() or "SEK",
                    status=status,
                    url=raw.get("ItemUrl") or raw.get("Url") or raw.get("LinkUrl"),
                    ended_at=ended_at,
                    shipping_cost=parse_float(raw.get("ShippingCost") or raw.get("ShippingFee") or raw.get("Freight")),
                    condition_hint=raw.get("ItemCondition") or raw.get("Condition"),
                    raw=raw,
                )
            )

        return normalized

    def _normalize_status(self, raw_status: str | None, ended_at: datetime | None) -> str:
        status = (raw_status or "").strip().lower()

        if any(token in status for token in ["ended", "closed", "sold", "completed", "inactive"]):
            return "completed"

        if any(token in status for token in ["active", "open", "running"]):
            return "active"

        if ended_at is not None:
            now = datetime.now(UTC)
            if ended_at <= now:
                return "completed"
            return "active"

        return "unknown"

    def _filter_by_status(self, comparables: list[MarketComparable], status: str) -> list[MarketComparable]:
        return [comparable for comparable in comparables if comparable.status == status]

    def _dedupe_by_listing_id(self, comparables: list[MarketComparable]) -> list[MarketComparable]:
        deduped: list[MarketComparable] = []
        seen_listing_ids: set[tuple[str, str]] = set()

        for comparable in comparables:
            identity = (
                str(comparable.source),
                str(comparable.url or comparable.listing_id),
            )
            if identity in seen_listing_ids:
                continue

            seen_listing_ids.add(identity)
            deduped.append(comparable)

        return deduped

    def _sort_fallback_results(self, comparables: list[MarketComparable]) -> list[MarketComparable]:
        return sorted(
            comparables,
            key=lambda comparable: (
                self._fallback_exactness_confidence(comparable),
                self._fallback_source_quality_rank(comparable),
                comparable.price,
            ),
            reverse=True,
        )

    def _fallback_source_quality(self, comparable: MarketComparable) -> str:
        metadata = comparable.raw.get("_fallback_metadata", {})
        return str(metadata.get("source_quality") or "")

    def _fallback_source_quality_rank(self, comparable: MarketComparable) -> int:
        metadata = comparable.raw.get("_fallback_metadata", {})
        value = metadata.get("source_quality_rank")
        return int(value) if isinstance(value, int | float) else 0

    def _fallback_exactness_confidence(self, comparable: MarketComparable) -> float:
        metadata = comparable.raw.get("_fallback_metadata", {})
        value = metadata.get("exactness_confidence")
        return float(value) if isinstance(value, int | float) else 0.0

    def _build_fallback_queries(
        self,
        *,
        brand: str,
        model: str,
        category: str | None = None,
    ) -> list[str]:
        model_tokens = tokenize_query_part(model)
        normalized_model = normalize_query_text(model)
        fallback_queries: list[str] = []

        # For Osmo action cameras, skip the first-token fallback ("DJI Osmo") — it is far
        # too broad and floods results with unrelated DJI Osmo products (Pocket, Gimbal, 360).
        # The alias query ("DJI Action 5 Pro") already runs before fallbacks, so we only
        # add a generation-level fallback here.
        is_osmo_action = "osmo" in normalized_model and "action" in normalized_model
        if not is_osmo_action:
            if model_tokens:
                fallback_queries.append(build_search_query(brand, model_tokens[0]))
            if len(model_tokens) >= 2:
                fallback_queries.append(build_search_query(*model_tokens[:2]))
        else:
            # For Osmo Action: use brand + "action" + generation number as fallback
            action_idx = next((i for i, t in enumerate(model_tokens) if t.lower() == "action"), None)
            if action_idx is not None and action_idx + 1 < len(model_tokens):
                gen_token = model_tokens[action_idx + 1]
                fallback_queries.append(build_search_query(brand, "action", gen_token))

        fallback_queries.append(build_search_query(brand, category))

        deduped_queries: list[str] = []
        seen_queries: set[str] = set()
        for query in fallback_queries:
            if not query or query in seen_queries:
                continue
            seen_queries.add(query)
            deduped_queries.append(query)

        return deduped_queries
