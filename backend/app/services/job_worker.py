"""Crawl job worker — claims jobs from queue and executes them.

No daemon, no threads. Runs as a simple async loop that:
1. Claims next pending job
2. Runs the crawl for that product
3. Saves results via existing pipeline
4. Marks job complete/failed

Designed to be called from a CLI script or cron.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from sqlalchemy import text

from backend.app.db.database import async_session
from backend.app.integrations.blocket_client import BlocketClient
from backend.app.integrations.tradera_client import TraderaClient
from backend.app.db.crud import upsert_comparables, upsert_product
from backend.app.services.data_validator import validate_comparable
from backend.app.services.job_queue import claim_next_job, complete_job, fail_job
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

# Rate limiting between products
INTER_JOB_DELAY = 5  # seconds between jobs
TRADERA_DELAY = 3    # seconds between Tradera calls


async def execute_crawl_job(job: dict) -> dict:
    """Execute a single crawl job. Returns result dict.

    Steps:
    1. Generate search queries for the product
    2. Fetch from Blocket + Tradera
    3. Normalize + validate
    4. Store via existing CRUD
    5. Update product.last_crawled_at
    """
    t0 = time.monotonic()
    product_key = job["product_key"]
    result = {"blocket": 0, "tradera": 0, "rejected": 0, "errors": []}

    # Resolve brand + model from product key
    parts = product_key.split("_", 1)
    brand = parts[0].title() if parts else ""
    model = parts[1].replace("-", " ").title() if len(parts) > 1 else ""
    query = f"{brand} {model}".strip()

    if not query:
        raise ValueError(f"Cannot build query for product_key={product_key}")

    # Upsert product identity
    await upsert_product(product_key, brand, model)

    # Blocket (always available, no API key)
    try:
        blocket = BlocketClient()
        blocket_results = blocket.search(query)
        blocket_comps = [
            {
                "title": getattr(r, "title", ""),
                "price": getattr(r, "price", 0),
                "url": getattr(r, "url", ""),
            }
            for r in blocket_results if r
        ]
        if blocket_comps:
            counts = await upsert_comparables(product_key, blocket_comps, source="blocket")
            result["blocket"] = counts.get("inserted", 0) + counts.get("updated", 0)
            result["rejected"] += counts.get("rejected", 0)
    except Exception as exc:
        logger.warning("worker.blocket_error", extra={"product_key": product_key, "error": str(exc)})
        result["errors"].append(f"blocket: {exc}")

    # Tradera (if configured)
    try:
        tradera = TraderaClient()
        if tradera.is_configured:
            await asyncio.sleep(TRADERA_DELAY)
            tradera_results = tradera.search(query)
            tradera_comps = [
                {
                    "title": str(r.get("ShortDescription") or r.get("Title") or ""),
                    "price": float(r.get("MaxBid") or r.get("CurrentPrice") or r.get("BuyItNowPrice") or 0),
                    "url": str(r.get("ItemUrl") or r.get("Url") or ""),
                }
                for r in tradera_results if r
            ]
            if tradera_comps:
                counts = await upsert_comparables(product_key, tradera_comps, source="tradera")
                result["tradera"] = counts.get("inserted", 0) + counts.get("updated", 0)
                result["rejected"] += counts.get("rejected", 0)
    except Exception as exc:
        logger.warning("worker.tradera_error", extra={"product_key": product_key, "error": str(exc)})
        result["errors"].append(f"tradera: {exc}")

    # Update last_crawled_at
    try:
        async with async_session() as session:
            await session.execute(
                text("UPDATE product SET last_crawled_at = :now WHERE product_key = :pk"),
                {"now": datetime.now(timezone.utc), "pk": product_key},
            )
            await session.commit()
    except Exception:
        pass  # Non-critical

    result["duration_ms"] = int((time.monotonic() - t0) * 1000)
    result["total"] = result["blocket"] + result["tradera"]
    return result


async def run_worker(
    max_jobs: int = 50,
    stop_on_empty: bool = True,
) -> list[dict]:
    """Process jobs from the queue until empty or max_jobs reached.

    Returns list of job results.
    """
    results: list[dict] = []

    for i in range(max_jobs):
        job = await claim_next_job()
        if not job:
            if stop_on_empty:
                logger.info("worker.queue_empty", extra={"processed": len(results)})
                break
            # Wait and retry
            await asyncio.sleep(10)
            continue

        job_id = job["id"]
        product_key = job["product_key"]

        try:
            result = await execute_crawl_job(job)
            await complete_job(
                job_id,
                observations_added=result["total"],
                observations_rejected=result["rejected"],
                summary=f"blocket:{result['blocket']} tradera:{result['tradera']}",
            )
            result["job_id"] = job_id
            result["product_key"] = product_key
            result["status"] = "completed"
            results.append(result)
            logger.info("worker.job_done", extra={
                "job_id": job_id, "product_key": product_key,
                "total": result["total"], "duration_ms": result["duration_ms"],
            })
        except Exception as exc:
            await fail_job(
                job_id,
                error_message=str(exc),
                attempts=job["attempts"],
                max_attempts=job["max_attempts"],
            )
            results.append({
                "job_id": job_id,
                "product_key": product_key,
                "status": "failed",
                "error": str(exc),
            })
            logger.error("worker.job_failed", extra={
                "job_id": job_id, "product_key": product_key, "error": str(exc),
            })

        # Rate limit between jobs
        if i < max_jobs - 1:
            await asyncio.sleep(INTER_JOB_DELAY)

    logger.info("worker.batch_done", extra={
        "processed": len(results),
        "succeeded": sum(1 for r in results if r.get("status") == "completed"),
        "failed": sum(1 for r in results if r.get("status") == "failed"),
    })
    return results
