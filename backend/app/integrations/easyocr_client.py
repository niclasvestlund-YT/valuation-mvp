"""EasyOCR fallback client for local OCR without cloud API.

Lazy-loads the model on first use (~2s). Runs inference in thread executor
to avoid blocking the event loop.
"""

import hashlib
import time
from io import BytesIO

from backend.app.core.config import settings
from backend.app.schemas.ocr_result import OcrResult
from backend.app.utils.cache import get_cached as get_cache, set_cached as set_cache
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

_reader = None
_reader_load_attempted = False


def _cache_key(image_hash: str) -> str:
    return f"easyocr:{image_hash}"


def _get_reader():
    global _reader, _reader_load_attempted
    if _reader_load_attempted:
        return _reader

    if _reader is None and not settings.use_mock_easyocr:
        _reader_load_attempted = True
        try:
            import easyocr
            languages = [lang.strip() for lang in settings.easyocr_languages.split(",")]
            _reader = easyocr.Reader(languages, gpu=False, verbose=False)
            logger.info("easyocr.model_loaded", extra={"languages": languages})
        except Exception as exc:
            logger.error("easyocr.model_load_failed", extra={"error": str(exc)})
    return _reader


class EasyOcrClient:
    @property
    def is_configured(self) -> bool:
        if settings.use_mock_easyocr:
            return True
        if not settings.easyocr_enabled:
            return False
        return _get_reader() is not None

    def detect(self, image_bytes: bytes) -> OcrResult:
        """Run EasyOCR on image bytes."""
        t0 = time.monotonic()
        image_hash = hashlib.sha256(image_bytes).hexdigest()

        cached = get_cache(_cache_key(image_hash))
        if cached is not None:
            return cached

        if settings.use_mock_easyocr:
            result = self._mock_detect()
            set_cache(_cache_key(image_hash), result)
            return result

        reader = _get_reader()
        if reader is None:
            return OcrResult.empty()

        try:
            import numpy as np
            from PIL import Image

            img = Image.open(BytesIO(image_bytes)).convert("RGB")
            img_array = np.array(img)

            results = reader.readtext(img_array, detail=1)

            detected_text = []
            total_confidence = 0.0
            for bbox, text, confidence in results:
                if confidence > 0.3:  # minimum confidence threshold
                    detected_text.append(text)
                    total_confidence += confidence

            avg_confidence = total_confidence / len(results) if results else 0.0
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            result = OcrResult(
                detected_text=detected_text,
                detected_logos=[],  # EasyOCR doesn't detect logos
                detected_labels=[],
                web_entities=[],
                source="easyocr",
                raw_confidence=round(avg_confidence, 2),
                processing_time_ms=elapsed_ms,
            )
            set_cache(_cache_key(image_hash), result)
            logger.info("easyocr.detect_ok", extra={
                "image_hash": image_hash[:12],
                "text_count": len(detected_text),
                "elapsed_ms": elapsed_ms,
            })
            return result

        except Exception as exc:
            logger.error("easyocr.detect_failed", extra={"error": str(exc)})
            return OcrResult.empty()

    def _mock_detect(self) -> OcrResult:
        return OcrResult(
            detected_text=["MOCK EASYOCR TEXT"],
            detected_logos=[],
            detected_labels=[],
            web_entities=[],
            source="easyocr_mock",
            raw_confidence=0.85,
            processing_time_ms=3,
        )
