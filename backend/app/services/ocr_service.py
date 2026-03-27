"""OCR service — orchestrates Google Vision → EasyOCR → empty fallback.

Returns the best available OCR result for cross-verification with
OpenAI Vision product identification.
"""

from backend.app.core.config import settings
from backend.app.integrations.easyocr_client import EasyOcrClient
from backend.app.integrations.google_vision_client import GoogleVisionClient
from backend.app.schemas.ocr_result import OcrResult
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)


class OcrService:
    def __init__(
        self,
        google_client: GoogleVisionClient | None = None,
        easyocr_client: EasyOcrClient | None = None,
    ) -> None:
        self.google_client = google_client or GoogleVisionClient()
        self.easyocr_client = easyocr_client or EasyOcrClient()

    def detect(self, image_bytes: bytes) -> OcrResult:
        """Run OCR with cascading fallback: Google Vision → EasyOCR → empty."""
        # Try Google Vision first (best quality)
        if self.google_client.is_configured:
            result = self.google_client.detect(image_bytes)
            if result.has_text or result.has_logos:
                result.provider = "google_vision"
                result.text_found = result.has_text
                logger.info("ocr.source_used", extra={"source": result.source, "provider": "google_vision"})
                return result
            logger.info("ocr.google_vision_empty_fallback_to_easyocr")

        # Fallback to EasyOCR (local, no API cost)
        if self.easyocr_client.is_configured:
            result = self.easyocr_client.detect(image_bytes)
            if result.has_text:
                result.provider = "easyocr"
                result.text_found = True
                logger.info("ocr.source_used", extra={"source": result.source, "provider": "easyocr"})
                return result
            logger.info("ocr.easyocr_empty")

        # No OCR results available
        logger.info("ocr.no_results")
        empty = OcrResult.empty()
        empty.provider = "none"
        empty.text_found = False
        return empty
