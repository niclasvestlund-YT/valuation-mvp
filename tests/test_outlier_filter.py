"""Unit tests for outlier_filter.py — trust-critical statistical filtering.

These tests verify the IQR and MAD outlier removal that directly affects
which comparable prices are included in valuations.
"""

import unittest

from backend.app.services.outlier_filter import (
    filter_comparable_outliers,
    filter_iqr_outliers,
    filter_mad_outliers,
    filter_price_outliers,
    median_absolute_deviation,
    median_value,
)


class TestMedianValue(unittest.TestCase):
    def test_empty_list_returns_zero(self):
        self.assertEqual(median_value([]), 0.0)

    def test_single_value(self):
        self.assertEqual(median_value([42.0]), 42.0)

    def test_odd_count(self):
        self.assertEqual(median_value([1.0, 2.0, 3.0]), 2.0)

    def test_even_count(self):
        self.assertEqual(median_value([1.0, 2.0, 3.0, 4.0]), 2.5)


class TestMedianAbsoluteDeviation(unittest.TestCase):
    def test_empty_list_returns_zero(self):
        self.assertEqual(median_absolute_deviation([]), 0.0)

    def test_identical_values_returns_zero(self):
        self.assertEqual(median_absolute_deviation([5.0, 5.0, 5.0]), 0.0)

    def test_known_values(self):
        # median=3, deviations=[2,1,0,1,2], MAD=1
        self.assertEqual(median_absolute_deviation([1.0, 2.0, 3.0, 4.0, 5.0]), 1.0)


class TestFilterIqrOutliers(unittest.TestCase):
    def test_fewer_than_4_values_returns_all(self):
        kept, removed = filter_iqr_outliers([1.0, 2.0, 3.0])
        self.assertEqual(kept, [1.0, 2.0, 3.0])
        self.assertEqual(removed, [])

    def test_no_outliers_in_tight_cluster(self):
        values = [100.0, 101.0, 102.0, 103.0, 104.0]
        kept, removed = filter_iqr_outliers(values)
        self.assertEqual(len(kept), 5)
        self.assertEqual(len(removed), 0)

    def test_extreme_value_removed(self):
        values = [100.0, 101.0, 102.0, 103.0, 500.0]
        kept, removed = filter_iqr_outliers(values)
        self.assertIn(500.0, removed)
        self.assertNotIn(500.0, kept)

    def test_empty_list(self):
        kept, removed = filter_iqr_outliers([])
        self.assertEqual(kept, [])
        self.assertEqual(removed, [])


class TestFilterMadOutliers(unittest.TestCase):
    def test_fewer_than_5_values_returns_all(self):
        kept, removed = filter_mad_outliers([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(kept, [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(removed, [])

    def test_identical_values_returns_all(self):
        """MAD=0 means no outlier filtering possible."""
        kept, removed = filter_mad_outliers([5.0, 5.0, 5.0, 5.0, 5.0])
        self.assertEqual(kept, [5.0, 5.0, 5.0, 5.0, 5.0])
        self.assertEqual(removed, [])

    def test_extreme_outlier_removed(self):
        values = [100.0, 101.0, 102.0, 103.0, 104.0, 1000.0]
        kept, removed = filter_mad_outliers(values)
        self.assertIn(1000.0, removed)
        self.assertNotIn(1000.0, kept)


class TestFilterPriceOutliers(unittest.TestCase):
    def test_prefers_mad_when_it_removes_outliers(self):
        """MAD is tried first; if it removes something, IQR is skipped."""
        values = [100.0, 101.0, 102.0, 103.0, 104.0, 1000.0]
        kept, removed = filter_price_outliers(values)
        self.assertIn(1000.0, removed)
        # All non-outlier values kept
        for v in [100.0, 101.0, 102.0, 103.0, 104.0]:
            self.assertIn(v, kept)

    def test_falls_back_to_iqr_when_mad_removes_nothing(self):
        # With 4 values MAD does nothing (< 5 threshold), IQR kicks in
        values = [100.0, 101.0, 102.0, 103.0, 500.0]
        kept, removed = filter_price_outliers(values)
        # IQR should remove the extreme value
        self.assertIn(500.0, removed)


class TestFilterComparableOutliers(unittest.TestCase):
    def _comparable(self, price: float, title: str = "Test Item") -> dict:
        return {"price": price, "title": title, "source": "test"}

    def test_empty_list(self):
        kept, removed = filter_comparable_outliers([])
        self.assertEqual(kept, [])
        self.assertEqual(removed, [])

    def test_no_outliers_preserves_all(self):
        comparables = [self._comparable(p) for p in [100, 105, 110, 115, 120]]
        kept, removed = filter_comparable_outliers(comparables)
        self.assertEqual(len(kept), 5)
        self.assertEqual(len(removed), 0)

    def test_extreme_comparable_removed(self):
        comparables = [
            self._comparable(100),
            self._comparable(105),
            self._comparable(110),
            self._comparable(115),
            self._comparable(120),
            self._comparable(1000),
        ]
        kept, removed = filter_comparable_outliers(comparables)
        removed_prices = [c["price"] for c in removed]
        self.assertIn(1000, removed_prices)
        self.assertEqual(len(kept), 5)

    def test_preserves_dict_identity(self):
        """Ensure the returned dicts are the same objects, not copies."""
        c1 = self._comparable(100)
        c2 = self._comparable(105)
        c3 = self._comparable(110)
        c4 = self._comparable(115)
        c5 = self._comparable(120)
        kept, _ = filter_comparable_outliers([c1, c2, c3, c4, c5])
        self.assertIs(kept[0], c1)

    def test_duplicate_prices_handled_correctly(self):
        """When multiple comparables share a price, outlier removal should
        correctly assign each to kept or removed."""
        comparables = [
            self._comparable(100),
            self._comparable(100),
            self._comparable(100),
            self._comparable(100),
            self._comparable(100),
            self._comparable(1000),
        ]
        kept, removed = filter_comparable_outliers(comparables)
        kept_prices = [c["price"] for c in kept]
        removed_prices = [c["price"] for c in removed]
        self.assertEqual(kept_prices.count(100), 5)
        self.assertIn(1000, removed_prices)


if __name__ == "__main__":
    unittest.main()
