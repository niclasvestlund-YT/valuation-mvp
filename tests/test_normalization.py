"""Tests for product key normalization."""

from backend.app.utils.normalization import normalize_product_key


def test_basic_normalization():
    assert normalize_product_key("Sony", "WH-1000XM5") == "sony_wh-1000xm5"


def test_spaces_to_hyphens():
    assert normalize_product_key("Apple", "iPhone 15 Pro") == "apple_iphone-15-pro"


def test_brand_alias():
    assert normalize_product_key("DJI Innovation", "Osmo Pocket 3") == "dji_osmo-pocket-3"


def test_brand_alias_apple_inc():
    assert normalize_product_key("Apple Inc", "MacBook Air M2") == "apple_macbook-air-m2"


def test_empty_brand():
    assert normalize_product_key("", "WH-1000XM5") == "wh-1000xm5"


def test_empty_model():
    assert normalize_product_key("Sony", "") == "sony"


def test_both_empty():
    assert normalize_product_key("", "") == "unknown"


def test_whitespace_handling():
    assert normalize_product_key("  Sony  ", "  WH-1000XM5  ") == "sony_wh-1000xm5"


def test_special_characters_stripped():
    key = normalize_product_key("Sony", "WH-1000XM5 (2022)")
    assert key == "sony_wh-1000xm5-2022"
