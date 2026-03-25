import unittest

from backend.app.services.depreciation_rules import get_depreciation_range


class DepreciationRulesTests(unittest.TestCase):
    def test_known_category_returns_plausible_range(self) -> None:
        low, high = get_depreciation_range("smartphone")
        self.assertGreater(high, low)
        self.assertGreaterEqual(low, 0.1)
        self.assertLessEqual(high, 0.98)

    def test_unknown_category_falls_back_to_default(self) -> None:
        low, high = get_depreciation_range("toaster")
        low_default, high_default = get_depreciation_range("unknown")
        self.assertEqual(low, low_default)
        self.assertEqual(high, high_default)

    def test_none_category_falls_back_to_default(self) -> None:
        low, high = get_depreciation_range(None)
        low_default, high_default = get_depreciation_range("unknown")
        self.assertEqual(low, low_default)
        self.assertEqual(high, high_default)

    def test_excellent_condition_shifts_range_up(self) -> None:
        low_good, high_good = get_depreciation_range("smartphone", condition="good")
        low_exc, high_exc = get_depreciation_range("smartphone", condition="excellent")
        self.assertGreater(low_exc, low_good)
        self.assertGreater(high_exc, high_good)

    def test_poor_condition_shifts_range_down(self) -> None:
        low_good, high_good = get_depreciation_range("smartphone", condition="good")
        low_poor, high_poor = get_depreciation_range("smartphone", condition="poor")
        self.assertLess(low_poor, low_good)
        self.assertLess(high_poor, high_good)

    def test_fair_condition_sits_between_good_and_poor(self) -> None:
        low_good, _ = get_depreciation_range("smartphone", condition="good")
        low_fair, _ = get_depreciation_range("smartphone", condition="fair")
        low_poor, _ = get_depreciation_range("smartphone", condition="poor")
        self.assertLess(low_poor, low_fair)
        self.assertLess(low_fair, low_good)

    def test_range_is_always_valid(self) -> None:
        for condition in ("excellent", "good", "fair", "poor", None, "unknown"):
            low, high = get_depreciation_range("smartphone", condition=condition)
            self.assertGreater(high, low, f"high must exceed low for condition={condition!r}")
            self.assertGreaterEqual(low, 0.1)
            self.assertLessEqual(high, 0.98)

    def test_all_categories_return_valid_ranges(self) -> None:
        categories = ["smartphone", "tablet", "laptop", "headphones", "camera", "smartwatch", "console", "router", "accessory"]
        for cat in categories:
            low, high = get_depreciation_range(cat)
            self.assertGreater(high, low, f"invalid range for category={cat}")


if __name__ == "__main__":
    unittest.main()
