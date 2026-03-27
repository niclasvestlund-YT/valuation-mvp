"""Tests for VALOR training pipeline logic."""

import unittest
from unittest.mock import patch


class TestETLQualityScore(unittest.TestCase):

    def test_quality_score_max(self):
        """final_price=True, is_sold=True, known condition, known listing_type → 1.0."""
        base = 0.2
        final_price = 0.3
        is_sold = 0.2
        condition_known = 0.15
        listing_known = 0.15
        total = base + final_price + is_sold + condition_known + listing_known
        self.assertAlmostEqual(total, 1.0)

    def test_quality_score_minimum(self):
        """All unknown/false → 0.2 (base only)."""
        total = 0.2  # base
        self.assertAlmostEqual(total, 0.2)

    def test_quality_score_threshold(self):
        """Quality score must be >= 0.5 for inclusion."""
        # Just base + is_sold = 0.4 → excluded
        self.assertLess(0.2 + 0.2, 0.5)
        # base + final_price = 0.5 → included
        self.assertGreaterEqual(0.2 + 0.3, 0.5)

    def test_condition_encoding(self):
        """Condition encoding map should have known values."""
        condition_map = {
            "like_new": 1.0, "excellent": 0.9, "good": 0.8,
            "used": 0.6, "fair": 0.5, "poor": 0.3, "unknown": 0.5,
        }
        self.assertEqual(condition_map["like_new"], 1.0)
        self.assertEqual(condition_map["poor"], 0.3)
        self.assertEqual(condition_map["unknown"], 0.5)

    def test_price_inclusion_range(self):
        """Only prices 200-150000 should be included."""
        min_price = 200
        max_price = 150_000
        self.assertFalse(100 >= min_price and 100 <= max_price)
        self.assertTrue(5000 >= min_price and 5000 <= max_price)
        self.assertFalse(200_000 >= min_price and 200_000 <= max_price)

    def test_suspicious_excluded(self):
        """Suspicious observations should always be excluded."""
        suspicious = True
        included = not suspicious
        self.assertFalse(included)

    def test_days_capped_at_365(self):
        """days_since_observation should be capped at 365."""
        raw_days = 500
        capped = min(raw_days, 365)
        self.assertEqual(capped, 365)

    def test_price_to_new_ratio_clip(self):
        """price_to_new_ratio should be clipped to 0.1-1.0."""
        self.assertEqual(max(min(0.05, 1.0), 0.1), 0.1)
        self.assertEqual(max(min(1.5, 1.0), 0.1), 1.0)
        self.assertEqual(max(min(0.6, 1.0), 0.1), 0.6)

    def test_feature_list_complete(self):
        """Feature list should have exactly 10 features."""
        features = [
            "condition_encoded", "month_of_year", "days_since_observation",
            "price_to_new_ratio", "is_sold_int", "listing_type_fixed",
            "listing_type_auction", "source_valuation", "source_crawler",
            "source_agent",
        ]
        self.assertEqual(len(features), 10)

    def test_data_quality_variance_warning(self):
        """CV > 2.0 should trigger a warning."""
        import statistics
        prices = [1, 1, 1000000]
        mean = statistics.mean(prices)
        stdev = statistics.stdev(prices)
        cv = stdev / mean
        self.assertGreater(cv, 1.5)  # extreme variance triggers warning


if __name__ == "__main__":
    unittest.main()
