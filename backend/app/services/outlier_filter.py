from collections import Counter
from statistics import median, quantiles


def median_value(values: list[float]) -> float:
    if not values:
        return 0.0

    return float(median(values))


def filter_iqr_outliers(values: list[float], multiplier: float = 1.5) -> tuple[list[float], list[float]]:
    if len(values) < 4:
        return values[:], []

    q1, _, q3 = quantiles(values, n=4, method="inclusive")
    iqr = q3 - q1
    lower_bound = q1 - (iqr * multiplier)
    upper_bound = q3 + (iqr * multiplier)

    kept = [value for value in values if lower_bound <= value <= upper_bound]
    removed = [value for value in values if value < lower_bound or value > upper_bound]
    return kept, removed


def median_absolute_deviation(values: list[float]) -> float:
    if not values:
        return 0.0

    midpoint = median_value(values)
    absolute_deviations = [abs(value - midpoint) for value in values]
    return float(median(absolute_deviations))


def filter_mad_outliers(values: list[float], threshold: float = 3.5) -> tuple[list[float], list[float]]:
    if len(values) < 5:
        return values[:], []

    midpoint = median_value(values)
    mad = median_absolute_deviation(values)
    if mad == 0:
        return values[:], []

    kept: list[float] = []
    removed: list[float] = []
    for value in values:
        modified_z_score = 0.6745 * (value - midpoint) / mad
        if abs(modified_z_score) > threshold:
            removed.append(value)
            continue

        kept.append(value)

    return kept, removed


def filter_price_outliers(values: list[float]) -> tuple[list[float], list[float]]:
    mad_kept, mad_removed = filter_mad_outliers(values)
    if mad_removed:
        return mad_kept, mad_removed

    return filter_iqr_outliers(values)


def filter_comparable_outliers(comparables: list[dict]) -> tuple[list[dict], list[dict]]:
    prices = [float(comparable["price"]) for comparable in comparables]
    kept_prices, removed_prices = filter_price_outliers(prices)

    kept_counter = Counter(kept_prices)
    removed_counter = Counter(removed_prices)

    kept: list[dict] = []
    removed: list[dict] = []

    for comparable in comparables:
        price = float(comparable["price"])
        if kept_counter[price] > 0:
            kept.append(comparable)
            kept_counter[price] -= 1
            continue

        if removed_counter[price] > 0:
            removed.append(comparable)
            removed_counter[price] -= 1
            continue

        kept.append(comparable)

    return kept, removed
