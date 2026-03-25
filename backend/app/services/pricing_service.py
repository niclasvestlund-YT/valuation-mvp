from statistics import mean

from backend.app.services.comparable_scoring import listing_weight, score_comparable_relevance
from backend.app.services.depreciation_rules import get_depreciation_range
from backend.app.services.outlier_filter import filter_comparable_outliers

MIN_RELEVANCE_SCORE = 0.55
MIN_RELEVANT_COMPARABLES = 3
MIN_AVERAGE_RELEVANCE = 0.65
MIN_SOLD_COMPARABLES = 0  # Blocket/Tradera only expose active listings; active prices are valid market data

BASE_PRICING_CONFIDENCE = 0.2
MAX_PRICING_CONFIDENCE = 0.95
LOW_IDENTIFICATION_CONFIDENCE_CAP = 0.68
AMBIGUOUS_IDENTIFICATION_CONFIDENCE_CAP = 0.78
MULTI_CANDIDATE_CONFIDENCE_CAP = 0.68
SINGLE_CANDIDATE_CONFIDENCE_CAP = 0.78

INSUFFICIENT_EVIDENCE_WARNING = "Underlaget från andrahandsmarknaden räcker inte för en trovärdig värdering"


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def weighted_median(values_and_weights: list[tuple[float, float]]) -> float:
    if not values_and_weights:
        return 0.0

    sorted_values = sorted(values_and_weights, key=lambda item: item[0])
    total_weight = sum(weight for _, weight in sorted_values)
    running_weight = 0.0

    for value, weight in sorted_values:
        running_weight += weight
        if running_weight >= total_weight / 2:
            return float(value)

    return float(sorted_values[-1][0])


def extract_new_price_anchor(new_price_estimate: dict | None) -> float | None:
    if not new_price_estimate:
        return None

    value = new_price_estimate.get("estimated_new_price")
    if value is None:
        return None

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    return parsed if parsed > 0 else None


def select_currency(comparables: list[dict], new_price_estimate: dict | None) -> str:
    if new_price_estimate and new_price_estimate.get("currency"):
        return str(new_price_estimate["currency"])

    currencies = [str(comparable.get("currency") or "").strip() for comparable in comparables if comparable.get("currency")]
    if not currencies:
        return "SEK"

    ranked = sorted(
        {currency: currencies.count(currency) for currency in set(currencies)}.items(),
        key=lambda item: (-item[1], item[0]),
    )
    return ranked[0][0]


def build_pricing_warnings(reasons: list[str]) -> list[str]:
    if not reasons:
        return []

    warning_map = {
        "no_relevant_comparables": "Vi kunde inte hitta relevanta jämförelseannonser",
        "not_enough_relevant_comparables": "För få starka jämförelseannonser återstod",
        "average_relevance_too_low": "Jämförelseannonserna liknar produkten för dåligt",
        "no_sold_comparables": "Vi behöver sålda annonser för att förankra ett trovärdigt begagnatvärde",
        "cannot_value_from_new_price_only": "Nypris ensam räcker inte för att värdera en begagnad produkt",
    }

    warnings = [INSUFFICIENT_EVIDENCE_WARNING]
    for reason in reasons:
        message = warning_map.get(reason)
        if message and message not in warnings:
            warnings.append(message)
    return warnings


class PricingService:
    def calculate_valuation(
        self,
        product_identification,
        used_market_comparables: list[dict],
        new_price_estimate: dict | None = None,
        condition: str | None = None,
    ) -> dict:
        scored_comparables = self._score_comparables(
            used_market_comparables=used_market_comparables,
            product_identification=product_identification,
        )
        filtered_comparables, removed_outliers = filter_comparable_outliers(scored_comparables)
        working_comparables = filtered_comparables or scored_comparables

        sold_count = sum(1 for comparable in working_comparables if comparable.get("listing_type") == "sold")
        active_count = sum(1 for comparable in working_comparables if comparable.get("listing_type") != "sold")
        average_relevance = (
            mean([float(comparable["relevance_score"]) for comparable in working_comparables])
            if working_comparables
            else 0.0
        )
        outlier_ratio = (
            round(len(removed_outliers) / len(scored_comparables), 2)
            if scored_comparables
            else 0.0
        )
        new_price_anchor = extract_new_price_anchor(new_price_estimate)

        evidence = {
            "comparable_count": len(working_comparables),
            "sold_comparable_count": sold_count,
            "active_comparable_count": active_count,
            "average_relevance": round(average_relevance, 2),
            "outlier_ratio": outlier_ratio,
            "scored_comparable_count": len(scored_comparables),
            "used_new_price_anchor": bool(new_price_anchor),
        }

        reasons = self._pricing_gate_reasons(
            comparables=working_comparables,
            average_relevance=average_relevance,
            sold_count=sold_count,
            has_new_price_anchor=bool(new_price_anchor),
        )
        if reasons:
            return {
                "status": "insufficient_evidence",
                "valuation": None,
                "warnings": build_pricing_warnings(reasons),
                "reasons": reasons,
                "evidence": evidence,
            }

        weighted_points = [
            (float(comparable["price"]), float(comparable["weight"])) for comparable in working_comparables
        ]
        fair_estimate = weighted_median(weighted_points)
        comparable_prices = [float(comparable["price"]) for comparable in working_comparables]
        low_estimate = min(comparable_prices)
        high_estimate = max(comparable_prices)
        currency = select_currency(working_comparables, new_price_estimate)

        if new_price_anchor:
            depreciation_low, depreciation_high = get_depreciation_range(
                getattr(product_identification, "category", None),
                condition=condition,
            )
            lower_bound = new_price_anchor * depreciation_low
            upper_bound = new_price_anchor * depreciation_high
            low_estimate = clamp(low_estimate, lower_bound, upper_bound)
            fair_estimate = clamp(fair_estimate, lower_bound, upper_bound)
            high_estimate = clamp(high_estimate, lower_bound, upper_bound)

        if low_estimate > fair_estimate:
            low_estimate = fair_estimate
        if high_estimate < fair_estimate:
            high_estimate = fair_estimate

        confidence = self._confidence_score(
            product_identification=product_identification,
            comparables=working_comparables,
            removed_outliers=removed_outliers,
            has_new_price_anchor=bool(new_price_anchor),
        )

        evidence_summary = (
            f"Used {len(working_comparables)} relevant comparables "
            f"({sold_count} sold, {active_count} active) with average relevance "
            f"{average_relevance:.2f}. Removed {len(removed_outliers)} outliers."
        )
        if new_price_anchor:
            evidence_summary += " A new-price anchor was used only as a sanity constraint."

        valuation_method = "relevance_weighted_median_with_robust_outlier_filter"
        if new_price_anchor:
            valuation_method += "_and_new_price_constraint"

        return {
            "status": "ok",
            "valuation": {
                "low_estimate": int(round(low_estimate)),
                "fair_estimate": int(round(fair_estimate)),
                "high_estimate": int(round(high_estimate)),
                "confidence": confidence,
                "currency": currency,
                "evidence_summary": evidence_summary,
                "valuation_method": valuation_method,
                "comparable_count": len(working_comparables),
                "source_breakdown": {
                    "sold_listings": sold_count,
                    "active_listings": active_count,
                    "outliers_removed": len(removed_outliers),
                    "used_new_price": bool(new_price_anchor),
                },
            },
            "warnings": [],
            "reasons": [],
            "evidence": {
                **evidence,
                "pricing_confidence": confidence,
            },
        }

    def _score_comparables(
        self,
        *,
        used_market_comparables: list[dict],
        product_identification,
    ) -> list[dict]:
        scored_comparables = []
        for comparable in used_market_comparables:
            score_result = score_comparable_relevance(comparable, product_identification)
            if score_result.hard_reject:
                continue
            if score_result.score < MIN_RELEVANCE_SCORE:
                continue

            scored_comparables.append(
                {
                    **comparable,
                    "relevance_score": score_result.score,
                    "relevance_reasons": score_result.reasons,
                    "hard_reject": score_result.hard_reject,
                    "weight": round(score_result.score * listing_weight(comparable), 3),
                }
            )

        return scored_comparables

    def _pricing_gate_reasons(
        self,
        *,
        comparables: list[dict],
        average_relevance: float,
        sold_count: int,
        has_new_price_anchor: bool,
    ) -> list[str]:
        reasons: list[str] = []

        if not comparables:
            reasons.append("no_relevant_comparables")
            if has_new_price_anchor:
                reasons.append("cannot_value_from_new_price_only")
            return reasons

        if len(comparables) < MIN_RELEVANT_COMPARABLES:
            reasons.append("not_enough_relevant_comparables")

        if average_relevance < MIN_AVERAGE_RELEVANCE:
            reasons.append("average_relevance_too_low")

        return reasons

    def _confidence_score(
        self,
        product_identification,
        comparables: list[dict],
        removed_outliers: list[dict],
        has_new_price_anchor: bool,
    ) -> float:
        comparable_count = len(comparables)
        average_relevance = (
            mean([float(comparable["relevance_score"]) for comparable in comparables]) if comparables else 0.0
        )
        sold_count = sum(1 for comparable in comparables if comparable.get("listing_type") == "sold")
        sold_ratio = sold_count / comparable_count if comparable_count else 0.0
        total_considered = comparable_count + len(removed_outliers)
        outlier_ratio = len(removed_outliers) / total_considered if total_considered else 0.0

        score = BASE_PRICING_CONFIDENCE
        score += min(comparable_count, 5) * 0.08
        score += average_relevance * 0.2
        score += sold_ratio * 0.12
        if has_new_price_anchor:
            score += 0.04
        score -= outlier_ratio * 0.18

        identification_confidence = float(getattr(product_identification, "confidence", 1.0) or 1.0)
        candidate_models = getattr(product_identification, "candidate_models", []) or []
        is_manual_override = getattr(product_identification, "source", "") == "Manual override"

        confidence_cap = MAX_PRICING_CONFIDENCE
        if not is_manual_override:
            if identification_confidence < 0.72:
                confidence_cap = min(confidence_cap, LOW_IDENTIFICATION_CONFIDENCE_CAP)
            elif identification_confidence < 0.85:
                confidence_cap = min(confidence_cap, AMBIGUOUS_IDENTIFICATION_CONFIDENCE_CAP)

            if len(candidate_models) > 1:
                confidence_cap = min(confidence_cap, MULTI_CANDIDATE_CONFIDENCE_CAP)
            elif len(candidate_models) == 1:
                confidence_cap = min(confidence_cap, SINGLE_CANDIDATE_CONFIDENCE_CAP)

        return round(clamp(score, 0.15, confidence_cap), 2)
