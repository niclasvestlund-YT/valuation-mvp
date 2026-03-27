"""Tests for OCR service and clients.

Clears caches and forces mock mode before each test to prevent
pollution from other tests that may load real OCR clients.
"""

import pytest

from backend.app.schemas.ocr_result import OcrResult


@pytest.fixture(autouse=True)
def _force_ocr_mocks():
    """Force mock mode and clear all OCR caches/singletons before each test."""
    from backend.app.core.config import settings
    from backend.app.utils.cache import _cache
    import backend.app.integrations.easyocr_client as easyocr_mod

    # Save originals
    orig_gv = settings.use_mock_google_vision
    orig_eo = settings.use_mock_easyocr

    # Force mock mode (bypass frozen dataclass)
    object.__setattr__(settings, "use_mock_google_vision", True)
    object.__setattr__(settings, "use_mock_easyocr", True)

    # Clear TTL cache (prevents stale real results from leaking in)
    _cache.clear()

    # Reset EasyOCR singleton (prevents real model from being used)
    easyocr_mod._reader = None

    yield

    # Restore originals
    object.__setattr__(settings, "use_mock_google_vision", orig_gv)
    object.__setattr__(settings, "use_mock_easyocr", orig_eo)
    _cache.clear()


class TestOcrResultSchema:
    def test_empty_result(self):
        result = OcrResult.empty()
        assert not result.has_text
        assert not result.has_logos
        assert result.source == "none"
        assert result.all_text_lower == ""

    def test_result_with_text(self):
        result = OcrResult(detected_text=["Sony WH-1000XM5"], source="test")
        assert result.has_text
        assert "sony" in result.all_text_lower

    def test_result_with_logos(self):
        result = OcrResult(detected_logos=["Sony"], source="test")
        assert result.has_logos
        assert "sony" in result.all_logos_lower


class TestGoogleVisionClient:
    def test_mock_configured(self):
        from backend.app.integrations.google_vision_client import GoogleVisionClient
        client = GoogleVisionClient()
        assert client.is_configured

    def test_mock_detect_returns_result(self):
        from backend.app.integrations.google_vision_client import GoogleVisionClient
        client = GoogleVisionClient()
        result = client.detect(b"fake image bytes for ocr test")
        assert result.has_text
        assert result.source == "google_vision_mock"
        assert result.raw_confidence > 0

    def test_mock_detect_has_logos(self):
        from backend.app.integrations.google_vision_client import GoogleVisionClient
        client = GoogleVisionClient()
        result = client.detect(b"fake image bytes for ocr test")
        assert result.has_logos
        assert "MockBrand" in result.detected_logos


class TestEasyOcrClient:
    def test_mock_configured(self):
        from backend.app.integrations.easyocr_client import EasyOcrClient
        client = EasyOcrClient()
        assert client.is_configured

    def test_mock_detect_returns_result(self):
        from backend.app.integrations.easyocr_client import EasyOcrClient
        client = EasyOcrClient()
        result = client.detect(b"fake image bytes for easyocr test")
        assert result.has_text
        assert result.source == "easyocr_mock"


class TestOcrService:
    def test_uses_google_vision_first(self):
        from backend.app.services.ocr_service import OcrService
        service = OcrService()
        result = service.detect(b"fake image bytes for service test")
        assert "google_vision" in result.source

    def test_returns_non_empty(self):
        from backend.app.services.ocr_service import OcrService
        service = OcrService()
        result = service.detect(b"fake image bytes for non-empty test")
        assert result.has_text or result.has_logos

    def test_fallback_chain(self):
        """Both mocks return results; first one (Google) wins."""
        from backend.app.services.ocr_service import OcrService
        service = OcrService()
        result = service.detect(b"test bytes for fallback chain test")
        assert result.source.startswith("google_vision")
