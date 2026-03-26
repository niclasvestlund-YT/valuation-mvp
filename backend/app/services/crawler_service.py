"""Background crawler for pre-populating the comparable cache.

Searches Blocket + Tradera for known products and upserts results
into the same DB tables the live pipeline uses.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.core.config import settings
from backend.app.db.crud import get_latest_new_price, upsert_comparables, upsert_new_price, upsert_product
from backend.app.integrations.blocket_client import BlocketClient
from backend.app.integrations.tradera_client import TraderaClient
from backend.app.services.new_price_service import NewPriceService
from backend.app.utils.logger import get_logger
from backend.app.utils.normalization import normalize_product_key

logger = get_logger(__name__)

SEED_FILE = Path(__file__).resolve().parents[1] / "data" / "seed_products.json"


@dataclass
class SeedProduct:
    brand: str
    model: str
    category: str | None = None
    priority: int = 3

    @property
    def product_key(self) -> str:
        return normalize_product_key(self.brand, self.model)

    @property
    def search_query(self) -> str:
        return f"{self.brand} {self.model}"


@dataclass
class CrawlResult:
    product_key: str
    blocket_count: int = 0
    tradera_count: int = 0
    new_price_fetched: bool = False
    error: str | None = None
    duration_ms: int = 0


def load_seed_products(priorities: set[int] | None = None) -> list[SeedProduct]:
    """Load seed products from JSON, optionally filtered by priority."""
    with open(SEED_FILE) as f:
        data = json.load(f)

    products = [SeedProduct(**item) for item in data]
    if priorities:
        products = [p for p in products if p.priority in priorities]

    return products


async def crawl_product(
    product: SeedProduct,
    *,
    use_serper: bool = False,
    tradera_client: TraderaClient | None = None,
    blocket_client: BlocketClient | None = None,
    new_price_service: NewPriceService | None = None,
) -> CrawlResult:
    """Crawl a single product from all configured sources."""
    t0 = time.monotonic()
    result = CrawlResult(product_key=product.product_key)

    try:
        # Upsert product identity
        await upsert_product(product.product_key, product.brand, product.model, product.category)

        blocket = blocket_client or BlocketClient()
        query = product.search_query

        # Blocket (always available)
        try:
            blocket_results = blocket.search(query)
            blocket_comps = [
                {
                    "title": getattr(r, "title", "") or r.get("title", "") if isinstance(r, dict) else r.title,
                    "price": getattr(r, "price", 0) or r.get("price", 0) if isinstance(r, dict) else r.price,
                    "url": getattr(r, "url", "") or r.get("url", "") if isinstance(r, dict) else (r.url or ""),
                }
                for r in blocket_results
                if r
            ]
            if blocket_comps:
                await upsert_comparables(product.product_key, blocket_comps, source="blocket")
                result.blocket_count = len(blocket_comps)
        except Exception as exc:
            logger.warning("crawler.blocket_error", extra={"product_key": product.product_key, "error": str(exc)})

        # Tradera (if configured)
        tradera = tradera_client or TraderaClient()
        if tradera.is_configured:
            try:
                tradera_results = tradera.search(query)
                tradera_comps = [
                    {
                        "title": str(r.get("ShortDescription") or r.get("Title") or ""),
                        "price": float(r.get("MaxBid") or r.get("CurrentPrice") or r.get("BuyItNowPrice") or 0),
                        "url": str(r.get("ItemUrl") or r.get("Url") or ""),
                    }
                    for r in tradera_results
                    if r
                ]
                if tradera_comps:
                    await upsert_comparables(product.product_key, tradera_comps, source="tradera")
                    result.tradera_count = len(tradera_comps)
            except Exception as exc:
                logger.warning("crawler.tradera_error", extra={"product_key": product.product_key, "error": str(exc)})

            # Rate limit Tradera
            await asyncio.sleep(settings.crawler_tradera_sleep)

        # New price (if enabled and not recently fetched)
        if use_serper:
            cached = await get_latest_new_price(product.product_key)
            cache_fresh = False
            if cached and cached.get("fetched_at"):
                fetched_at = cached["fetched_at"]
                if hasattr(fetched_at, "timestamp"):
                    age_hours = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
                    cache_fresh = age_hours < 48

            if not cache_fresh:
                try:
                    svc = new_price_service or NewPriceService()
                    price_data = svc.get_new_price(product.brand, product.model, category=product.category)
                    est = price_data.get("estimated_new_price")
                    if est:
                        sources = price_data.get("sources") or []
                        await upsert_new_price(
                            product.product_key,
                            int(est),
                            source=price_data.get("method") or "serper",
                            currency=price_data.get("currency") or "SEK",
                            url=sources[0].get("url") if sources else None,
                            title=sources[0].get("title") if sources else None,
                        )
                        result.new_price_fetched = True
                except Exception as exc:
                    logger.warning("crawler.new_price_error", extra={"product_key": product.product_key, "error": str(exc)})

    except Exception as exc:
        result.error = str(exc)
        logger.error("crawler.product_error", extra={"product_key": product.product_key, "error": str(exc)})

    result.duration_ms = int((time.monotonic() - t0) * 1000)
    return result


async def run_crawl(
    *,
    priorities: set[int] | None = None,
    max_products: int | None = None,
    use_serper: bool = False,
    dry_run: bool = False,
) -> list[CrawlResult]:
    """Run the crawler for a batch of seed products."""
    products = load_seed_products(priorities)
    if max_products:
        products = products[:max_products]

    logger.info("crawler.start", extra={
        "product_count": len(products),
        "priorities": sorted(priorities) if priorities else "all",
        "use_serper": use_serper,
        "dry_run": dry_run,
    })

    if dry_run:
        return [CrawlResult(product_key=p.product_key) for p in products]

    results: list[CrawlResult] = []
    for product in products:
        result = await crawl_product(product, use_serper=use_serper)
        results.append(result)
        logger.info("crawler.product_done", extra={
            "product_key": result.product_key,
            "blocket": result.blocket_count,
            "tradera": result.tradera_count,
            "new_price": result.new_price_fetched,
            "duration_ms": result.duration_ms,
        })
        await asyncio.sleep(settings.crawler_sleep_seconds)

    total_blocket = sum(r.blocket_count for r in results)
    total_tradera = sum(r.tradera_count for r in results)
    errors = sum(1 for r in results if r.error)
    logger.info("crawler.complete", extra={
        "products": len(results),
        "total_blocket": total_blocket,
        "total_tradera": total_tradera,
        "errors": errors,
    })

    return results
