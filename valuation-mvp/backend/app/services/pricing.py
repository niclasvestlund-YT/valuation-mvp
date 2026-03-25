# DEPRECATED: This is the legacy pricing engine.
# Use backend/app/services/pricing_service.py (CANONICAL PRICING ENGINE) instead.
import statistics
from ..models import MarketListing


def calculate_pricing(
    listings: list[MarketListing],
    new_price: float | None,
    depreciation_estimate: float | None = None,
) -> dict:
    if not listings and depreciation_estimate is None:
        return _empty(new_price)

    sold = [item for item in listings if item.status == "sold" and item.relevance_score >= 0.25]
    active = [item for item in listings if item.status == "active" and item.relevance_score >= 0.25]

    # Weight sold 1.5x since they represent real transactions
    weighted_listings = [(item, 1.5) for item in sold] + [(item, 1.0) for item in active]

    if not weighted_listings and depreciation_estimate is not None:
        return _depreciation_only(new_price, depreciation_estimate)

    total_weight = sum(item.relevance_score * w for item, w in weighted_listings)
    if total_weight == 0:
        return _empty(new_price)

    estimated_value = sum(item.price * item.relevance_score * w for item, w in weighted_listings) / total_weight

    # If fewer than 3 comparables, blend in depreciation estimate
    if len(weighted_listings) < 3 and depreciation_estimate is not None:
        blend_factor = 0.3
        estimated_value = estimated_value * (1 - blend_factor) + depreciation_estimate * blend_factor

    all_prices = [item.price for item, _ in weighted_listings]
    if len(all_prices) >= 4:
        value_range = (
            round(statistics.quantiles(all_prices, n=4)[0]),
            round(statistics.quantiles(all_prices, n=4)[2]),
        )
    elif all_prices:
        value_range = (round(min(all_prices) * 0.9), round(max(all_prices) * 1.1))
    else:
        value_range = (round(estimated_value * 0.85), round(estimated_value * 1.15))

    # Confidence calculation
    sources = {item.source for item, _ in weighted_listings}
    confidence = min(len(weighted_listings), 10) / 10 * 0.75
    if sold:
        confidence = min(confidence + 0.15, 1.0)
    confidence += min(len(sources) - 1, 3) * 0.05
    if not weighted_listings:
        confidence -= 0.3
    confidence = round(max(0.0, min(confidence, 1.0)), 4)

    validated_new_price, depreciation_percent = _validate_depreciation(new_price, estimated_value)

    return {
        "estimated_value": round(estimated_value),
        "value_range": value_range,
        "confidence": confidence,
        "new_price": validated_new_price,
        "depreciation_percent": depreciation_percent,
        "comparables_used": len(weighted_listings),
        "sold_count": len(sold),
        "active_count": len(active),
        "sources_used": list(sources),
    }


def _validate_depreciation(
    new_price: float | None,
    estimated_value: float,
) -> tuple[float | None, float | None]:
    """Validate new_price against estimated_value.
    Returns (validated_new_price, depreciation_percent) or (None, None) if invalid.
    """
    if not new_price or new_price <= 0:
        return None, None

    # New price must be higher than second-hand value
    if new_price <= estimated_value:
        import logging
        logging.getLogger(__name__).warning(
            f"New price ({new_price}) <= estimated value ({estimated_value}) — discarding new price as invalid"
        )
        return None, None

    depreciation_percent = round((1 - estimated_value / new_price) * 100, 1)

    # Depreciation must be 0-90%
    if not (0 <= depreciation_percent <= 90):
        import logging
        logging.getLogger(__name__).warning(
            f"Depreciation {depreciation_percent}% outside valid range — discarding"
        )
        return None, None

    return new_price, depreciation_percent


def _empty(new_price: float | None) -> dict:
    return {
        "estimated_value": None,
        "value_range": None,
        "confidence": None,
        "new_price": new_price,
        "depreciation_percent": None,
        "comparables_used": 0,
        "sold_count": 0,
        "active_count": 0,
        "sources_used": [],
    }


def _depreciation_only(new_price: float | None, estimate: float) -> dict:
    value_range = (round(estimate * 0.85), round(estimate * 1.15))
    validated_new_price, depreciation_percent = _validate_depreciation(new_price, estimate)
    return {
        "estimated_value": estimate,
        "value_range": value_range,
        "confidence": 0.35,
        "new_price": validated_new_price,
        "depreciation_percent": depreciation_percent,
        "comparables_used": 0,
        "sold_count": 0,
        "active_count": 0,
        "sources_used": [],
    }
