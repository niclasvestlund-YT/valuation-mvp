#!/usr/bin/env python3
"""CLI script to crawl prices for seed products.

Usage:
    python scripts/crawl_prices.py --priority 1,2 --max 20 --dry-run
    python scripts/crawl_prices.py --priority 1 --with-new-prices
    python scripts/crawl_prices.py                              # all products, no Serper
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.crawler_service import run_crawl  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Crawl prices for seed products")
    parser.add_argument(
        "--priority",
        type=str,
        default=None,
        help="Comma-separated priority tiers (1,2,3). Default: all",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Max products to crawl",
    )
    parser.add_argument(
        "--with-new-prices",
        action="store_true",
        help="Also fetch new prices via Serper (uses API credits!)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List products without crawling",
    )
    args = parser.parse_args()

    priorities = None
    if args.priority:
        priorities = {int(p.strip()) for p in args.priority.split(",")}

    results = asyncio.run(run_crawl(
        priorities=priorities,
        max_products=args.max,
        use_serper=args.with_new_prices,
        dry_run=args.dry_run,
    ))

    print(f"\n{'=' * 60}")
    print(f"Crawl complete: {len(results)} products")
    if args.dry_run:
        for r in results:
            print(f"  [DRY] {r.product_key}")
    else:
        total_b = sum(r.blocket_count for r in results)
        total_t = sum(r.tradera_count for r in results)
        total_n = sum(1 for r in results if r.new_price_fetched)
        errors = sum(1 for r in results if r.error)
        print(f"  Blocket listings: {total_b}")
        print(f"  Tradera listings: {total_t}")
        print(f"  New prices fetched: {total_n}")
        print(f"  Errors: {errors}")
        if errors:
            for r in results:
                if r.error:
                    print(f"    ERROR {r.product_key}: {r.error}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
