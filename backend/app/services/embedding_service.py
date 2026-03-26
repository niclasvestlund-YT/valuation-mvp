"""Embedding service for product image similarity using SigLIP/CLIP vectors.

Computes 768-dim embeddings from product images. Used for:
- Fast-path identification (skip OpenAI Vision for known products)
- Learning loop (verified embeddings improve over time)
"""

import hashlib
from io import BytesIO
from typing import Any

from backend.app.core.config import settings
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

_model = None
_processor = None

EMBEDDING_DIM = 768


def _get_model():
    """Lazy-load SigLIP model. ~100ms on CPU after first load."""
    global _model, _processor
    if _model is None:
        if settings.use_mock_embedding:
            return None, None
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(settings.embedding_model)
            logger.info("embedding.model_loaded", extra={"model": settings.embedding_model})
        except Exception as exc:
            logger.error("embedding.model_load_failed", extra={"error": str(exc)})
            return None, None
    return _model, _processor


def compute_image_hash(image_bytes: bytes) -> str:
    """SHA-256 hash of image bytes for deduplication."""
    return hashlib.sha256(image_bytes).hexdigest()


def compute_embedding(image_bytes: bytes) -> list[float] | None:
    """Compute embedding vector from image bytes. Returns 768-dim list or None on failure.

    When USE_MOCK_EMBEDDING=true, returns a deterministic mock vector based on image hash.
    """
    if settings.use_mock_embedding:
        # Deterministic mock: hash-based pseudo-random vector
        h = compute_image_hash(image_bytes)
        import struct
        # Use first 768*4 bytes of repeated hash as float seeds
        hash_bytes = (h.encode() * 100)[:EMBEDDING_DIM * 4]
        mock_vec = [float(b) / 255.0 for b in hash_bytes[:EMBEDDING_DIM]]
        # Normalize to unit vector
        norm = sum(x * x for x in mock_vec) ** 0.5
        if norm > 0:
            mock_vec = [x / norm for x in mock_vec]
        return mock_vec

    model, _ = _get_model()
    if model is None:
        logger.warning("embedding.model_unavailable")
        return None

    try:
        from PIL import Image
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        # SentenceTransformer encodes images directly
        embedding = model.encode(img, normalize_embeddings=True)
        vec = embedding.tolist()
        if len(vec) != EMBEDDING_DIM:
            logger.warning("embedding.unexpected_dim", extra={"dim": len(vec), "expected": EMBEDDING_DIM})
        return vec
    except Exception as exc:
        logger.error("embedding.compute_failed", extra={"error": str(exc)})
        return None


def compute_embedding_from_base64(base64_data: str) -> list[float] | None:
    """Compute embedding from a base64-encoded image string."""
    import base64
    try:
        # Strip data URL prefix if present
        if "," in base64_data:
            base64_data = base64_data.split(",", 1)[1]
        image_bytes = base64.b64decode(base64_data)
        return compute_embedding(image_bytes)
    except Exception as exc:
        logger.error("embedding.base64_decode_failed", extra={"error": str(exc)})
        return None
