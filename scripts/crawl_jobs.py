#!/usr/bin/env python3
"""Crawl job system CLI — scheduler, worker, status.

Usage:
    # Schedule due products for crawling
    python scripts/crawl_jobs.py schedule --dry-run
    python scripts/crawl_jobs.py schedule --max 20

    # Assign crawl tiers from seed_products.json
    python scripts/crawl_jobs.py assign-tiers

    # Run the worker (process pending jobs)
    python scripts/crawl_jobs.py work --max 10

    # Show queue status
    python scripts/crawl_jobs.py status

    # Full run: schedule + work
    python scripts/crawl_jobs.py run --max 20
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.job_queue import get_queue_stats  # noqa: E402
from backend.app.services.job_scheduler import assign_tiers_from_seed, schedule_due_products  # noqa: E402
from backend.app.services.job_worker import run_worker  # noqa: E402


async def cmd_schedule(args):
    scheduled = await schedule_due_products(max_jobs=args.max, dry_run=args.dry_run)
    prefix = "[DRY]" if args.dry_run else "✓"
    print(f"\n{'='*60}")
    print(f"Scheduled {len(scheduled)} crawl jobs")
    for s in scheduled[:20]:
        print(f"  {prefix} {s['product_key']} (tier={s['tier']}, priority={s['priority']})")
    if len(scheduled) > 20:
        print(f"  ... and {len(scheduled) - 20} more")
    print(f"{'='*60}\n")


async def cmd_assign_tiers(args):
    updated = await assign_tiers_from_seed()
    print(f"Updated {updated} product crawl tiers from seed_products.json")


async def cmd_work(args):
    results = await run_worker(max_jobs=args.max, stop_on_empty=True)
    succeeded = sum(1 for r in results if r.get("status") == "completed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    total_listings = sum(r.get("total", 0) for r in results if r.get("status") == "completed")

    print(f"\n{'='*60}")
    print(f"Worker processed {len(results)} jobs")
    print(f"  Succeeded: {succeeded}")
    print(f"  Failed: {failed}")
    print(f"  Total listings: {total_listings}")
    for r in results:
        status = r.get("status", "?")
        pk = r.get("product_key", "?")
        if status == "completed":
            print(f"  ✓ {pk}: {r.get('total',0)} listings ({r.get('duration_ms',0)}ms)")
        else:
            print(f"  ✗ {pk}: {r.get('error','unknown')}")
    print(f"{'='*60}\n")


async def cmd_status(args):
    stats = await get_queue_stats()
    print(f"\n{'='*40}")
    print(f"  Job Queue Status")
    print(f"{'='*40}")
    for key, val in stats.items():
        print(f"  {key:>12}: {val}")
    print(f"{'='*40}\n")


async def cmd_run(args):
    # Schedule + work in one command
    scheduled = await schedule_due_products(max_jobs=args.max)
    print(f"Scheduled {len(scheduled)} jobs")
    if scheduled:
        results = await run_worker(max_jobs=args.max, stop_on_empty=True)
        succeeded = sum(1 for r in results if r.get("status") == "completed")
        total_listings = sum(r.get("total", 0) for r in results if r.get("status") == "completed")
        print(f"Processed {len(results)} jobs: {succeeded} succeeded, {total_listings} listings")
    else:
        print("No products due for crawling")


def main():
    parser = argparse.ArgumentParser(description="Crawl job system")
    sub = parser.add_subparsers(dest="command", required=True)

    p_schedule = sub.add_parser("schedule", help="Schedule due products for crawling")
    p_schedule.add_argument("--max", type=int, default=50)
    p_schedule.add_argument("--dry-run", action="store_true")

    sub.add_parser("assign-tiers", help="Assign crawl tiers from seed_products.json")

    p_work = sub.add_parser("work", help="Process pending jobs from the queue")
    p_work.add_argument("--max", type=int, default=50)

    sub.add_parser("status", help="Show queue status")

    p_run = sub.add_parser("run", help="Schedule + work in one step")
    p_run.add_argument("--max", type=int, default=20)

    args = parser.parse_args()
    cmd_map = {
        "schedule": cmd_schedule,
        "assign-tiers": cmd_assign_tiers,
        "work": cmd_work,
        "status": cmd_status,
        "run": cmd_run,
    }
    asyncio.run(cmd_map[args.command](args))


if __name__ == "__main__":
    main()
