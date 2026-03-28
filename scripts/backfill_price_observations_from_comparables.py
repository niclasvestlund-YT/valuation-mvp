#!/usr/bin/env python3
"""Backfill conservative price_observation rows from cached market_comparable data.

Default behavior is a dry-run audit. Use `--apply` to insert observations through
the same ingest path the API uses, while preserving the historical disappeared_at
timestamp on each backfilled row.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

from backend.app.db.database import async_session  # noqa: E402
from backend.app.db.models import MarketComparable, NewPriceSnapshot, PriceObservation  # noqa: E402
from backend.app.routers.ingest import _persist_observations  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

MIN_TRAINING_PRICE_SEK = 200
MAX_TRAINING_PRICE_SEK = 150_000
DEFAULT_ALLOWED_SOURCES = frozenset({"tradera"})
DEFAULT_AGENT_RUN_ID = "valor_lab_comparable_backfill"


@dataclass(slots=True)
class BackfillObservation:
    product_key: str
    price_sek: int
    condition: str = "unknown"
    source: str = ""
    source_url: str | None = None
    title: str | None = None
    raw_text: str | None = None
    agent_run_id: str | None = None
    is_sold: bool = False
    listing_type: str = "unknown"
    final_price: bool = False
    new_price_at_observation: int | None = None
    currency: str = "SEK"
    observed_at: datetime | None = None


def parse_sources(raw_value: str | None) -> set[str]:
    if not raw_value:
        return set(DEFAULT_ALLOWED_SOURCES)
    return {
        part.strip().lower()
        for part in raw_value.split(",")
        if part.strip()
    }


def row_to_snapshot(row) -> dict:
    return {
        "id": row.id,
        "product_key": row.product_key,
        "source": (row.source or "").lower(),
        "listing_url": row.listing_url,
        "title": row.title,
        "price_sek": int(row.price_sek),
        "condition": row.condition or "unknown",
        "flagged": bool(row.flagged),
        "is_active": bool(row.is_active),
        "first_seen": row.first_seen,
        "last_seen": row.last_seen,
        "disappeared_at": row.disappeared_at,
    }


def select_backfill_candidates(
    rows: list[dict],
    *,
    allowed_sources: set[str],
    now: datetime,
    min_disappeared_age_hours: int,
) -> tuple[list[dict], dict]:
    selected: list[dict] = []
    skipped = Counter()
    selected_per_source = Counter()

    for row in rows:
        source = str(row.get("source") or "").lower()
        price = int(row.get("price_sek") or 0)
        disappeared_at = row.get("disappeared_at")

        if source not in allowed_sources:
            skipped["source_not_allowed"] += 1
            continue

        if row.get("flagged"):
            skipped["flagged"] += 1
            continue

        if row.get("is_active"):
            skipped["still_active"] += 1
            continue

        if not disappeared_at:
            skipped["missing_disappeared_at"] += 1
            continue

        if price < MIN_TRAINING_PRICE_SEK or price > MAX_TRAINING_PRICE_SEK:
            skipped["price_out_of_range"] += 1
            continue

        if row.get("already_backfilled"):
            skipped["already_backfilled"] += 1
            continue

        disappeared_age = now - disappeared_at
        if disappeared_age < timedelta(hours=min_disappeared_age_hours):
            skipped["disappeared_too_recently"] += 1
            continue

        selected.append(row)
        selected_per_source[source] += 1

    summary = {
        "selected": len(selected),
        "selected_per_source": dict(selected_per_source),
        "skipped_by_reason": dict(skipped),
    }
    return selected, summary


def build_backfill_observation(row: dict) -> BackfillObservation:
    source = str(row["source"]).lower()
    observed_at = row.get("disappeared_at") or row.get("last_seen") or row.get("first_seen")
    raw_text = json.dumps(
        {
            "backfill_from": "market_comparable",
            "comparable_id": row.get("id"),
            "source": source,
            "first_seen": row.get("first_seen").isoformat() if row.get("first_seen") else None,
            "last_seen": row.get("last_seen").isoformat() if row.get("last_seen") else None,
            "disappeared_at": row.get("disappeared_at").isoformat() if row.get("disappeared_at") else None,
        },
        ensure_ascii=True,
    )

    return BackfillObservation(
        product_key=row["product_key"],
        price_sek=int(row["price_sek"]),
        condition=row.get("condition") or "unknown",
        source=f"{source}_backfill",
        source_url=row.get("listing_url"),
        title=row.get("title"),
        raw_text=raw_text,
        agent_run_id=DEFAULT_AGENT_RUN_ID,
        is_sold=True,
        listing_type="unknown",
        final_price=False,
        new_price_at_observation=row.get("latest_new_price_sek"),
        currency="SEK",
        observed_at=observed_at,
    )


async def fetch_candidate_rows(
    *,
    product_key: str | None,
    limit: int | None,
) -> list[dict]:
    async with async_session() as session:
        latest_new_price = (
            select(NewPriceSnapshot.price_sek)
            .where(NewPriceSnapshot.product_key == MarketComparable.product_key)
            .order_by(NewPriceSnapshot.fetched_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        already_backfilled = (
            select(PriceObservation.id)
            .where(PriceObservation.source_url == MarketComparable.listing_url)
            .limit(1)
            .scalar_subquery()
        )

        query = (
            select(
                MarketComparable.id,
                MarketComparable.product_key,
                MarketComparable.source,
                MarketComparable.listing_url,
                MarketComparable.title,
                MarketComparable.price_sek,
                MarketComparable.condition,
                MarketComparable.flagged,
                MarketComparable.is_active,
                MarketComparable.first_seen,
                MarketComparable.last_seen,
                MarketComparable.disappeared_at,
                latest_new_price.label("latest_new_price_sek"),
                already_backfilled.label("already_backfilled"),
            )
            .order_by(MarketComparable.disappeared_at.desc().nullslast(), MarketComparable.last_seen.desc())
        )

        if product_key:
            query = query.where(MarketComparable.product_key == product_key)
        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        return [
            {
                **row_to_snapshot(row),
                "latest_new_price_sek": row.latest_new_price_sek,
                "already_backfilled": bool(row.already_backfilled),
            }
            for row in result
        ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply a conservative price_observation backfill from market_comparable."
    )
    parser.add_argument(
        "--product",
        type=str,
        default=None,
        help="Only inspect one product_key.",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="tradera",
        help="Comma-separated comparable sources to allow. Default: tradera",
    )
    parser.add_argument(
        "--min-disappeared-age-hours",
        type=int,
        default=24,
        help="Require a listing to have been inactive for at least this long before backfill.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum comparable rows to inspect. Default: 500",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=10,
        help="How many selected candidates to preview in dry-run output.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write observations to price_observation via shared ingest logic.",
    )
    return parser


async def main_async(args) -> int:
    allowed_sources = parse_sources(args.sources)
    now = datetime.now(timezone.utc)
    rows = await fetch_candidate_rows(product_key=args.product, limit=args.limit)
    selected_rows, summary = select_backfill_candidates(
        rows,
        allowed_sources=allowed_sources,
        now=now,
        min_disappeared_age_hours=args.min_disappeared_age_hours,
    )
    observations = [build_backfill_observation(row) for row in selected_rows]

    print("\n=== Comparable Backfill Audit ===")
    print(f"Rows inspected: {len(rows)}")
    print(f"Allowed sources: {', '.join(sorted(allowed_sources))}")
    print(f"Selected candidates: {summary['selected']}")
    print(f"Skipped by reason: {json.dumps(summary['skipped_by_reason'], ensure_ascii=True, sort_keys=True)}")
    print(f"Selected per source: {json.dumps(summary['selected_per_source'], ensure_ascii=True, sort_keys=True)}")

    if observations:
        print("\nSample candidates:")
        for obs in observations[: max(args.sample, 0)]:
            print(
                f"  - {obs.product_key} | {obs.price_sek} kr | {obs.source} | "
                f"{obs.source_url or 'no-url'} | observed_at={obs.observed_at.isoformat() if obs.observed_at else 'n/a'}"
            )
    else:
        print("\nNo safe backfill candidates matched the current filters.")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to ingest selected candidates.")
        return 0

    if not observations:
        print("\nNothing to apply.")
        return 0

    response = await _persist_observations(
        observations,
        search_terms=[
            "backfill:market_comparable",
            f"sources:{','.join(sorted(allowed_sources))}",
        ],
    )
    print("\nApplied backfill via shared ingest path:")
    print(
        json.dumps(
            {
                "accepted": response.accepted,
                "rejected": response.rejected,
                "suspicious": response.suspicious,
                "agent_job_id": response.agent_job_id,
                "rejection_reasons": response.rejection_reasons,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
