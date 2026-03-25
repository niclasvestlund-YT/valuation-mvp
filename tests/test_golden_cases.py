"""
Golden test cases — canonical products that must always be handled correctly.

These tests use mock vision responses to verify the full pipeline produces
expected outcomes for known product types. Add new cases here as regressions
are discovered.
"""

import unittest
from unittest.mock import patch

from backend.app.core.value_engine import ValueEngine
from backend.app.schemas.product_identification import ProductIdentificationResult


def _mock_vision(brand, model, category, confidence=0.92, candidate_models=None):
    """Create a mock ProductIdentificationResult."""
    return ProductIdentificationResult(
        brand=brand,
        line=None,
        model=model,
        category=category,
        variant=None,
        candidate_models=candidate_models or [],
        confidence=confidence,
        reasoning_summary="Golden test mock — visible model text on product body.",
        needs_more_images=False,
        requested_additional_angles=[],
        source="Mock golden test",
        request_id="golden_test",
    )


def _mock_comparables(brand, model, prices, source="Tradera"):
    """Create mock market comparables."""
    return [
        {
            "source": source,
            "listing_id": f"golden_{i}",
            "title": f"{brand} {model}",
            "price": price,
            "currency": "SEK",
            "status": "completed",
            "listing_type": "sold",
            "url": None,
            "ended_at": None,
            "shipping_cost": None,
            "condition_hint": None,
            "raw": {},
        }
        for i, price in enumerate(prices)
    ]


def _mock_new_price(price, currency="SEK"):
    """Create mock new price data."""
    return {
        "estimated_new_price": price,
        "currency": currency,
        "confidence": 0.75,
        "source_count": 3,
        "sources": [{"source": "test", "title": "test", "price": price, "currency": currency, "url": None}],
        "method": "golden_test",
        "price": price,
        "source": "golden_test",
    }


class GoldenTestCases(unittest.TestCase):
    """Each test verifies a specific product through the full valuation pipeline."""

    def _run_pipeline(self, vision_result, comparables, new_price):
        engine = ValueEngine()
        with (
            patch.object(engine.vision_service, "detect_product", return_value=vision_result),
            patch.object(engine.market_service, "get_comparables", return_value=comparables),
            patch.object(engine.new_price_service, "get_new_price", return_value=new_price),
        ):
            return engine.value_item(images=["data:image/jpeg;base64,/9j/"])

    def test_sony_wh1000xm4_with_strong_evidence_returns_ok(self):
        """Sony WH-1000XM4 with 5 sold comparables should return ok."""
        result = self._run_pipeline(
            vision_result=_mock_vision("Sony", "WH-1000XM4", "headphones"),
            comparables=_mock_comparables("Sony", "WH-1000XM4", [1800, 1900, 2000, 2100, 1950]),
            new_price=_mock_new_price(3490),
        )
        self.assertEqual(result["status"], "ok")
        self.assertIsNotNone(result["data"]["valuation"])
        fair = result["data"]["valuation"]["fair_estimate"]
        self.assertGreater(fair, 1000)
        self.assertLess(fair, 3000)

    def test_sony_wh1000xm5_distinguished_from_xm4(self):
        """WH-1000XM5 comparables should not be contaminated by XM4 prices."""
        result = self._run_pipeline(
            vision_result=_mock_vision("Sony", "WH-1000XM5", "headphones"),
            comparables=_mock_comparables("Sony", "WH-1000XM5", [2500, 2600, 2700, 2800, 2650]),
            new_price=_mock_new_price(3990),
        )
        self.assertEqual(result["status"], "ok")
        fair = result["data"]["valuation"]["fair_estimate"]
        self.assertGreater(fair, 2000)

    def test_iphone_13_common_product_reaches_ok(self):
        """iPhone 13 with clear market data should reach ok status."""
        result = self._run_pipeline(
            vision_result=_mock_vision("Apple", "iPhone 13", "smartphone"),
            comparables=_mock_comparables("Apple", "iPhone 13", [4500, 4800, 5000, 4700, 4600]),
            new_price=_mock_new_price(8990),
        )
        self.assertEqual(result["status"], "ok")

    def test_dji_osmo_pocket_3_not_confused_with_generic_osmo(self):
        """DJI Osmo Pocket 3 should not be confused with Osmo Action or generic Osmo."""
        result = self._run_pipeline(
            vision_result=_mock_vision("DJI", "Osmo Pocket 3", "camera"),
            comparables=_mock_comparables("DJI", "Osmo Pocket 3", [3500, 3600, 3700, 3800]),
            new_price=_mock_new_price(5490),
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["model"], "Osmo Pocket 3")

    def test_macbook_air_m2_with_strong_evidence(self):
        """MacBook Air M2 with sold listings should return ok."""
        result = self._run_pipeline(
            vision_result=_mock_vision("Apple", "MacBook Air M2", "laptop"),
            comparables=_mock_comparables("Apple", "MacBook Air M2", [9000, 9500, 10000, 9200, 9800]),
            new_price=_mock_new_price(13990),
        )
        self.assertEqual(result["status"], "ok")
        fair = result["data"]["valuation"]["fair_estimate"]
        self.assertGreater(fair, 7000)
        self.assertLess(fair, 12000)

    def test_unknown_product_with_no_comparables_returns_insufficient(self):
        """Rare product with no market data should not fabricate a value."""
        result = self._run_pipeline(
            vision_result=_mock_vision("Obscure", "Widget Pro X", "unknown", confidence=0.88),
            comparables=[],
            new_price={"estimated_new_price": None, "currency": None, "confidence": 0.0,
                       "source_count": 0, "sources": [], "method": "unavailable", "price": 0.0, "source": "unavailable"},
        )
        self.assertIn(result["status"], {"insufficient_evidence"})

    def test_low_confidence_identification_returns_ambiguous(self):
        """Product with very low confidence should return ambiguous_model."""
        result = self._run_pipeline(
            vision_result=_mock_vision("Unknown", None, "smartphone", confidence=0.30),
            comparables=[],
            new_price={"estimated_new_price": None, "currency": None, "confidence": 0.0,
                       "source_count": 0, "sources": [], "method": "unavailable", "price": 0.0, "source": "unavailable"},
        )
        self.assertEqual(result["status"], "ambiguous_model")


if __name__ == "__main__":
    unittest.main()
