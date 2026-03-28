"""Tests for conservative market_comparable -> price_observation backfill helpers."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from scripts.backfill_price_observations_from_comparables import (
    build_backfill_observation,
    parse_sources,
    select_backfill_candidates,
)


class TestBackfillSourceParsing(unittest.TestCase):

    def test_parse_sources_defaults_to_tradera(self):
        self.assertEqual(parse_sources(None), {"tradera"})
        self.assertEqual(parse_sources(""), {"tradera"})

    def test_parse_sources_normalizes_and_deduplicates(self):
        self.assertEqual(parse_sources(" Tradera, pipeline,TRADERA "), {"tradera", "pipeline"})


class TestBackfillCandidateSelection(unittest.TestCase):

    def test_select_backfill_candidates_keeps_only_safe_rows(self):
        now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
        old = now - timedelta(days=3)
        recent = now - timedelta(hours=2)
        rows = [
            {
                "id": 1,
                "product_key": "sony_wh-1000xm4",
                "source": "tradera",
                "listing_url": "https://example.com/1",
                "title": "Sony WH-1000XM4",
                "price_sek": 2200,
                "condition": "good",
                "flagged": False,
                "is_active": False,
                "first_seen": old - timedelta(days=2),
                "last_seen": old - timedelta(hours=1),
                "disappeared_at": old,
                "already_backfilled": False,
            },
            {
                "id": 2,
                "product_key": "sony_wh-1000xm4",
                "source": "tradera",
                "listing_url": "https://example.com/2",
                "title": "Sony WH-1000XM4 kabel",
                "price_sek": 500,
                "condition": "good",
                "flagged": True,
                "is_active": False,
                "first_seen": old,
                "last_seen": old,
                "disappeared_at": old,
                "already_backfilled": False,
            },
            {
                "id": 3,
                "product_key": "sony_wh-1000xm4",
                "source": "tradera",
                "listing_url": "https://example.com/3",
                "title": "Sony WH-1000XM4",
                "price_sek": 2500,
                "condition": "good",
                "flagged": False,
                "is_active": True,
                "first_seen": old,
                "last_seen": old,
                "disappeared_at": old,
                "already_backfilled": False,
            },
            {
                "id": 4,
                "product_key": "sony_wh-1000xm4",
                "source": "pipeline",
                "listing_url": "https://example.com/4",
                "title": "Sony WH-1000XM4",
                "price_sek": 2500,
                "condition": "good",
                "flagged": False,
                "is_active": False,
                "first_seen": old,
                "last_seen": old,
                "disappeared_at": old,
                "already_backfilled": False,
            },
            {
                "id": 5,
                "product_key": "sony_wh-1000xm4",
                "source": "tradera",
                "listing_url": "https://example.com/5",
                "title": "Sony WH-1000XM4",
                "price_sek": 150,
                "condition": "good",
                "flagged": False,
                "is_active": False,
                "first_seen": old,
                "last_seen": old,
                "disappeared_at": old,
                "already_backfilled": False,
            },
            {
                "id": 6,
                "product_key": "sony_wh-1000xm4",
                "source": "tradera",
                "listing_url": "https://example.com/6",
                "title": "Sony WH-1000XM4",
                "price_sek": 2500,
                "condition": "good",
                "flagged": False,
                "is_active": False,
                "first_seen": old,
                "last_seen": old,
                "disappeared_at": recent,
                "already_backfilled": False,
            },
            {
                "id": 7,
                "product_key": "sony_wh-1000xm4",
                "source": "tradera",
                "listing_url": "https://example.com/7",
                "title": "Sony WH-1000XM4",
                "price_sek": 2500,
                "condition": "good",
                "flagged": False,
                "is_active": False,
                "first_seen": old,
                "last_seen": old,
                "disappeared_at": old,
                "already_backfilled": True,
            },
            {
                "id": 8,
                "product_key": "sony_wh-1000xm4",
                "source": "tradera",
                "listing_url": "https://example.com/8",
                "title": "Sony WH-1000XM4",
                "price_sek": 2500,
                "condition": "good",
                "flagged": False,
                "is_active": False,
                "first_seen": old,
                "last_seen": old,
                "disappeared_at": None,
                "already_backfilled": False,
            },
        ]

        selected, summary = select_backfill_candidates(
            rows,
            allowed_sources={"tradera"},
            now=now,
            min_disappeared_age_hours=24,
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["id"], 1)
        self.assertEqual(summary["selected_per_source"], {"tradera": 1})
        self.assertEqual(summary["skipped_by_reason"]["flagged"], 1)
        self.assertEqual(summary["skipped_by_reason"]["still_active"], 1)
        self.assertEqual(summary["skipped_by_reason"]["source_not_allowed"], 1)
        self.assertEqual(summary["skipped_by_reason"]["price_out_of_range"], 1)
        self.assertEqual(summary["skipped_by_reason"]["disappeared_too_recently"], 1)
        self.assertEqual(summary["skipped_by_reason"]["already_backfilled"], 1)
        self.assertEqual(summary["skipped_by_reason"]["missing_disappeared_at"], 1)


class TestBackfillObservationBuilding(unittest.TestCase):

    def test_build_backfill_observation_preserves_traceability(self):
        disappeared_at = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        row = {
            "id": 42,
            "product_key": "apple_iphone-13",
            "source": "tradera",
            "listing_url": "https://example.com/listing/42",
            "title": "Apple iPhone 13 128GB",
            "price_sek": 4200,
            "condition": "good",
            "first_seen": disappeared_at - timedelta(days=2),
            "last_seen": disappeared_at - timedelta(hours=1),
            "disappeared_at": disappeared_at,
            "latest_new_price_sek": 7990,
        }

        obs = build_backfill_observation(row)

        self.assertEqual(obs.source, "tradera_backfill")
        self.assertEqual(obs.product_key, "apple_iphone-13")
        self.assertTrue(obs.is_sold)
        self.assertFalse(obs.final_price)
        self.assertEqual(obs.observed_at, disappeared_at)
        self.assertEqual(obs.new_price_at_observation, 7990)
        self.assertIn("market_comparable", obs.raw_text or "")
        self.assertIn("\"comparable_id\": 42", obs.raw_text or "")


class TestObservedAtHelper(unittest.TestCase):

    def test_observed_at_helper_keeps_timezone_and_normalizes_naive(self):
        from backend.app.routers.ingest import _observed_at_for

        aware = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
        naive = datetime(2026, 3, 1, 8, 0)

        self.assertEqual(_observed_at_for(SimpleNamespace(observed_at=aware)), aware)
        self.assertEqual(
            _observed_at_for(SimpleNamespace(observed_at=naive)),
            aware,
        )


if __name__ == "__main__":
    unittest.main()
