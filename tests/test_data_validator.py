"""Tests for the ingestion data validator."""

import pytest

from backend.app.services.data_validator import validate_comparable


class TestHardRejects:
    def test_price_below_minimum(self):
        result = validate_comparable("Sony WH-1000XM4", 30, "sony_wh-1000xm4")
        assert not result.valid
        assert result.reject_reason == "price_below_minimum"

    def test_price_above_maximum(self):
        result = validate_comparable("Sony WH-1000XM4", 150_000, "sony_wh-1000xm4")
        assert not result.valid
        assert result.reject_reason == "price_above_maximum"

    def test_title_too_short(self):
        result = validate_comparable("Hi", 500, "sony_wh-1000xm4")
        assert not result.valid
        assert result.reject_reason == "title_too_short"

    def test_empty_title(self):
        result = validate_comparable("", 500, "sony_wh-1000xm4")
        assert not result.valid
        assert result.reject_reason == "title_too_short"

    def test_bundle_listing_paket(self):
        result = validate_comparable("Sony WH-1000XM4 paket med laddare", 500, "sony_wh-1000xm4")
        assert not result.valid
        assert result.reject_reason == "bundle_listing"

    def test_bundle_listing_x2(self):
        result = validate_comparable("Sony WH-1000XM4 x2 st", 500, "sony_wh-1000xm4")
        assert not result.valid
        assert result.reject_reason == "bundle_listing"

    def test_bundle_listing_lot(self):
        result = validate_comparable("Lot of Sony headphones WH-1000XM4", 500, "sony_wh-1000xm4")
        assert not result.valid
        assert result.reject_reason == "bundle_listing"

    def test_product_mismatch(self):
        result = validate_comparable("Samsung Galaxy S24 Ultra", 5000, "sony_wh-1000xm4")
        assert not result.valid
        assert result.reject_reason == "product_mismatch"


class TestValidListings:
    def test_valid_listing(self):
        result = validate_comparable("Sony WH-1000XM4 hörlurar", 2500, "sony_wh-1000xm4")
        assert result.valid
        assert result.reject_reason is None
        assert result.warnings == []

    def test_valid_listing_partial_key_match(self):
        result = validate_comparable("DJI Osmo Pocket 3 kamera", 4000, "dji_osmo-pocket-3")
        assert result.valid

    def test_boundary_price_minimum(self):
        result = validate_comparable("Sony WH-1000XM4 begagnad", 50, "sony_wh-1000xm4")
        assert result.valid

    def test_boundary_price_maximum(self):
        result = validate_comparable("Sony WH-1000XM4 begagnad", 100_000, "sony_wh-1000xm4")
        assert result.valid


class TestSoftWarnings:
    def test_defect_keyword_warning(self):
        result = validate_comparable("Sony WH-1000XM4 trasig", 500, "sony_wh-1000xm4")
        assert result.valid
        assert "defect_keywords" in result.warnings

    def test_price_outlier_high(self):
        result = validate_comparable("Sony WH-1000XM4", 10000, "sony_wh-1000xm4", existing_median=2500)
        assert result.valid
        assert "price_outlier_high" in result.warnings

    def test_price_outlier_low(self):
        result = validate_comparable("Sony WH-1000XM4", 300, "sony_wh-1000xm4", existing_median=2500)
        assert result.valid
        assert "price_outlier_low" in result.warnings

    def test_no_warnings_within_range(self):
        result = validate_comparable("Sony WH-1000XM4", 2000, "sony_wh-1000xm4", existing_median=2500)
        assert result.valid
        assert result.warnings == []
