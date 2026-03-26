"""Cross-verify OCR results against OpenAI Vision identification.

Rules:
- "no text found" is NOT a contradiction (many products have minimal text)
- Brand/model match boosts confidence
- Brand/model contradiction reduces confidence
"""

from dataclasses import dataclass

from backend.app.schemas.ocr_result import OcrResult
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class VerificationResult:
    brand_match: bool = False
    model_match: bool = False
    has_contradiction: bool = False
    confidence_delta: float = 0.0
    details: str = ""


def _normalize(text: str | None) -> str:
    return " ".join((text or "").lower().replace("-", " ").split())


def verify_ocr_against_identification(
    ocr: OcrResult,
    *,
    brand: str | None,
    model: str | None,
) -> VerificationResult:
    """Cross-verify OCR text/logos against identified brand + model.

    Returns verification result with confidence adjustment.
    """
    if not ocr.has_text and not ocr.has_logos:
        # No OCR data = no evidence either way. NOT a contradiction.
        return VerificationResult(details="no_ocr_data")

    all_text = _normalize(ocr.all_text_lower)
    all_logos = [_normalize(logo) for logo in ocr.detected_logos]

    brand_norm = _normalize(brand)
    model_norm = _normalize(model)

    brand_match = False
    model_match = False
    has_contradiction = False

    # Brand matching
    if brand_norm:
        brand_in_text = brand_norm in all_text
        brand_in_logos = any(brand_norm in logo for logo in all_logos)
        brand_match = brand_in_text or brand_in_logos

        # Check for contradicting brand in logos
        if not brand_match and all_logos:
            known_brands = {
                "apple", "sony", "samsung", "dji", "bose", "jbl",
                "canon", "nikon", "google", "microsoft", "nintendo",
                "gopro", "marshall", "sennheiser", "lg", "hp", "dell",
                "lenovo", "asus", "xiaomi", "huawei", "oneplus",
            }
            found_brands = [logo for logo in all_logos if logo in known_brands]
            if found_brands and brand_norm not in found_brands:
                has_contradiction = True

    # Model matching
    if model_norm:
        model_tokens = model_norm.split()
        significant_tokens = [t for t in model_tokens if len(t) >= 3 or any(c.isdigit() for c in t)]
        if significant_tokens:
            matches = sum(1 for token in significant_tokens if token in all_text)
            model_match = matches >= len(significant_tokens) * 0.6  # 60% token match

    # Confidence adjustment
    confidence_delta = 0.0
    if brand_match and model_match:
        confidence_delta = 0.05  # Strong OCR confirmation
    elif brand_match:
        confidence_delta = 0.02  # Brand confirmed
    elif has_contradiction:
        confidence_delta = -0.08  # Brand contradicted

    details = []
    if brand_match:
        details.append("brand_confirmed")
    if model_match:
        details.append("model_confirmed")
    if has_contradiction:
        details.append("brand_contradicted")
    if not details:
        details.append("no_strong_signal")

    result = VerificationResult(
        brand_match=brand_match,
        model_match=model_match,
        has_contradiction=has_contradiction,
        confidence_delta=confidence_delta,
        details=", ".join(details),
    )

    logger.info("ocr_verification", extra={
        "brand": brand,
        "model": model,
        "brand_match": brand_match,
        "model_match": model_match,
        "contradiction": has_contradiction,
        "delta": confidence_delta,
    })

    return result
