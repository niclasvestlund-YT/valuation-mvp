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
    orig_attempted = easyocr_mod._reader_load_attempted

    # Force mock mode (bypass frozen dataclass)
    object.__setattr__(settings, "use_mock_google_vision", True)
    object.__setattr__(settings, "use_mock_easyocr", True)

    # Clear TTL cache (prevents stale real results from leaking in)
    _cache.clear()

    # Reset EasyOCR singleton (prevents real model from being used)
    easyocr_mod._reader = None
    easyocr_mod._reader_load_attempted = False

    yield

    # Restore originals
    object.__setattr__(settings, "use_mock_google_vision", orig_gv)
    object.__setattr__(settings, "use_mock_easyocr", orig_eo)
    easyocr_mod._reader_load_attempted = orig_attempted
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

    def test_reports_unconfigured_when_dependency_is_missing(self):
        from backend.app.core.config import settings
        import backend.app.integrations.easyocr_client as easyocr_mod
        from backend.app.integrations.easyocr_client import EasyOcrClient

        orig_mock = settings.use_mock_easyocr
        orig_enabled = settings.easyocr_enabled
        orig_attempted = easyocr_mod._reader_load_attempted
        orig_reader = easyocr_mod._reader
        try:
            object.__setattr__(settings, "use_mock_easyocr", False)
            object.__setattr__(settings, "easyocr_enabled", True)
            easyocr_mod._reader = None
            easyocr_mod._reader_load_attempted = False

            client = EasyOcrClient()
            assert not client.is_configured
        finally:
            object.__setattr__(settings, "use_mock_easyocr", orig_mock)
            object.__setattr__(settings, "easyocr_enabled", orig_enabled)
            easyocr_mod._reader = orig_reader
            easyocr_mod._reader_load_attempted = orig_attempted


class TestOcrService:
    def test_prefers_easyocr_when_local_text_is_useful(self):
        from backend.app.services.ocr_service import OcrService

        class StubGoogleVisionClient:
            is_configured = True

            def __init__(self):
                self.calls = 0

            def detect(self, image_bytes):
                self.calls += 1
                return OcrResult(detected_text=["Sony WH-1000XM5"], detected_logos=["Sony"], source="google")

        class StubEasyOcrClient:
            is_configured = True

            def __init__(self):
                self.calls = 0

            def detect(self, image_bytes):
                self.calls += 1
                return OcrResult(detected_text=["Sony WH-1000XM5"], source="easy")

        google = StubGoogleVisionClient()
        easy = StubEasyOcrClient()
        service = OcrService(google_client=google, easyocr_client=easy)
        result = service.detect(b"fake image bytes for service test")

        assert result.provider == "easyocr"
        assert easy.calls == 1
        assert google.calls == 0

    def test_falls_back_to_google_vision_when_easyocr_is_empty(self):
        from backend.app.services.ocr_service import OcrService

        class StubGoogleVisionClient:
            is_configured = True

            def __init__(self):
                self.calls = 0

            def detect(self, image_bytes):
                self.calls += 1
                return OcrResult(detected_text=["Sony WH-1000XM5"], detected_logos=["Sony"], source="google")

        class StubEasyOcrClient:
            is_configured = True

            def __init__(self):
                self.calls = 0

            def detect(self, image_bytes):
                self.calls += 1
                return OcrResult.empty()

        google = StubGoogleVisionClient()
        easy = StubEasyOcrClient()
        service = OcrService(google_client=google, easyocr_client=easy)
        result = service.detect(b"fake image bytes for non-empty test")

        assert result.provider == "google_vision"
        assert easy.calls == 1
        assert google.calls == 1

    def test_falls_back_to_google_vision_when_easyocr_text_is_weak(self):
        from backend.app.services.ocr_service import OcrService

        class StubGoogleVisionClient:
            is_configured = True

            def __init__(self):
                self.calls = 0

            def detect(self, image_bytes):
                self.calls += 1
                return OcrResult(detected_logos=["Sony"], source="google")

        class StubEasyOcrClient:
            is_configured = True

            def __init__(self):
                self.calls = 0

            def detect(self, image_bytes):
                self.calls += 1
                return OcrResult(detected_text=["Sony"], source="easy")

        google = StubGoogleVisionClient()
        easy = StubEasyOcrClient()
        service = OcrService(google_client=google, easyocr_client=easy)
        result = service.detect(b"test bytes for fallback chain test")

        assert result.provider == "google_vision"
        assert easy.calls == 1
        assert google.calls == 1

    def test_returns_weak_easyocr_when_google_vision_is_empty(self):
        from backend.app.services.ocr_service import OcrService

        class StubGoogleVisionClient:
            is_configured = True

            def __init__(self):
                self.calls = 0

            def detect(self, image_bytes):
                self.calls += 1
                return OcrResult.empty()

        class StubEasyOcrClient:
            is_configured = True

            def __init__(self):
                self.calls = 0

            def detect(self, image_bytes):
                self.calls += 1
                return OcrResult(detected_text=["Sony"], source="easy")

        google = StubGoogleVisionClient()
        easy = StubEasyOcrClient()
        service = OcrService(google_client=google, easyocr_client=easy)
        result = service.detect(b"test bytes for weak easyocr fallback")

        assert result.provider == "easyocr"
        assert result.has_text
        assert easy.calls == 1
        assert google.calls == 1
