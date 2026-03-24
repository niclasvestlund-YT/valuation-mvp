from collections import Counter
from statistics import median

from backend.app.core.config import settings
from backend.app.schemas.product_identification import ProductIdentificationResult
from backend.app.services.comparable_scoring import score_comparable_relevance
from backend.app.services.depreciation_rules import get_depreciation_range
from backend.app.services.market_service import MarketService
from backend.app.services.new_price_service import NewPriceService
from backend.app.services.pricing_service import MIN_RELEVANCE_SCORE, PricingService
from backend.app.services.vision_service import VisionService
from backend.app.utils.normalization import normalize_product_name

ABSOLUTE_IDENTIFICATION_CONFIDENCE_FLOOR = 0.72
AMBIGUOUS_IDENTIFICATION_CONFIDENCE_THRESHOLD = 0.90
AMBIGUOUS_NEW_PRICE_CONFIDENCE_FLOOR = 0.78
PRELIMINARY_ESTIMATE_CONFIDENCE_FLOOR = 0.86
PRELIMINARY_ESTIMATE_MIN_RELEVANT_SIGNALS = 1
PRELIMINARY_ESTIMATE_MIN_AVERAGE_RELEVANCE = 0.66
PRELIMINARY_ESTIMATE_MIN_DISCOVERY_RESULTS = 3
DEGRADED_WARNING = "Resultatet bygger på begränsat underlag"
DEGRADED_REASON = "valuation_pipeline_failure"
POSITIVE_RELEVANCE_REASONS = {
    "exact_model_match",
    "brand_match",
    "line_match",
    "variant_match",
    "sold_listing",
    "active_listing",
}
STATUS_REASON_LABELS = {
    "missing_brand_or_model": "Varumärke eller exakt modell är inte säkert bekräftad ännu.",
    "needs_more_images": "Fler eller tydligare bilder behövs innan marknadsunderlaget används.",
    "exact_model_confidence_too_low": "Exakt modell är fortfarande för osäker för en trygg värdering.",
    "multiple_plausible_models": "Flera rimliga modellkandidater finns fortfarande kvar.",
    "no_relevant_comparables": "Inga relevanta andrahandsannonser klarade relevansfiltren.",
    "not_enough_relevant_comparables": "För få relevanta andrahandsannonser överlevde filtreringen.",
    "average_relevance_too_low": "Jämförelseannonserna liknar målprodukten för dåligt.",
    "no_sold_comparables": "Det saknas tillräckligt starka sålda annonser.",
    "cannot_value_from_new_price_only": "Nypriskontexten räcker inte ensam för att värdera begagnatvärde.",
    "valuation_pipeline_failure": "Värderingsflödet misslyckades oväntat.",
    "unexpected_pricing_status": "Värderingslagret returnerade ett oväntat tillstånd.",
}
RELEVANCE_REASON_LABELS = {
    "missing_exact_model_match": "Exakt modell saknas i annonsrubriken",
    "matched_alternative_candidate_model": "Annonsen matchar en alternativ modell",
    "osmo_family_mismatch": "Annan Osmo-produktfamilj, till exempel Pocket i stället för Action",
    "osmo_generation_mismatch": "Annan generation eller version än målprodukten",
    "osmo_generation_missing_in_listing": "Annonsen saknar tydlig generationsangivelse",
    "osmo_generation_specific_for_broad_target": "Specifik generation mot en bredare målmodell",
    "osmo_variant_qualifier_mismatch": "Variant eller modellsuffix skiljer sig från målprodukten",
    "osmo_variant_specific_for_plain_target": "Specifik variant mot en enklare grundmodell",
    "bundle_variant_for_plain_target": "Bundle- eller combo-variant mot en grundmodell",
    "listing_bundle_mismatch": "Paketvariant som inte matchar målprodukten",
    "listing_accessory_mismatch": "Tillbehör i stället för huvudprodukt",
    "listing_for_parts": "Delar eller reservdelsannons",
    "listing_broken": "Trasig annons",
    "listing_defect": "Defekt annons",
    "listing_locked": "Låst enhet",
    "listing_empty_box": "Tom kartong",
    "listing_case_only": "Endast fodral eller case",
    "listing_charger_only": "Endast laddare",
    "listing_replacement_parts": "Reservdelar i stället för hel produkt",
    "listing_body_only": "Endast hus eller basenhet",
}


def is_manual_override(identification: ProductIdentificationResult) -> bool:
    return identification.source == "Manual override"


def build_ambiguity_reasons(
    identification: ProductIdentificationResult,
    confidence_floor: float = ABSOLUTE_IDENTIFICATION_CONFIDENCE_FLOOR,
    ambiguity_threshold: float = AMBIGUOUS_IDENTIFICATION_CONFIDENCE_THRESHOLD,
) -> list[str]:
    reasons: list[str] = []
    if not identification.brand or not identification.model:
        reasons.append("missing_brand_or_model")

    if identification.needs_more_images:
        reasons.append("needs_more_images")

    if is_manual_override(identification):
        return reasons

    candidate_models = identification.candidate_models or []
    if identification.confidence < confidence_floor:
        reasons.append("exact_model_confidence_too_low")

    if candidate_models and identification.confidence < ambiguity_threshold:
        reasons.append("multiple_plausible_models")

    return list(dict.fromkeys(reasons))


def build_ambiguity_warnings(reasons: list[str]) -> list[str]:
    warnings: list[str] = []
    if any(reason in reasons for reason in ["missing_brand_or_model", "needs_more_images", "exact_model_confidence_too_low"]):
        warnings.append("Vi behöver tydligare bilder")

    if "multiple_plausible_models" in reasons:
        warnings.append("Vi hittade flera möjliga modeller")

    return warnings


def build_sources(
    *,
    identification_source: str,
    market_comparables: list[dict] | None = None,
    new_price_data: dict | None = None,
) -> list[str]:
    sources = [identification_source]

    for comparable in market_comparables or []:
        source = str(comparable.get("source") or "").strip()
        if source:
            sources.append(source)

    for source_record in (new_price_data or {}).get("sources", []):
        source = str(source_record.get("source") or "").strip()
        if source:
            sources.append(source)

    return list(dict.fromkeys(sources))


def build_market_data(
    *,
    market_comparables: list[dict] | None,
    new_price_data: dict | None,
    pricing_result: dict | None = None,
) -> dict:
    valuation = (pricing_result or {}).get("valuation") or {}
    evidence = (pricing_result or {}).get("evidence")
    currency = valuation.get("currency") or (new_price_data or {}).get("currency")

    return {
        "comparables": market_comparables or [],
        "new_price": new_price_data,
        "pricing_evidence": evidence,
        "currency": currency,
    }


def _display_exactness_confidence(comparable: dict) -> float:
    raw = comparable.get("raw") or {}
    metadata = raw.get("_fallback_metadata") or {}
    value = metadata.get("exactness_confidence")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def sort_market_comparables_for_display(
    *,
    product_identification: ProductIdentificationResult,
    market_comparables: list[dict] | None,
) -> list[dict]:
    comparables = list(market_comparables or [])

    def sort_key(comparable: dict) -> tuple[float, float, int, float]:
        score_result = score_comparable_relevance(comparable, product_identification)
        sold_boost = 1 if comparable.get("listing_type") == "sold" or comparable.get("status") == "completed" else 0
        return (
            0.0 if score_result.hard_reject else score_result.score,
            _display_exactness_confidence(comparable),
            sold_boost,
            float(comparable.get("price") or 0.0),
        )

    return sorted(comparables, key=sort_key, reverse=True)


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").lower().replace("-", " ").split())


def should_fetch_new_price_for_ambiguous(identification: ProductIdentificationResult, reasons: list[str]) -> bool:
    if not identification.brand or not identification.model:
        return False

    if is_manual_override(identification):
        return True

    if identification.confidence < AMBIGUOUS_NEW_PRICE_CONFIDENCE_FLOOR:
        return False

    if "multiple_plausible_models" in reasons:
        return False

    return True


def _has_bid_activity(comparable: dict) -> bool:
    raw = comparable.get("raw") or {}
    try:
        bid_count = int(raw.get("BidCount") or 0)
    except (TypeError, ValueError):
        bid_count = 0

    return str(raw.get("HasBids") or "").lower() == "true" or bid_count > 0


def _is_accessory_like_comparable(comparable: dict) -> bool:
    text = _normalize_text(f"{comparable.get('title') or ''} {comparable.get('condition_hint') or ''}")
    return any(
        keyword in text
        for keyword in [
            "case",
            "fodral",
            "charger",
            "laddare",
            "cable",
            "kabel",
            "battery",
            "batteri",
            "mount",
            "faste",
            "fäste",
            "strap",
            "remote",
            "cover",
            "housing",
            "adapter",
        ]
    )


def _is_bundle_like_comparable(comparable: dict) -> bool:
    text = _normalize_text(comparable.get("title") or "")
    return any(
        keyword in text
        for keyword in [
            "combo",
            "bundle",
            "paket",
            "kit",
            "adventure",
            "creator",
            "sandisk",
            "mikrofon",
            "microphone",
            "selfie",
            "battery",
            "batteri",
            "minneskort",
            "micro sd",
            "microsd",
        ]
    )


def build_market_snapshot(
    *,
    market_lookup_attempted: bool,
    market_comparables: list[dict] | None = None,
    pricing_result: dict | None = None,
) -> dict:
    comparables = market_comparables or []
    evidence = (pricing_result or {}).get("evidence") or {}

    sold_count = 0
    active_count = 0
    bidding_count = 0
    accessory_like_count = 0
    bundle_like_count = 0

    for comparable in comparables:
        if comparable.get("listing_type") == "sold" or comparable.get("status") == "completed":
            sold_count += 1
        else:
            active_count += 1

        if _has_bid_activity(comparable):
            bidding_count += 1

        if _is_accessory_like_comparable(comparable):
            accessory_like_count += 1

        if _is_bundle_like_comparable(comparable):
            bundle_like_count += 1

    return {
        "fetched_count": len(comparables) if market_lookup_attempted else 0,
        "relevant_count": int(evidence.get("comparable_count") or 0),
        "sold_count": sold_count if market_lookup_attempted else 0,
        "active_count": active_count if market_lookup_attempted else 0,
        "bidding_count": bidding_count if market_lookup_attempted else 0,
        "accessory_like_count": accessory_like_count if market_lookup_attempted else 0,
        "bundle_like_count": bundle_like_count if market_lookup_attempted else 0,
    }


def _extract_new_price_anchor(
    new_price_data: dict | None,
    *,
    allow_source_fallback: bool = False,
) -> float | None:
    if not new_price_data:
        return None

    value = new_price_data.get("estimated_new_price")
    if value is not None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = None

        if parsed and parsed > 0:
            return parsed

    if not allow_source_fallback:
        return None

    source_prices: list[float] = []
    for source in new_price_data.get("sources", []):
        try:
            source_price = float(source.get("price"))
        except (TypeError, ValueError, AttributeError):
            continue
        if source_price > 0:
            source_prices.append(source_price)

    if not source_prices:
        return None

    return min(source_prices)


def build_preliminary_estimate(
    *,
    product_identification: ProductIdentificationResult,
    market_comparables: list[dict],
    new_price_data: dict | None,
    pricing_result: dict | None,
) -> dict | None:
    if is_manual_override(product_identification):
        identification_confidence = 0.99
    else:
        identification_confidence = float(product_identification.confidence or 0.0)

    if identification_confidence < PRELIMINARY_ESTIMATE_CONFIDENCE_FLOOR:
        return None

    if product_identification.needs_more_images:
        return None

    if len(product_identification.candidate_models or []) > 1:
        return None

    new_price_anchor = _extract_new_price_anchor(new_price_data, allow_source_fallback=False)
    if not new_price_anchor:
        return None

    pricing_reasons = set((pricing_result or {}).get("reasons") or [])
    if {"no_relevant_comparables", "average_relevance_too_low"} & pricing_reasons:
        return None

    scored_signals: list[dict] = []
    for comparable in market_comparables:
        score_result = score_comparable_relevance(comparable, product_identification)
        if score_result.hard_reject or score_result.score < MIN_RELEVANCE_SCORE:
            continue

        scored_signals.append({
            **comparable,
            "relevance_score": score_result.score,
        })

    if len(scored_signals) < PRELIMINARY_ESTIMATE_MIN_RELEVANT_SIGNALS:
        return None

    average_relevance = sum(signal["relevance_score"] for signal in scored_signals) / len(scored_signals)
    if average_relevance < PRELIMINARY_ESTIMATE_MIN_AVERAGE_RELEVANCE:
        return None

    if len(market_comparables) < PRELIMINARY_ESTIMATE_MIN_DISCOVERY_RESULTS and len(scored_signals) < 2:
        return None

    market_prices = [float(signal["price"]) for signal in scored_signals]
    market_signal_estimate = float(median(market_prices))
    depreciation_low, depreciation_high = get_depreciation_range(
        getattr(product_identification, "category", None),
        condition=None,
    )
    anchor_midpoint = new_price_anchor * ((depreciation_low + depreciation_high) / 2)
    blended_estimate = (market_signal_estimate * 0.75) + (anchor_midpoint * 0.25)
    bounded_estimate = max(
        new_price_anchor * depreciation_low,
        min(blended_estimate, new_price_anchor * depreciation_high),
    )

    sold_signal_count = sum(1 for signal in scored_signals if signal.get("listing_type") == "sold")
    active_signal_count = sum(1 for signal in scored_signals if signal.get("listing_type") != "sold")
    confidence = 0.28 + min(len(scored_signals), 3) * 0.05 + min(average_relevance, 1.0) * 0.12
    confidence = min(0.55, round(confidence, 2))

    return {
        "estimate": int(round(bounded_estimate)),
        "currency": str((new_price_data or {}).get("currency") or "SEK"),
        "confidence": confidence,
        "basis_summary": (
            f"Grov uppskattning baserad på {len(scored_signals)} relevant marknadssignal"
            f"{'' if len(scored_signals) == 1 else 'er'} och nypriskontext. "
            "Det här är inte ett fullständigt begagnatvärde."
        ),
        "supporting_signal_count": len(scored_signals),
        "active_signal_count": active_signal_count,
        "sold_signal_count": sold_signal_count,
        "new_price_anchor": int(round(new_price_anchor)),
    }


def _format_ranked_reasons(counter: Counter[str], *, limit: int = 3) -> list[str]:
    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    formatted: list[str] = []
    for reason, count in ranked[:limit]:
        label = RELEVANCE_REASON_LABELS.get(reason) or STATUS_REASON_LABELS.get(reason) or reason.replace("_", " ")
        formatted.append(f"{label} ({count})")
    return formatted


def build_debug_summary(
    *,
    market_lookup_attempted: bool,
    status_reasons: list[str],
    market_comparables: list[dict] | None = None,
    pricing_result: dict | None = None,
    product_identification: ProductIdentificationResult | None = None,
) -> dict:
    pricing_evidence = (pricing_result or {}).get("evidence") or {}
    total_comparables = len(market_comparables or []) if market_lookup_attempted else 0

    rejection_reasons: Counter[str] = Counter()
    downgrade_reasons: Counter[str] = Counter()
    if market_lookup_attempted and market_comparables and product_identification is not None:
        for comparable in market_comparables:
            score_result = score_comparable_relevance(comparable, product_identification)
            unique_reasons = list(dict.fromkeys(score_result.reasons))

            if score_result.hard_reject:
                rejection_reasons.update(unique_reasons)
                continue

            negative_reasons = [
                reason for reason in unique_reasons
                if reason not in POSITIVE_RELEVANCE_REASONS
            ]
            if score_result.score < MIN_RELEVANCE_SCORE:
                downgrade_reasons.update(negative_reasons or ["missing_exact_model_match"])
            elif negative_reasons:
                downgrade_reasons.update(negative_reasons)

    return {
        "market_lookup_attempted": market_lookup_attempted,
        "total_comparables_fetched": total_comparables,
        "relevant_comparables_kept": pricing_evidence.get("comparable_count"),
        "sold_comparables_kept": pricing_evidence.get("sold_comparable_count"),
        "average_relevance": pricing_evidence.get("average_relevance"),
        "status_reasons": [
            STATUS_REASON_LABELS.get(reason, reason.replace("_", " ").capitalize())
            for reason in status_reasons
        ],
        "top_rejection_reasons": _format_ranked_reasons(rejection_reasons),
        "top_downgrade_reasons": _format_ranked_reasons(downgrade_reasons),
    }


class ValueEngine:
    def __init__(
        self,
        vision_service: VisionService | None = None,
        market_service: MarketService | None = None,
        new_price_service: NewPriceService | None = None,
        pricing_service: PricingService | None = None,
    ) -> None:
        self.settings = settings
        self.is_mock_mode = settings.is_mock_mode
        self.vision_service = vision_service or VisionService()
        self.market_service = market_service or MarketService()
        self.new_price_service = new_price_service or NewPriceService()
        self.pricing_service = pricing_service or PricingService()

    def value_item(
        self,
        images: list[str] | None = None,
        image: str | None = None,
        brand: str | None = None,
        model: str | None = None,
    ) -> dict:
        market_comparables: list[dict] = []
        new_price_data: dict | None = None
        if brand and model:
            vision_result = ProductIdentificationResult(
                brand=brand,
                line=None,
                model=model,
                category=None,
                variant=None,
                candidate_models=[],
                confidence=0.99,
                reasoning_summary="The user provided a manual brand and model override.",
                needs_more_images=False,
                requested_additional_angles=[],
                source="Manual override",
                request_id="manual_override",
            )
        else:
            vision_result = self.vision_service.detect_product(images=images, image=image)

        confidence = float(vision_result.confidence)
        if brand and model:
            confidence = 0.99

        resolved_identification = vision_result.model_copy(
            update={
                "brand": normalize_product_name(brand) or normalize_product_name(vision_result.brand),
                "model": normalize_product_name(model) or normalize_product_name(vision_result.model),
                "confidence": round(confidence, 2),
            }
        )

        ambiguity_reasons = build_ambiguity_reasons(resolved_identification)
        if ambiguity_reasons:
            ambiguity_warnings = build_ambiguity_warnings(ambiguity_reasons)
            if should_fetch_new_price_for_ambiguous(resolved_identification, ambiguity_reasons):
                try:
                    new_price_data = self.new_price_service.get_new_price(
                        resolved_identification.brand or "",
                        resolved_identification.model or "",
                        category=resolved_identification.category,
                    )
                except Exception:
                    new_price_data = None
                    ambiguity_warnings = list(dict.fromkeys([
                        *ambiguity_warnings,
                        "Nypriskontext kunde inte hämtas i det här försöket",
                    ]))

            return {
                "status": "ambiguous_model",
                "data": {
                    "brand": resolved_identification.brand,
                    "line": resolved_identification.line,
                    "model": resolved_identification.model,
                    "category": resolved_identification.category,
                    "variant": resolved_identification.variant,
                    "candidate_models": resolved_identification.candidate_models,
                    "confidence": resolved_identification.confidence,
                    "reasoning_summary": resolved_identification.reasoning_summary,
                    "needs_more_images": True,
                    "requested_additional_angles": resolved_identification.requested_additional_angles,
                    "price": None,
                    "valuation": None,
                    "market_data": build_market_data(
                        market_comparables=[],
                        new_price_data=new_price_data,
                        pricing_result=None,
                    ),
                    "sources": build_sources(
                        identification_source=resolved_identification.source,
                        market_comparables=[],
                        new_price_data=new_price_data,
                    ),
                },
                "warnings": ambiguity_warnings,
                "reasons": ambiguity_reasons,
                "market_snapshot": build_market_snapshot(
                    market_lookup_attempted=False,
                    market_comparables=[],
                    pricing_result=None,
                ),
                "debug_summary": build_debug_summary(
                    market_lookup_attempted=False,
                    status_reasons=ambiguity_reasons,
                    market_comparables=[],
                    pricing_result=None,
                    product_identification=resolved_identification,
                ),
                "debug_id": resolved_identification.request_id,
            }

        resolved_brand = resolved_identification.brand or ""
        resolved_model = resolved_identification.model or ""
        try:
            market_comparables = self.market_service.get_comparables(
                resolved_brand,
                resolved_model,
                category=resolved_identification.category,
            )
            new_price_data = self.new_price_service.get_new_price(
                resolved_brand,
                resolved_model,
                category=resolved_identification.category,
            )

            pricing_result = self.pricing_service.calculate_valuation(
                product_identification=resolved_identification,
                used_market_comparables=market_comparables,
                new_price_estimate=new_price_data,
                condition=None,
            )
        except Exception:
            display_market_comparables = sort_market_comparables_for_display(
                product_identification=resolved_identification,
                market_comparables=market_comparables,
            )
            return {
                "status": "degraded",
                "data": {
                    "brand": resolved_brand,
                    "line": resolved_identification.line,
                    "model": resolved_model,
                    "category": resolved_identification.category,
                    "variant": resolved_identification.variant,
                    "candidate_models": resolved_identification.candidate_models,
                    "confidence": resolved_identification.confidence,
                    "reasoning_summary": resolved_identification.reasoning_summary,
                    "needs_more_images": resolved_identification.needs_more_images,
                    "requested_additional_angles": resolved_identification.requested_additional_angles,
                    "price": None,
                    "valuation": None,
                    "market_data": None,
                    "sources": [resolved_identification.source],
                },
                "warnings": [
                    DEGRADED_WARNING,
                    "Valuation pipeline unavailable",
                ],
                "reasons": [DEGRADED_REASON],
                "market_snapshot": build_market_snapshot(
                    market_lookup_attempted=True,
                    market_comparables=display_market_comparables,
                    pricing_result=None,
                ),
                "debug_summary": build_debug_summary(
                    market_lookup_attempted=True,
                    status_reasons=[DEGRADED_REASON],
                    market_comparables=display_market_comparables,
                    pricing_result=None,
                    product_identification=resolved_identification,
                ),
                "debug_id": resolved_identification.request_id,
            }

        display_market_comparables = sort_market_comparables_for_display(
            product_identification=resolved_identification,
            market_comparables=market_comparables,
        )
        sources = build_sources(
            identification_source=resolved_identification.source,
            market_comparables=display_market_comparables,
            new_price_data=new_price_data,
        )
        preliminary_estimate = build_preliminary_estimate(
            product_identification=resolved_identification,
            market_comparables=market_comparables,
            new_price_data=new_price_data,
            pricing_result=pricing_result,
        )
        if pricing_result.get("status") == "insufficient_evidence":
            warnings = list(pricing_result.get("warnings", []))
            if preliminary_estimate:
                warnings = list(dict.fromkeys([
                    "Det här är en grov uppskattning, inte ett fullständigt begagnatvärde",
                    *warnings,
                ]))
            return {
                "status": "insufficient_evidence",
                "data": {
                    "brand": resolved_brand,
                    "line": resolved_identification.line,
                    "model": resolved_model,
                    "category": resolved_identification.category,
                    "variant": resolved_identification.variant,
                    "candidate_models": resolved_identification.candidate_models,
                    "confidence": resolved_identification.confidence,
                    "reasoning_summary": resolved_identification.reasoning_summary,
                    "needs_more_images": resolved_identification.needs_more_images,
                    "requested_additional_angles": resolved_identification.requested_additional_angles,
                    "price": None,
                    "valuation": None,
                    "preliminary_estimate": preliminary_estimate,
                    "market_data": build_market_data(
                        market_comparables=display_market_comparables,
                        new_price_data=new_price_data,
                        pricing_result=pricing_result,
                    ),
                    "sources": sources,
                },
                "warnings": warnings,
                "reasons": pricing_result.get("reasons", []),
                "market_snapshot": build_market_snapshot(
                    market_lookup_attempted=True,
                    market_comparables=display_market_comparables,
                    pricing_result=pricing_result,
                ),
                "debug_summary": build_debug_summary(
                    market_lookup_attempted=True,
                    status_reasons=pricing_result.get("reasons", []),
                    market_comparables=display_market_comparables,
                    pricing_result=pricing_result,
                    product_identification=resolved_identification,
                ),
                "debug_id": resolved_identification.request_id,
            }

        if pricing_result.get("status") != "ok":
            return {
                "status": "degraded",
                "data": {
                    "brand": resolved_brand,
                    "line": resolved_identification.line,
                    "model": resolved_model,
                    "category": resolved_identification.category,
                    "variant": resolved_identification.variant,
                    "candidate_models": resolved_identification.candidate_models,
                    "confidence": resolved_identification.confidence,
                    "reasoning_summary": resolved_identification.reasoning_summary,
                    "needs_more_images": resolved_identification.needs_more_images,
                    "requested_additional_angles": resolved_identification.requested_additional_angles,
                    "price": None,
                    "valuation": None,
                    "preliminary_estimate": None,
                    "market_data": build_market_data(
                        market_comparables=display_market_comparables,
                        new_price_data=new_price_data,
                        pricing_result=pricing_result,
                    ),
                    "sources": sources,
                },
                "warnings": [
                    DEGRADED_WARNING,
                    "Unexpected valuation status returned",
                ],
                "reasons": ["unexpected_pricing_status"],
                "market_snapshot": build_market_snapshot(
                    market_lookup_attempted=True,
                    market_comparables=display_market_comparables,
                    pricing_result=pricing_result,
                ),
                "debug_summary": build_debug_summary(
                    market_lookup_attempted=True,
                    status_reasons=["unexpected_pricing_status"],
                    market_comparables=display_market_comparables,
                    pricing_result=pricing_result,
                    product_identification=resolved_identification,
                ),
                "debug_id": resolved_identification.request_id,
            }

        valuation = pricing_result["valuation"]

        return {
            "status": "ok",
            "data": {
                "brand": resolved_brand,
                "line": resolved_identification.line,
                "model": resolved_model,
                "category": resolved_identification.category,
                "variant": resolved_identification.variant,
                "candidate_models": resolved_identification.candidate_models,
                "confidence": resolved_identification.confidence,
                "reasoning_summary": resolved_identification.reasoning_summary,
                "needs_more_images": resolved_identification.needs_more_images,
                "requested_additional_angles": resolved_identification.requested_additional_angles,
                "price": valuation["fair_estimate"],
                "valuation": valuation,
                "preliminary_estimate": None,
                "market_data": build_market_data(
                    market_comparables=display_market_comparables,
                    new_price_data=new_price_data,
                    pricing_result=pricing_result,
                ),
                "sources": sources,
            },
            "warnings": pricing_result.get("warnings", []),
            "reasons": pricing_result.get("reasons", []),
            "market_snapshot": build_market_snapshot(
                market_lookup_attempted=True,
                market_comparables=display_market_comparables,
                pricing_result=pricing_result,
            ),
            "debug_summary": build_debug_summary(
                market_lookup_attempted=True,
                status_reasons=pricing_result.get("reasons", []),
                market_comparables=display_market_comparables,
                pricing_result=pricing_result,
                product_identification=resolved_identification,
            ),
            "debug_id": resolved_identification.request_id,
        }
