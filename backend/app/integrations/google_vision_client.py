"""Google Cloud Vision API client for OCR and logo detection.

Sends TEXT_DETECTION + LOGO_DETECTION + LABEL_DETECTION in one call.
Caches results using SHA-256 image hash.
"""

import hashlib
import time
from typing import Any

from backend.app.core.config import settings
from backend.app.schemas.ocr_result import OcrResult
from backend.app.utils import api_counter
from backend.app.utils.cache import get_cached as get_cache, set_cached as set_cache
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)


def _cache_key(image_hash: str) -> str:
    return f"google_vision:{image_hash}"


def _quota_units_per_request() -> int:
    units = 3  # TEXT_DETECTION + LOGO_DETECTION + LABEL_DETECTION
    if settings.google_vision_use_web_detection:
        units += 1
    return units


class GoogleVisionClient:
    def __init__(self) -> None:
        self._client = None

    @property
    def is_configured(self) -> bool:
        if settings.use_mock_google_vision:
            return True
        if not settings.google_vision_enabled:
            return False
        try:
            import google.auth
            google.auth.default()
            return True
        except Exception:
            return False

    def _get_client(self):
        if self._client is None and not settings.use_mock_google_vision:
            try:
                from google.cloud import vision
                self._client = vision.ImageAnnotatorClient()
            except Exception as exc:
                logger.error("google_vision.client_init_failed", extra={"error": str(exc)})
        return self._client

    def detect(self, image_bytes: bytes) -> OcrResult:
        """Run OCR + logo + label detection on image bytes."""
        t0 = time.monotonic()
        image_hash = hashlib.sha256(image_bytes).hexdigest()

        # Check cache
        cached = get_cache(_cache_key(image_hash))
        if cached is not None:
            logger.debug("google_vision.cache_hit", extra={"image_hash": image_hash[:12]})
            return cached

        if settings.use_mock_google_vision:
            result = self._mock_detect(image_bytes)
            set_cache(_cache_key(image_hash), result)
            return result

        client = self._get_client()
        if client is None:
            return OcrResult.empty()

        try:
            from google.cloud import vision

            quota = api_counter.reserve_quota("google_vision_ocr", amount=_quota_units_per_request())
            if not quota["allowed"]:
                logger.warning(
                    "google_vision.quota_exhausted limit=%s remaining=%s",
                    quota["quota_limit"],
                    quota["quota_remaining"],
                )
                return OcrResult.empty()

            image = vision.Image(content=image_bytes)
            features = [
                vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION),
                vision.Feature(type_=vision.Feature.Type.LOGO_DETECTION),
                vision.Feature(type_=vision.Feature.Type.LABEL_DETECTION),
            ]
            if settings.google_vision_use_web_detection:
                features.append(vision.Feature(type_=vision.Feature.Type.WEB_DETECTION))

            request = vision.AnnotateImageRequest(image=image, features=features)
            response = client.annotate_image(request=request, timeout=settings.google_vision_timeout_seconds)

            detected_text = []
            if response.text_annotations:
                # First annotation is the full text block
                detected_text = [response.text_annotations[0].description]

            detected_logos = [logo.description for logo in (response.logo_annotations or [])]
            detected_labels = [label.description for label in (response.label_annotations or [])[:10]]

            web_entities = []
            if settings.google_vision_use_web_detection and response.web_detection:
                web_entities = [
                    entity.description
                    for entity in (response.web_detection.web_entities or [])[:10]
                    if entity.description
                ]

            confidence = 0.0
            if response.text_annotations:
                confidence = max(
                    (ann.confidence for ann in response.text_annotations if hasattr(ann, "confidence")),
                    default=0.8,
                )

            elapsed_ms = int((time.monotonic() - t0) * 1000)
            result = OcrResult(
                detected_text=detected_text,
                detected_logos=detected_logos,
                detected_labels=detected_labels,
                web_entities=web_entities,
                source="google_vision",
                raw_confidence=confidence,
                processing_time_ms=elapsed_ms,
            )
            set_cache(_cache_key(image_hash), result)
            api_counter.increment("google_vision_ocr")
            logger.info("google_vision.detect_ok", extra={
                "image_hash": image_hash[:12],
                "text_count": len(detected_text),
                "logo_count": len(detected_logos),
                "label_count": len(detected_labels),
                "elapsed_ms": elapsed_ms,
            })
            return result

        except Exception as exc:
            api_counter.increment_error("google_vision_ocr")
            logger.error("google_vision.detect_failed", extra={"error": str(exc)})
            return OcrResult.empty()

    def _mock_detect(self, image_bytes: bytes) -> OcrResult:
        """Return a mock result for testing."""
        return OcrResult(
            detected_text=["MOCK OCR TEXT"],
            detected_logos=["MockBrand"],
            detected_labels=["electronics", "headphones"],
            web_entities=[],
            source="google_vision_mock",
            raw_confidence=0.9,
            processing_time_ms=5,
        )
