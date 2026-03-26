"""Ingestion validator for market comparables and new price data."""

from dataclasses import dataclass, field

from backend.app.core.thresholds import (
    COMPARABLE_MAX_PRICE_SEK,
    COMPARABLE_MIN_PRICE_SEK,
    COMPARABLE_MIN_TITLE_LENGTH,
    COMPARABLE_OUTLIER_RATIO,
)


BUNDLE_PATTERNS = {"st.", "lot", "paket", "bundle", "x2", "x3", "set of", "st "}
DEFECT_PATTERNS = {"trasig", "defekt", "for parts", "ej fungerande", "broken", "faulty"}


@dataclass
class ValidationResult:
    valid: bool
    reject_reason: str | None = None
    warnings: list[str] = field(default_factory=list)


def validate_comparable(
    title: str,
    price_sek: int,
    product_key: str,
    existing_median: int | None = None,
) -> ValidationResult:
    """Validate a market comparable before storage.

    Hard rejects: never store.
    Soft warnings: store but flag.
    """
    title_lower = (title or "").lower().strip()

    # Hard rejects
    if price_sek < COMPARABLE_MIN_PRICE_SEK:
        return ValidationResult(valid=False, reject_reason="price_below_minimum")

    if price_sek > COMPARABLE_MAX_PRICE_SEK:
        return ValidationResult(valid=False, reject_reason="price_above_maximum")

    if len(title_lower) < COMPARABLE_MIN_TITLE_LENGTH:
        return ValidationResult(valid=False, reject_reason="title_too_short")

    if any(pattern in title_lower for pattern in BUNDLE_PATTERNS):
        return ValidationResult(valid=False, reject_reason="bundle_listing")

    # Check brand or model presence in title
    key_parts = product_key.replace("_", " ").replace("-", " ").split()
    significant_parts = [p for p in key_parts if len(p) >= 3]
    if significant_parts and not any(part in title_lower for part in significant_parts):
        return ValidationResult(valid=False, reject_reason="product_mismatch")

    # Soft warnings
    warnings: list[str] = []

    if any(pattern in title_lower for pattern in DEFECT_PATTERNS):
        warnings.append("defect_keywords")

    if existing_median and existing_median > 0:
        if price_sek > existing_median * COMPARABLE_OUTLIER_RATIO:
            warnings.append("price_outlier_high")
        if price_sek < existing_median * 0.2:
            warnings.append("price_outlier_low")

    return ValidationResult(valid=True, warnings=warnings)
