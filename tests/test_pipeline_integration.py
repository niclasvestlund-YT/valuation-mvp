"""Integration tests for the intelligence layer pipeline.

Tests the full flow: product normalization → validation → cache CRUD → embedding.
Uses mock mode for embeddings and in-memory data (no real DB required).
"""

import os

os.environ["USE_MOCK_EMBEDDING"] = "true"

from backend.app.services.data_validator import validate_comparable
from backend.app.services.embedding_service import (
    EMBEDDING_DIM,
    compute_embedding,
    compute_embedding_from_base64,
    compute_image_hash,
)
from backend.app.utils.normalization import normalize_product_key


class TestPipelineNormalizationToValidation:
    """Test that product keys flow correctly into validation."""

    def test_normalized_key_validates_matching_title(self):
        key = normalize_product_key("Sony", "WH-1000XM5")
        assert key == "sony_wh-1000xm5"
        result = validate_comparable("Sony WH-1000XM5 svarta", 2500, key)
        assert result.valid

    def test_normalized_key_rejects_wrong_product(self):
        key = normalize_product_key("Sony", "WH-1000XM5")
        result = validate_comparable("Apple AirPods Pro 2nd gen", 2500, key)
        assert not result.valid
        assert result.reject_reason == "product_mismatch"

    def test_dji_normalization_validates(self):
        key = normalize_product_key("DJI Innovation", "Osmo Pocket 3")
        assert key == "dji_osmo-pocket-3"
        result = validate_comparable("DJI Osmo Pocket 3 kamera", 4000, key)
        assert result.valid

    def test_apple_alias_normalization(self):
        key = normalize_product_key("Apple Inc", "MacBook Air M2")
        assert key == "apple_macbook-air-m2"
        result = validate_comparable("Apple MacBook Air M2 2022", 8000, key)
        assert result.valid


class TestPipelineEmbeddingFlow:
    """Test embedding computation + hash deduplication flow."""

    def test_same_image_same_hash(self):
        img = b"test image bytes for embedding pipeline"
        h1 = compute_image_hash(img)
        h2 = compute_image_hash(img)
        assert h1 == h2

    def test_embedding_dimension_consistency(self):
        img1 = b"product image one for testing embedding dimension"
        img2 = b"product image two for testing embedding dimension"
        v1 = compute_embedding(img1)
        v2 = compute_embedding(img2)
        assert v1 is not None and v2 is not None
        assert len(v1) == EMBEDDING_DIM
        assert len(v2) == EMBEDDING_DIM

    def test_different_products_different_embeddings(self):
        v1 = compute_embedding(b"sony wh-1000xm5 headphones image bytes padding")
        v2 = compute_embedding(b"apple iphone 15 pro smartphone image bytes padding")
        assert v1 != v2

    def test_base64_roundtrip(self):
        import base64
        raw = b"test raw image bytes for base64 roundtrip check"
        b64 = base64.b64encode(raw).decode()
        v_raw = compute_embedding(raw)
        v_b64 = compute_embedding_from_base64(b64)
        assert v_raw == v_b64


class TestPipelineValidationEdgeCases:
    """Edge cases that combine normalization + validation."""

    def test_price_boundary_at_minimum(self):
        key = normalize_product_key("Sony", "WH-1000XM4")
        result = validate_comparable("Sony WH-1000XM4", 50, key)
        assert result.valid

    def test_price_boundary_below_minimum(self):
        key = normalize_product_key("Sony", "WH-1000XM4")
        result = validate_comparable("Sony WH-1000XM4", 49, key)
        assert not result.valid

    def test_flagged_defect_still_valid(self):
        key = normalize_product_key("Sony", "WH-1000XM4")
        result = validate_comparable("Sony WH-1000XM4 trasig", 500, key)
        assert result.valid
        assert "defect_keywords" in result.warnings

    def test_bundle_rejected_even_with_correct_product(self):
        key = normalize_product_key("Sony", "WH-1000XM4")
        result = validate_comparable("Sony WH-1000XM4 paket med case", 2000, key)
        assert not result.valid
        assert result.reject_reason == "bundle_listing"

    def test_outlier_warning_with_high_price(self):
        key = normalize_product_key("Apple", "iPhone 15 Pro")
        result = validate_comparable("Apple iPhone 15 Pro 256GB", 25000, key, existing_median=8000)
        assert result.valid
        assert "price_outlier_high" in result.warnings
