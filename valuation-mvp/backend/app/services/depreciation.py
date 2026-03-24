from datetime import datetime

DEPRECIATION_CURVES: dict[str, dict[int, float]] = {
    "smartphone": {1: 0.35, 2: 0.50, 3: 0.65, 4: 0.75, 5: 0.85},
    "laptop":     {1: 0.25, 2: 0.40, 3: 0.55, 4: 0.65, 5: 0.75},
    "headphones": {1: 0.30, 2: 0.45, 3: 0.55, 4: 0.65, 5: 0.75},
    "camera":     {1: 0.20, 2: 0.35, 3: 0.45, 4: 0.55, 5: 0.65},
    "drone":      {1: 0.30, 2: 0.45, 3: 0.55, 4: 0.65, 5: 0.75},
    "tablet":     {1: 0.30, 2: 0.45, 3: 0.60, 4: 0.70, 5: 0.80},
    "smartwatch": {1: 0.35, 2: 0.50, 3: 0.60, 4: 0.70, 5: 0.80},
    "other":      {1: 0.30, 2: 0.45, 3: 0.55, 4: 0.65, 5: 0.75},
}


def estimate_from_depreciation(
    new_price: float,
    category: str,
    year_released: int | None,
) -> float | None:
    if new_price <= 0:
        return None

    curve = DEPRECIATION_CURVES.get(category, DEPRECIATION_CURVES["other"])

    if year_released:
        years_old = datetime.now().year - year_released
    else:
        years_old = 2  # default assumption

    years_old = max(1, min(years_old, 5))
    depreciation_rate = curve[years_old]
    return round(new_price * (1 - depreciation_rate))
