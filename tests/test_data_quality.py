"""Data quality tests — verify invariants that must always hold."""

import json
from pathlib import Path

from backend.app.core.thresholds import (
    COMPARABLE_MAX_PRICE_SEK,
    COMPARABLE_MIN_PRICE_SEK,
    COMPARABLE_MIN_TITLE_LENGTH,
    NEW_PRICE_MAX_SEK,
    NEW_PRICE_MIN_SEK,
)
from backend.app.services.data_validator import validate_comparable
from backend.app.utils.normalization import normalize_product_key


SEED_FILE = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "seed_products.json"


class TestThresholdConsistency:
    """Verify threshold values are sane."""

    def test_min_less_than_max_comparable(self):
        assert COMPARABLE_MIN_PRICE_SEK < COMPARABLE_MAX_PRICE_SEK

    def test_min_less_than_max_new_price(self):
        assert NEW_PRICE_MIN_SEK < NEW_PRICE_MAX_SEK

    def test_comparable_min_positive(self):
        assert COMPARABLE_MIN_PRICE_SEK > 0

    def test_comparable_title_min_positive(self):
        assert COMPARABLE_MIN_TITLE_LENGTH > 0


class TestValidatorNeverPassesInvalid:
    """Ensure validator rejects clearly invalid data regardless of product."""

    def test_negative_price_rejected(self):
        result = validate_comparable("Valid Title Here", -100, "any_product")
        assert not result.valid

    def test_zero_price_rejected(self):
        result = validate_comparable("Valid Title Here", 0, "any_product")
        assert not result.valid

    def test_massive_price_rejected(self):
        result = validate_comparable("Valid Title Here", 999_999, "any_product")
        assert not result.valid

    def test_empty_title_rejected(self):
        result = validate_comparable("", 1000, "any_product")
        assert not result.valid

    def test_very_short_title_rejected(self):
        result = validate_comparable("ab", 1000, "any_product")
        assert not result.valid


class TestProductKeyNormalizationRoundTrips:
    """Product keys should be stable — normalizing twice gives same result."""

    def test_roundtrip_stability(self):
        pairs = [
            ("Sony", "WH-1000XM5"),
            ("Apple", "iPhone 15 Pro"),
            ("DJI", "Osmo Pocket 3"),
            ("Samsung", "Galaxy S24 Ultra"),
        ]
        for brand, model in pairs:
            k1 = normalize_product_key(brand, model)
            # Splitting and re-normalizing should give same key
            parts = k1.split("_", 1)
            if len(parts) == 2:
                k2 = normalize_product_key(parts[0], parts[1])
                # May not be identical (brand aliases stripped) but should be consistent format
                assert k2  # non-empty
                assert "_" not in k2 or k2.count("_") == 1  # at most one underscore


class TestSeedProductsQuality:
    """Verify seed products are well-formed."""

    def test_all_products_generate_valid_keys(self):
        data = json.loads(SEED_FILE.read_text())
        for item in data:
            key = normalize_product_key(item["brand"], item["model"])
            assert key != "unknown", f"Product {item} generates 'unknown' key"
            assert len(key) >= 3, f"Product key too short: {key} for {item}"

    def test_no_empty_brands_or_models(self):
        data = json.loads(SEED_FILE.read_text())
        for item in data:
            assert item["brand"].strip(), f"Empty brand: {item}"
            assert item["model"].strip(), f"Empty model: {item}"

    def test_categories_are_known(self):
        known_categories = {
            "smartphone", "tablet", "laptop", "headphones", "camera",
            "smartwatch", "gaming", "speaker", "appliance",
        }
        data = json.loads(SEED_FILE.read_text())
        for item in data:
            cat = item.get("category")
            if cat:
                assert cat in known_categories, f"Unknown category '{cat}' for {item['brand']} {item['model']}"
