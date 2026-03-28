"""Job scheduler — creates crawl jobs based on product priority tiers.

Tier schedule:
  HOT  → every 24h (priority 1-2, high-traffic products)
  WARM → every 72h (priority 3, standard products)
  COLD → every 168h (priority 4+, long-tail products)

Runs as a cron/CLI task, not a daemon. Idempotent: won't create
duplicate jobs if a pending/running job already exists for a product.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from backend.app.db.database import async_session
from backend.app.db.models import AgentJob, Product
from backend.app.services.job_queue import PENDING, RUNNING, enqueue_job
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

# Tier → (crawl interval hours, job priority)
TIER_CONFIG = {
    "hot":  {"interval_hours": 24,  "priority": 1},
    "warm": {"interval_hours": 72,  "priority": 5},
    "cold": {"interval_hours": 168, "priority": 8},
}

# Map seed priority (1/2/3) → crawl tier
SEED_PRIORITY_TO_TIER = {
    1: "hot",
    2: "warm",
    3: "cold",
}


async def schedule_due_products(
    max_jobs: int = 50,
    dry_run: bool = False,
) -> list[dict]:
    """Create crawl jobs for products that are due for a crawl.

    Idempotent: skips products that already have a pending/running job.
    Returns list of scheduled product dicts.
    """
    now = datetime.now(timezone.utc)
    scheduled: list[dict] = []

    try:
        async with async_session() as session:
            # Get all crawl-enabled products
            result = await session.execute(
                select(Product).where(Product.crawl_enabled.is_(True))
            )
            products = result.scalars().all()

            # Get products with active (pending/running) jobs — skip these
            active_result = await session.execute(
                text("""
                    SELECT DISTINCT product_key
                    FROM agent_job
                    WHERE status IN ('pending', 'running')
                """)
            )
            active_keys = {row[0] for row in active_result}

            for product in products:
                if len(scheduled) >= max_jobs:
                    break

                # Skip if already has active job
                if product.product_key in active_keys:
                    continue

                # Determine tier and interval
                tier = product.crawl_tier or "warm"
                config = TIER_CONFIG.get(tier, TIER_CONFIG["warm"])
                interval = timedelta(hours=config["interval_hours"])

                # Skip if crawled recently
                if product.last_crawled_at and (now - product.last_crawled_at) < interval:
                    continue

                # Due for crawl
                if dry_run:
                    scheduled.append({
                        "product_key": product.product_key,
                        "tier": tier,
                        "priority": config["priority"],
                        "last_crawled": product.last_crawled_at.isoformat() if product.last_crawled_at else None,
                    })
                else:
                    job_id = await enqueue_job(
                        product_key=product.product_key,
                        source="scheduler",
                        task_type="crawl",
                        priority=config["priority"],
                    )
                    scheduled.append({
                        "product_key": product.product_key,
                        "job_id": job_id,
                        "tier": tier,
                        "priority": config["priority"],
                    })

        logger.info("scheduler.run", extra={
            "scheduled": len(scheduled),
            "total_products": len(products),
            "active_jobs": len(active_keys),
            "dry_run": dry_run,
        })
    except Exception as exc:
        logger.error("scheduler.failed", extra={"error": str(exc)})

    return scheduled


async def assign_tiers_from_seed() -> int:
    """Assign crawl_tier to products based on their seed priority.

    Products with priority 1 → hot, 2 → warm, 3 → cold.
    Returns count of products updated.
    """
    import json
    from pathlib import Path

    seed_file = Path(__file__).resolve().parents[1] / "data" / "seed_products.json"
    if not seed_file.exists():
        return 0

    seed_data = json.loads(seed_file.read_text())
    updated = 0

    try:
        async with async_session() as session:
            from backend.app.utils.normalization import normalize_product_key
            for item in seed_data:
                pk = normalize_product_key(item["brand"], item["model"])
                tier = SEED_PRIORITY_TO_TIER.get(item.get("priority", 3), "cold")
                result = await session.execute(
                    text("UPDATE product SET crawl_tier = :tier WHERE product_key = :pk AND (crawl_tier IS NULL OR crawl_tier != :tier)"),
                    {"tier": tier, "pk": pk},
                )
                updated += result.rowcount
            await session.commit()
    except Exception as exc:
        logger.error("scheduler.assign_tiers_failed", extra={"error": str(exc)})

    logger.info("scheduler.tiers_assigned", extra={"updated": updated})
    return updated
