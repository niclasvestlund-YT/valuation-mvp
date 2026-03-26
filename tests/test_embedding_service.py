"""Tests for the embedding service."""

import base64
import os

import pytest

# Force mock mode for tests
os.environ["USE_MOCK_EMBEDDING"] = "true"

from backend.app.services.embedding_service import (
    EMBEDDING_DIM,
    compute_embedding,
    compute_embedding_from_base64,
    compute_image_hash,
)


# Minimal valid 1x1 PNG
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

_TINY_PNG_B64 = base64.b64encode(_TINY_PNG).decode()


class TestImageHash:
    def test_hash_deterministic(self):
        h1 = compute_image_hash(_TINY_PNG)
        h2 = compute_image_hash(_TINY_PNG)
        assert h1 == h2

    def test_hash_is_sha256(self):
        h = compute_image_hash(_TINY_PNG)
        assert len(h) == 64  # SHA-256 hex length
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_images_different_hash(self):
        h1 = compute_image_hash(_TINY_PNG)
        h2 = compute_image_hash(b"different image data")
        assert h1 != h2


class TestMockEmbedding:
    def test_returns_correct_dimensions(self):
        vec = compute_embedding(_TINY_PNG)
        assert vec is not None
        assert len(vec) == EMBEDDING_DIM

    def test_deterministic(self):
        v1 = compute_embedding(_TINY_PNG)
        v2 = compute_embedding(_TINY_PNG)
        assert v1 == v2

    def test_normalized(self):
        vec = compute_embedding(_TINY_PNG)
        assert vec is not None
        norm = sum(x * x for x in vec) ** 0.5
        assert abs(norm - 1.0) < 0.01

    def test_different_images_different_vectors(self):
        v1 = compute_embedding(_TINY_PNG)
        v2 = compute_embedding(b"different image bytes for embedding test pad pad")
        assert v1 != v2


class TestBase64Embedding:
    def test_raw_base64(self):
        vec = compute_embedding_from_base64(_TINY_PNG_B64)
        assert vec is not None
        assert len(vec) == EMBEDDING_DIM

    def test_data_url_prefix(self):
        data_url = f"data:image/png;base64,{_TINY_PNG_B64}"
        vec = compute_embedding_from_base64(data_url)
        assert vec is not None
        assert len(vec) == EMBEDDING_DIM

    def test_matches_raw(self):
        v1 = compute_embedding(_TINY_PNG)
        v2 = compute_embedding_from_base64(_TINY_PNG_B64)
        assert v1 == v2

    def test_invalid_base64_returns_none(self):
        vec = compute_embedding_from_base64("not-valid-base64!!!")
        assert vec is None
