import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Body
from pydantic import BaseModel, Field

from backend.app.core.value_engine import ValueEngine
from backend.app.db.crud import save_feedback, save_price_snapshot, save_valuation
from backend.app.schemas.product_identification import VisionServiceError
from backend.app.utils.error_reporting import (
    attach_error_fields,
    build_input_summary,
    infer_error_stage_from_exception,
    infer_error_stage_from_payload,
    new_debug_id,
    record_error_artifacts,
)
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()
value_engine = ValueEngine()

STATUS_TITLES = {
    "ok": "Begagnatvärde uppskattat",
    "ambiguous_model": "Fler bilder behövs",
    "insufficient_evidence": "För svagt marknadsunderlag",
    "degraded": "Tillfälligt systemproblem",
    "error": "Kunde inte värdera enheten",
}

STATUS_MESSAGES = {
    "ok": "Det här är en uppskattning av andrahandsvärdet, baserad på jämförbara annonser och tydligt underlag.",
    "ambiguous_model": "Vi behöver säkrare produktidentifiering innan vi visar ett begagnatvärde.",
    "insufficient_evidence": "Produkten kan vara rätt identifierad, men underlaget från andrahandsmarknaden räcker inte för en trovärdig värdering.",
    "degraded": "Det här är ett tillfälligt systemproblem, inte ett tillförlitligt värderingsresultat.",
    "error": "Begäran kunde inte slutföras.",
}

REASON_DETAILS = {
    "missing_brand_or_model": "Exakt varumärke eller modell kunde inte bekräftas.",
    "needs_more_images": "Bilderna visar inte tillräckligt många detaljer för säker identifiering.",
    "exact_model_confidence_too_low": "Vi är ännu inte tillräckligt säkra på den exakta modellen.",
    "multiple_plausible_models": "Det finns fortfarande flera rimliga modellkandidater.",
    "no_relevant_comparables": "Inga relevanta andrahandsannonser klarade relevansfiltren.",
    "not_enough_relevant_comparables": "För få relevanta andrahandsannonser överlevde filtreringen.",
    "average_relevance_too_low": "Jämförelseannonserna matchade produkten för svagt.",
    "no_sold_comparables": "Det saknas tillräckligt starka sålda annonser för att förankra ett begagnatvärde.",
    "cannot_value_from_new_price_only": "Nypris kan bara användas som stödkontext, inte som ensam grund för begagnatvärde.",
    "valuation_pipeline_failure": "Värderingsflödet misslyckades oväntat.",
    "unexpected_pricing_status": "Värderingslagret returnerade ett oväntat tillstånd.",
    "value_endpoint_failure": "API:t misslyckades innan ett tillförlitligt värderingssvar kunde skickas.",
}


class ValueRequest(BaseModel):
    image: str | None = None
    images: list[str] | None = None
    filename: str | None = None
    brand: str | None = None
    model: str | None = None
    category: str | None = None
    condition: str | None = None  # "excellent" | "good" | "fair" | "poor"


class SourceBreakdown(BaseModel):
    sold_listings: int = 0
    active_listings: int = 0
    outliers_removed: int = 0
    used_new_price: bool = False


class ValuationPayload(BaseModel):
    low_estimate: int
    fair_estimate: int
    high_estimate: int
    confidence: float
    currency: str
    evidence_summary: str
    valuation_method: str
    comparable_count: int
    source_breakdown: SourceBreakdown


class PreliminaryEstimatePayload(BaseModel):
    estimate: int
    currency: str
    confidence: float
    basis_summary: str
    supporting_signal_count: int
    active_signal_count: int = 0
    sold_signal_count: int = 0
    new_price_anchor: int | None = None


class ValueData(BaseModel):
    brand: str | None = None
    line: str | None = None
    model: str | None = None
    category: str | None = None
    variant: str | None = None
    candidate_models: list[str] = Field(default_factory=list)
    confidence: float | None = None
    reasoning_summary: str | None = None
    needs_more_images: bool = False
    requested_additional_angles: list[str] = Field(default_factory=list)
    price: int | None = None
    valuation: ValuationPayload | None = None
    preliminary_estimate: PreliminaryEstimatePayload | None = None
    market_data: dict[str, Any] | None = None
    sources: list[str] = Field(default_factory=list)


class DebugSummaryPayload(BaseModel):
    market_lookup_attempted: bool = False
    total_comparables_fetched: int | None = None
    relevant_comparables_kept: int | None = None
    sold_comparables_kept: int | None = None
    average_relevance: float | None = None
    status_reasons: list[str] = Field(default_factory=list)
    top_rejection_reasons: list[str] = Field(default_factory=list)
    top_downgrade_reasons: list[str] = Field(default_factory=list)


class MarketSnapshotPayload(BaseModel):
    fetched_count: int = 0
    relevant_count: int = 0
    sold_count: int = 0
    active_count: int = 0
    bidding_count: int = 0
    accessory_like_count: int = 0
    bundle_like_count: int = 0


class DevErrorPayload(BaseModel):
    report_path: str
    fix_prompt_path: str
    report_markdown: str
    fix_prompt_markdown: str
    relevant_filenames: list[str] = Field(default_factory=list)
    input_summary: dict[str, Any] = Field(default_factory=dict)
    suggested_investigation: str


class ValueEnvelope(BaseModel):
    status: Literal["ok", "insufficient_evidence", "ambiguous_model", "degraded", "error"]
    status_title: str
    status_message: str
    user_status_title: str
    user_explanation: str
    recommended_action: str | None = None
    error_stage: str | None = None
    user_message: str | None = None
    technical_message: str | None = None
    dev_error: DevErrorPayload | None = None
    data: ValueData | None = None
    warnings: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    reason_details: list[str] = Field(default_factory=list)
    market_snapshot: MarketSnapshotPayload | None = None
    debug_summary: DebugSummaryPayload | None = None
    debug_id: str
    valuation_id: str | None = None


def _build_ok_user_fields(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    data = payload.get("data") or {}
    valuation = data.get("valuation") or {}
    evidence_summary = valuation.get("evidence_summary")
    explanation = (
        str(evidence_summary)
        if evidence_summary
        else "Vi kunde identifiera produkten och hitta tillräckligt starka jämförelser från andrahandsmarknaden."
    )
    return (
        "Begagnatvärdet är klart",
        explanation,
        "Jämför gärna med skick, lagring och tillbehör innan du sätter ett slutpris.",
    )


def _build_ambiguous_user_fields(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    data = payload.get("data") or {}
    new_price = (data.get("market_data") or {}).get("new_price") or {}
    has_new_price = bool(new_price.get("estimated_new_price")) or bool(new_price.get("sources"))
    requested_angles = list(data.get("requested_additional_angles") or [])
    angle_text = (
        f"Ta gärna bilder på {', '.join(requested_angles[:4])}."
        if requested_angles
        else "Ta gärna fler bilder med modelltext, portar eller baksida."
    )
    explanation = "Vi behöver säkrare produktidentifiering innan vi visar ett begagnatvärde."
    if has_new_price:
        explanation += " Vi kunde däremot hämta nypriskontext som stöd medan vi väntar med själva begagnatvärdet."

    return (
        "Vi behöver säkrare modellträff",
        explanation,
        angle_text,
    )


def _build_insufficient_user_fields(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    snapshot = payload.get("market_snapshot") or {}
    data = payload.get("data") or {}
    preliminary_estimate = data.get("preliminary_estimate") or {}
    fetched = int(snapshot.get("fetched_count") or 0)
    relevant = int(snapshot.get("relevant_count") or 0)
    sold = int(snapshot.get("sold_count") or 0)

    if preliminary_estimate:
        signal_count = int(preliminary_estimate.get("supporting_signal_count") or 0)
        explanation = (
            f"Vi kan visa en grov uppskattning eftersom produkten ser rätt ut, nypriskontext finns och {signal_count} marknadssignal"
            f"{'' if signal_count == 1 else 'er'} pekar åt samma håll. Underlaget räcker däremot inte för ett vanligt begagnatvärde."
        )
        return (
            "Grov uppskattning finns, men inte full värdering",
            explanation,
            "Använd uppskattningen som orientering och kontrollera gärna fler sålda annonser innan du sätter pris.",
        )

    if fetched and relevant == 0:
        explanation = f"Vi hittade {fetched} annonser, men ingen var tillräckligt nära rätt produkt för ett tryggt begagnatvärde."
    elif fetched and relevant:
        explanation = f"Vi hittade {fetched} annonser, men bara {relevant} var tillräckligt relevanta och {sold} såg ut som sålda träffar."
    else:
        explanation = "Produkten kan vara rätt identifierad, men underlaget från andrahandsmarknaden är för svagt för en trygg värdering."

    return (
        "Underlaget räcker inte för begagnatvärde",
        explanation,
        "Prova gärna tydligare produktbilder eller försök igen senare när fler relevanta annonser finns.",
    )


def _build_degraded_user_fields(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    return (
        "Tillfälligt problem i tjänsten",
        "Det här är ett systemproblem i värderingsflödet, inte ett resultat för själva produkten.",
        "Försök igen om en liten stund med samma bilder.",
    )


def _build_error_user_fields(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    return (
        "Begäran kunde inte behandlas",
        "Vi kunde inte läsa eller behandla underlaget i det här försöket.",
        "Kontrollera bilderna och försök igen.",
    )


def build_user_fields(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    status = str(payload.get("status") or "error")
    if status == "ok":
        return _build_ok_user_fields(payload)
    if status == "ambiguous_model":
        return _build_ambiguous_user_fields(payload)
    if status == "insufficient_evidence":
        return _build_insufficient_user_fields(payload)
    if status == "degraded":
        return _build_degraded_user_fields(payload)
    return _build_error_user_fields(payload)


def enrich_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "error")
    reasons = [str(reason) for reason in payload.get("reasons", []) if reason]
    payload["warnings"] = list(dict.fromkeys(str(warning) for warning in payload.get("warnings", []) if warning))
    payload["reasons"] = list(dict.fromkeys(reasons))
    payload["status_title"] = STATUS_TITLES.get(status, STATUS_TITLES["error"])
    payload["status_message"] = STATUS_MESSAGES.get(status, STATUS_MESSAGES["error"])
    user_status_title, user_explanation, recommended_action = build_user_fields(payload)
    payload["user_status_title"] = user_status_title
    payload["user_explanation"] = user_explanation
    payload["recommended_action"] = recommended_action
    payload["reason_details"] = [
        REASON_DETAILS.get(reason, reason.replace("_", " ").capitalize())
        for reason in payload["reasons"]
    ]
    return payload


def _record_failure(
    *,
    payload: dict[str, Any],
    request: ValueRequest,
    error_type: str,
    technical_message: str | None = None,
) -> dict[str, Any]:
    stage = infer_error_stage_from_payload(payload)
    enriched_payload = attach_error_fields(
        payload,
        error_stage=stage,
        technical_message=technical_message,
    )
    artifact_payload = record_error_artifacts(
        debug_id=str(enriched_payload.get("debug_id") or "unknown_error"),
        stage=stage,
        error_type=error_type,
        user_message=str(enriched_payload.get("user_message") or enriched_payload.get("status_message") or "Något gick fel."),
        technical_message=enriched_payload.get("technical_message"),
        status=str(enriched_payload.get("status") or "error"),
        input_summary=build_input_summary(request),
        relevant_filenames=[request.filename] if request.filename else [],
    )
    enriched_payload["dev_error"] = artifact_payload
    return enriched_payload


async def _persist_valuation(response_payload: dict[str, Any], valuation_id: str) -> None:
    """Fire-and-forget: extract fields from response and save to DB. Never raises."""
    data = response_payload.get("data") or {}
    valuation = data.get("valuation") or {}
    market_data = data.get("market_data") or {}
    market_snapshot = response_payload.get("market_snapshot") or {}
    debug_summary = response_payload.get("debug_summary") or {}
    new_price_info = (market_data.get("new_price") or {})

    brand = data.get("brand")
    model_id = data.get("model")
    line = data.get("line")
    product_name = " ".join(p for p in [brand, line, model_id] if p) or None

    db_data = {
        "id": valuation_id,
        "product_name": product_name,
        "product_identifier": model_id,
        "brand": brand,
        "category": data.get("category"),
        "vision_confidence": data.get("confidence"),
        "status": response_payload.get("status"),
        "estimated_value": valuation.get("fair_estimate"),
        "value_range_low": valuation.get("low_estimate"),
        "value_range_high": valuation.get("high_estimate"),
        "new_price": new_price_info.get("estimated_new_price"),
        "confidence": valuation.get("confidence"),
        "num_comparables_raw": (
            debug_summary.get("total_comparables_fetched")
            or market_snapshot.get("fetched_count")
            or 0
        ),
        "num_comparables_used": valuation.get("comparable_count") or 0,
        "sources_json": {
            "fetched": market_snapshot.get("fetched_count", 0),
            "sold": market_snapshot.get("sold_count", 0),
            "active": market_snapshot.get("active_count", 0),
            "relevant": market_snapshot.get("relevant_count", 0),
        },
    }

    await save_valuation(db_data)

    if response_payload.get("status") == "ok" and db_data.get("estimated_value"):
        await save_price_snapshot({
            "product_identifier": model_id,
            "estimated_value": db_data["estimated_value"],
            "value_range_low": db_data["value_range_low"],
            "value_range_high": db_data["value_range_high"],
            "new_price": db_data["new_price"],
            "num_comparables": db_data["num_comparables_used"],
            "sources_json": db_data["sources_json"],
            "snapshot_date": datetime.utcnow().strftime("%Y-%m-%d"),
        })


@router.post("/value", response_model=ValueEnvelope)
def value_image(background_tasks: BackgroundTasks, payload: ValueRequest | None = Body(default=None)):
    request = payload or ValueRequest()
    valuation_id = str(uuid.uuid4())

    logger.info("request.value.start", extra={
        "valuation_id": valuation_id,
        "has_images": bool(request.images or request.image),
        "brand_override": bool(request.brand),
        "model_override": bool(request.model),
        "condition": request.condition,
    })

    try:
        response_payload = enrich_envelope(value_engine.value_item(
            images=request.images,
            image=request.image,
            brand=request.brand,
            model=request.model,
            category=request.category,
            condition=request.condition,
        ))
        if response_payload.get("status") in {"degraded", "error"}:
            result = _record_failure(
                payload=response_payload,
                request=request,
                error_type="ValueEngineFailure",
            )
        else:
            result = response_payload
    except VisionServiceError as exc:
        if exc.retryable:
            result = _record_failure(
                payload=enrich_envelope({
                "status": "degraded",
                "data": {
                    "brand": None,
                    "line": None,
                    "model": None,
                    "category": None,
                    "variant": None,
                    "candidate_models": [],
                    "confidence": None,
                    "reasoning_summary": None,
                    "needs_more_images": False,
                    "requested_additional_angles": [],
                    "price": None,
                    "market_data": None,
                    "sources": [],
                },
                "warnings": [
                    "Resultatet bygger på begränsat underlag",
                    exc.message,
                ],
                "reasons": [exc.code],
                "debug_id": exc.request_id,
            }),
                request=request,
                error_type=type(exc).__name__,
                technical_message=str(exc),
            )
        else:
            result = _record_failure(
                payload=enrich_envelope({
                "status": "error",
                "data": None,
                "warnings": [exc.message],
                "reasons": [exc.code],
                "debug_id": exc.request_id,
            }),
                request=request,
                error_type=type(exc).__name__,
                technical_message=str(exc),
            )
    except Exception as exc:
        result = _record_failure(
            payload=enrich_envelope({
            "status": "degraded",
            "data": None,
            "warnings": [
                "Resultatet bygger på begränsat underlag",
                "Värderings-API:t misslyckades oväntat",
            ],
            "reasons": ["value_endpoint_failure"],
            "debug_id": new_debug_id("value"),
        }),
            request=request,
            error_type=type(exc).__name__,
            technical_message=f"{type(exc).__name__}: {exc}",
        )

    result["valuation_id"] = valuation_id
    logger.info("request.value.complete", extra={
        "valuation_id": valuation_id,
        "status": result.get("status"),
    })
    background_tasks.add_task(_persist_valuation, result, valuation_id)
    return result


class FeedbackRequest(BaseModel):
    valuation_id: str
    feedback: Literal["correct", "too_high", "too_low", "wrong_product"]
    corrected_product: str | None = None


@router.post("/feedback")
async def submit_feedback(payload: FeedbackRequest):
    await save_feedback(payload.valuation_id, payload.feedback, payload.corrected_product)
    return {"ok": True}
