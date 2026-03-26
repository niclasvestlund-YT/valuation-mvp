#!/usr/bin/env python3
"""Database cleanup script for stale data and quality maintenance.

Usage:
    python scripts/cleanup_db.py --report              # show stats only
    python scripts/cleanup_db.py --max-age 90          # remove comparables older than 90 days
    python scripts/cleanup_db.py --deduplicate         # merge duplicate product keys
    python scripts/cleanup_db.py --flag-outliers       # flag price outliers
    python scripts/cleanup_db.py --dry-run --max-age 90  # preview what would be deleted
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select, update  # noqa: E402

from backend.app.db.database import async_session  # noqa: E402
from backend.app.db.models import MarketComparable, NewPriceSnapshot, Product  # noqa: E402


async def report():
    """Print data quality report."""
    async with async_session() as session:
        products = (await session.execute(select(func.count()).select_from(Product))).scalar() or 0
        comparables = (await session.execute(select(func.count()).select_from(MarketComparable))).scalar() or 0
        active = (await session.execute(
            select(func.count()).select_from(MarketComparable).where(MarketComparable.is_active.is_(True))
        )).scalar() or 0
        flagged = (await session.execute(
            select(func.count()).select_from(MarketComparable).where(MarketComparable.flagged.is_(True))
        )).scalar() or 0
        new_prices = (await session.execute(select(func.count()).select_from(NewPriceSnapshot))).scalar() or 0

        cutoff_90 = datetime.now(timezone.utc) - timedelta(days=90)
        stale = (await session.execute(
            select(func.count()).select_from(MarketComparable).where(MarketComparable.last_seen < cutoff_90)
        )).scalar() or 0

        print(f"\n{'=' * 50}")
        print(f"  Data Quality Report")
        print(f"{'=' * 50}")
        print(f"  Products:           {products}")
        print(f"  Comparables:        {comparables}")
        print(f"    Active:           {active}")
        print(f"    Inactive:         {comparables - active}")
        print(f"    Flagged:          {flagged}")
        print(f"    Stale (>90d):     {stale}")
        print(f"  New Price Snapshots: {new_prices}")
        print(f"{'=' * 50}\n")


async def cleanup_stale(max_age_days: int, dry_run: bool):
    """Remove comparables older than max_age_days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    async with async_session() as session:
        count = (await session.execute(
            select(func.count()).select_from(MarketComparable)
            .where(MarketComparable.last_seen < cutoff, MarketComparable.is_active.is_(False))
        )).scalar() or 0

        if dry_run:
            print(f"[DRY RUN] Would delete {count} stale inactive comparables older than {max_age_days} days")
            return

        if count:
            await session.execute(
                delete(MarketComparable)
                .where(MarketComparable.last_seen < cutoff, MarketComparable.is_active.is_(False))
            )
            await session.commit()
            print(f"Deleted {count} stale inactive comparables older than {max_age_days} days")
        else:
            print("No stale comparables to delete")


async def flag_outliers(dry_run: bool):
    """Flag price outliers (>3x median for their product)."""
    async with async_session() as session:
        products = (await session.execute(
            select(MarketComparable.product_key).distinct()
        )).scalars().all()

        flagged_count = 0
        for pk in products:
            rows = (await session.execute(
                select(MarketComparable.price_sek)
                .where(MarketComparable.product_key == pk, MarketComparable.is_active.is_(True))
            )).scalars().all()

            if len(rows) < 3:
                continue

            sorted_prices = sorted(rows)
            med = sorted_prices[len(sorted_prices) // 2]

            outlier_ids = (await session.execute(
                select(MarketComparable.id)
                .where(
                    MarketComparable.product_key == pk,
                    MarketComparable.is_active.is_(True),
                    MarketComparable.price_sek > med * 3,
                    MarketComparable.flagged.is_(False),
                )
            )).scalars().all()

            if outlier_ids:
                if not dry_run:
                    await session.execute(
                        update(MarketComparable)
                        .where(MarketComparable.id.in_(outlier_ids))
                        .values(flagged=True, flag_reason="price_outlier_3x_median")
                    )
                flagged_count += len(outlier_ids)

        if not dry_run:
            await session.commit()

        prefix = "[DRY RUN] Would flag" if dry_run else "Flagged"
        print(f"{prefix} {flagged_count} price outliers across {len(products)} products")


async def deduplicate(dry_run: bool):
    """Find and report duplicate product keys (case/formatting differences)."""
    async with async_session() as session:
        products = (await session.execute(select(Product))).scalars().all()
        seen: dict[str, list[str]] = {}
        for p in products:
            normalized = p.product_key.lower().replace(" ", "-")
            seen.setdefault(normalized, []).append(p.product_key)

        dupes = {k: v for k, v in seen.items() if len(v) > 1}
        if dupes:
            print(f"Found {len(dupes)} duplicate product key groups:")
            for norm, keys in dupes.items():
                print(f"  {norm}: {keys}")
        else:
            print("No duplicate product keys found")


def main():
    parser = argparse.ArgumentParser(description="Database cleanup and quality maintenance")
    parser.add_argument("--report", action="store_true", help="Show data quality report")
    parser.add_argument("--max-age", type=int, default=None, help="Remove stale comparables older than N days")
    parser.add_argument("--deduplicate", action="store_true", help="Find duplicate product keys")
    parser.add_argument("--flag-outliers", action="store_true", help="Flag price outliers")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    args = parser.parse_args()

    if not any([args.report, args.max_age, args.deduplicate, args.flag_outliers]):
        args.report = True

    async def run():
        if args.report:
            await report()
        if args.max_age:
            await cleanup_stale(args.max_age, args.dry_run)
        if args.deduplicate:
            await deduplicate(args.dry_run)
        if args.flag_outliers:
            await flag_outliers(args.dry_run)

    asyncio.run(run())


if __name__ == "__main__":
    main()
