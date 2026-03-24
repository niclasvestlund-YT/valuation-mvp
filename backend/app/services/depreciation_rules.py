CATEGORY_DEPRECIATION_RANGES = {
    "smartphone": (0.38, 0.72),
    "tablet": (0.4, 0.74),
    "laptop": (0.42, 0.78),
    "headphones": (0.28, 0.62),
    "camera": (0.5, 0.82),
    "smartwatch": (0.32, 0.62),
    "console": (0.42, 0.7),
    "router": (0.22, 0.5),
    "accessory": (0.2, 0.48),
    "manual_override": (0.3, 0.72),
    "unknown": (0.25, 0.6),
}

CONDITION_ADJUSTMENTS = {
    "excellent": 0.05,
    "good": 0.0,
    "fair": -0.07,
    "poor": -0.16,
}


def get_depreciation_range(category: str | None, condition: str | None = None) -> tuple[float, float]:
    normalized_category = (category or "unknown").lower()
    low, high = CATEGORY_DEPRECIATION_RANGES.get(
        normalized_category,
        CATEGORY_DEPRECIATION_RANGES["unknown"],
    )

    adjustment = CONDITION_ADJUSTMENTS.get((condition or "good").lower(), 0.0)
    adjusted_low = max(0.1, min(low + adjustment, 0.95))
    adjusted_high = max(adjusted_low + 0.05, min(high + adjustment, 0.98))
    return round(adjusted_low, 2), round(adjusted_high, 2)
