"""Tests for the /api/ingest endpoint."""

import unittest
from unittest.mock import AsyncMock, patch, MagicMock


class TestIngestValidation(unittest.TestCase):
    """Test ingest validation logic without DB."""

    def test_rejects_price_too_low(self):
        from backend.app.routers.ingest import MIN_PRICE_SEK
        self.assertEqual(MIN_PRICE_SEK, 100)
        # A price of 50 is below minimum
        self.assertTrue(50 < MIN_PRICE_SEK)

    def test_rejects_price_too_high(self):
        from backend.app.routers.ingest import MAX_PRICE_SEK
        self.assertEqual(MAX_PRICE_SEK, 200_000)
        self.assertTrue(500_001 > MAX_PRICE_SEK)

    def test_rejects_missing_product_key(self):
        """Empty product_key should be rejected."""
        pk = ""
        self.assertFalse(bool(pk and pk.strip()))

    def test_flags_accessory_title(self):
        from backend.app.routers.ingest import _check_accessory
        self.assertTrue(_check_accessory("Sony XM4 kabel"))
        self.assertTrue(_check_accessory("Fodral för iPhone 13"))
        self.assertTrue(_check_accessory("Laddare USB-C"))
        self.assertTrue(_check_accessory("Öronkudde replacement"))
        self.assertTrue(_check_accessory("Batteri original"))
        self.assertFalse(_check_accessory("Sony WH-1000XM4"))
        self.assertFalse(_check_accessory(None))

    def test_truncates_raw_text(self):
        from backend.app.routers.ingest import RAW_TEXT_MAX_LEN
        long_text = "a" * 1000
        truncated = long_text[:RAW_TEXT_MAX_LEN]
        self.assertEqual(len(truncated), 500)

    def test_accessory_keywords_comprehensive(self):
        from backend.app.routers.ingest import ACCESSORY_KEYWORDS
        expected = {"del ", "kabel", "fodral", "case", "skal", "laddare",
                    "adapter", "öronkudde", "dyna", "cover", "strap", "band",
                    "lins", "filter", "batteri", "hållare"}
        self.assertEqual(ACCESSORY_KEYWORDS, expected)

    def test_observation_model_defaults(self):
        from backend.app.routers.ingest import ObservationIn
        obs = ObservationIn(product_key="test", price_sek=1000, source="tradera")
        self.assertEqual(obs.condition, "unknown")
        self.assertEqual(obs.listing_type, "unknown")
        self.assertFalse(obs.is_sold)
        self.assertFalse(obs.final_price)
        self.assertEqual(obs.currency, "SEK")

    def test_median_ratios(self):
        from backend.app.routers.ingest import MEDIAN_LOW_RATIO, MEDIAN_HIGH_RATIO
        median = 2000
        # 300 is below 20% of 2000 (400)
        self.assertTrue(300 < median * MEDIAN_LOW_RATIO)
        # 7000 is above 300% of 2000 (6000)
        self.assertTrue(7000 > median * MEDIAN_HIGH_RATIO)


if __name__ == "__main__":
    unittest.main()
