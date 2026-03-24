import logging
from ..models import (
    MarketListing,
    PricePoint,
    ReasoningStep,
    ValuationResponse,
    ValuationStatus,
    VisionResult,
)

logger = logging.getLogger(__name__)


def build_response(
    vision: VisionResult,
    pricing: dict,
    all_listings: list[MarketListing],
    price_history: list[PricePoint],
    lowest_new_price_6m: float | None,
    new_price_source: str | None,
    sources: list[str],
    debug: dict | None,
    debug_enabled: bool,
) -> ValuationResponse:
    warnings: list[str] = []
    reasoning: list[ReasoningStep] = []

    # Step 1: Identification
    id_desc = (
        f"Produkten identifierades som {vision.product_name} med "
        f"{vision.confidence:.0%} säkerhet baserat på bildanalys."
    )
    if vision.confidence < 0.5:
        id_desc += f" OBS: Låg säkerhet — {vision.raw_description}"
    reasoning.append(ReasoningStep(
        step="Identifiering",
        description=id_desc,
        confidence=vision.confidence,
        data_points=1,
    ))

    # Step 2: New price
    new_price = pricing.get("new_price")
    if new_price:
        price_desc = f"Nypris hittades till {new_price:,.0f} kr via {new_price_source or 'Google Shopping'}."
        if lowest_new_price_6m and lowest_new_price_6m < new_price:
            price_desc += f" Lägsta pris senaste 6 mån: {lowest_new_price_6m:,.0f} kr."
    else:
        price_desc = "Nypris kunde inte hittas. Estimat baseras enbart på andrahandsdata."
    reasoning.append(ReasoningStep(
        step="Nypris",
        description=price_desc,
        confidence=0.9 if new_price else 0.3,
        data_points=1 if new_price else 0,
    ))

    # Step 3: Market data
    sold_count = pricing.get("sold_count", 0)
    active_count = pricing.get("active_count", 0)
    total = sold_count + active_count
    src_list = pricing.get("sources_used", [])

    if total > 0:
        market_desc = f"Hittade {total} relevanta annonser: "
        parts = []
        if sold_count:
            parts.append(f"{sold_count} sålda på Tradera")
        if active_count:
            parts.append(f"{active_count} aktiva på {', '.join(src_list)}")
        market_desc += ", ".join(parts) + "."
    else:
        market_desc = "Inga andrahandsannonser hittades. Estimat baseras på värdeminskningsmodell."

    reasoning.append(ReasoningStep(
        step="Andrahandsdata",
        description=market_desc,
        confidence=min(total / 10, 1.0),
        data_points=total,
    ))

    # Step 4: Calculation
    estimated_value = pricing.get("estimated_value")
    value_range = pricing.get("value_range")
    confidence = pricing.get("confidence")
    depreciation_percent = pricing.get("depreciation_percent")

    if estimated_value:
        calc_desc = (
            f"Baserat på {total} datapunkter estimeras andrahandsvärdet till "
            f"{estimated_value:,.0f} kr"
        )
        if value_range:
            calc_desc += f" (spann: {value_range[0]:,.0f}–{value_range[1]:,.0f} kr)"
        if depreciation_percent is not None:
            calc_desc += f". Det motsvarar ca {depreciation_percent:.0f}% värdeminskning från nypris."
        else:
            calc_desc += "."
        if sold_count:
            calc_desc += " Sålda annonser viktas högre (1.5x) då de representerar faktiska transaktioner."
    else:
        calc_desc = "Kunde inte beräkna ett estimat med tillräcklig säkerhet."

    reasoning.append(ReasoningStep(
        step="Beräkning",
        description=calc_desc,
        confidence=confidence or 0.0,
        data_points=total,
    ))

    # Determine status + gating
    status = ValuationStatus.ok
    suppress_value = False

    if vision.confidence < 0.5:
        status = ValuationStatus.ambiguous_model
        suppress_value = True
        warnings.append(
            f"Produktidentifiering osäker ({vision.confidence:.0%}). "
            "Försök med en tydligare bild som visar modellnumret."
        )
    elif total == 0 and new_price is None:
        status = ValuationStatus.insufficient_evidence
        suppress_value = True
        warnings.append("Ingen marknadsdata eller nypris hittades. Kan inte estimera värde.")
    elif total == 0 and new_price is not None:
        status = ValuationStatus.estimated_from_depreciation
        warnings.append(
            "Inga andrahandsannonser hittades. Värdet estimeras från värdeminskningsmodell — "
            "osäkerheten är hög."
        )
    elif total < 3:
        status = ValuationStatus.degraded
        suppress_value = True
        warnings.append(f"Endast {total} jämförelseobjekt hittades. Kan inte ge ett tillförlitligt estimat.")
    elif confidence is not None and confidence < 0.3:
        status = ValuationStatus.degraded
        suppress_value = True
        warnings.append("Stor prisspridning bland jämförelseobjekten. Kan inte ge ett tillförlitligt estimat.")

    # Sanity checks — catch data pipeline errors that produce nonsense estimates
    if estimated_value is not None and not suppress_value:
        if new_price is not None and new_price > 0:
            if estimated_value >= new_price * 0.95:
                logger.warning(
                    f"Sanity fail: estimated_value ({estimated_value:.0f}) >= 95% of new_price ({new_price:.0f}) — "
                    "used price at or above new price is implausible"
                )
                status = ValuationStatus.degraded
                suppress_value = True
                warnings.append(
                    "Estimerat begagnatpris är nästan lika högt som nypris — "
                    "data verkar felaktig. Inget estimat visas."
                )
            elif estimated_value < new_price * 0.10:
                logger.warning(
                    f"Sanity fail: estimated_value ({estimated_value:.0f}) < 10% of new_price ({new_price:.0f}) — "
                    "suspiciously low, likely junk data in comparables"
                )
                status = ValuationStatus.degraded
                suppress_value = True
                warnings.append(
                    "Estimatet verkar orealistiskt lågt i förhållande till nypris — "
                    "data verkar felaktig. Inget estimat visas."
                )

    return ValuationResponse(
        status=status,
        product_name=vision.product_name,
        estimated_value=None if suppress_value else estimated_value,
        value_range=None if suppress_value else value_range,
        confidence=None if suppress_value else confidence,
        currency="SEK",
        new_price=new_price,
        new_price_source=new_price_source,
        price_history=price_history,
        lowest_new_price_6m=lowest_new_price_6m,
        depreciation_percent=None if suppress_value else depreciation_percent,
        market_listings=all_listings,
        comparables_used=total,
        reasoning=reasoning,
        warnings=warnings,
        sources=sources,
        debug=debug if debug_enabled else None,
    )
