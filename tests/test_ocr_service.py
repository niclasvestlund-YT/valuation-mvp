"""Tests for OCR service and clients."""

import os

os.environ["USE_MOCK_GOOGLE_VISION"] = "true"
os.environ["USE_MOCK_EASYOCR"] = "true"

from backend.app.integrations.easyocr_client import EasyOcrClient
from backend.app.integrations.google_vision_client import GoogleVisionClient
from backend.app.schemas.ocr_result import OcrResult
from backend.app.services.ocr_service import OcrService


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
        client = GoogleVisionClient()
        assert client.is_configured

    def test_mock_detect_returns_result(self):
        client = GoogleVisionClient()
        result = client.detect(b"fake image bytes")
        assert result.has_text
        assert result.source == "google_vision_mock"
        assert result.raw_confidence > 0

    def test_mock_detect_has_logos(self):
        client = GoogleVisionClient()
        result = client.detect(b"fake image bytes")
        assert result.has_logos
        assert "MockBrand" in result.detected_logos


class TestEasyOcrClient:
    def test_mock_configured(self):
        client = EasyOcrClient()
        assert client.is_configured

    def test_mock_detect_returns_result(self):
        client = EasyOcrClient()
        result = client.detect(b"fake image bytes")
        assert result.has_text
        assert result.source == "easyocr_mock"


class TestOcrService:
    def test_uses_google_vision_first(self):
        service = OcrService()
        result = service.detect(b"fake image bytes")
        # Google Vision mock should be preferred
        assert "google_vision" in result.source

    def test_returns_non_empty(self):
        service = OcrService()
        result = service.detect(b"fake image bytes")
        assert result.has_text or result.has_logos

    def test_fallback_chain(self):
        """Both mocks return results; first one (Google) wins."""
        service = OcrService()
        result = service.detect(b"test bytes for fallback")
        assert result.source.startswith("google_vision")
