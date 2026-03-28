import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Body, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel, Field, field_validator

from backend.app.core.value_engine import ValueEngine
from backend.app.schemas.assistant import AssistantContext, QuickReply
from backend.app.services.assistant_flow import (
    build_assistant_context,
    build_user_fields,
    enrich_envelope,
    normalize_confirmation,
    is_bundle_eligible,
    STATUS_TITLES,
    STATUS_MESSAGES,
    REASON_DETAILS,
)
from backend.app.db.crud import (
    find_similar_products,
    invalidate_embeddings,
    mark_embeddings_verified,
    save_embedding,
    save_feedback,
    save_price_snapshot,
    save_valuation,
    upsert_comparables,
    upsert_new_price,
    upsert_product,
)
from backend.app.services.embedding_service import (
    compute_embedding_from_base64,
    compute_image_hash,
)
from backend.app.utils.normalization import normalize_product_key
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


# STATUS_TITLES, STATUS_MESSAGES, REASON_DETAILS are imported from assistant_flow



_VALID_CONDITIONS = {"excellent", "good", "fair", "poor"}
_MAX_IMAGES = 8
_MAX_TEXT_FIELD_LEN = 128



class ValueRequest(BaseModel):
    image: str | None = None
    images: list[str] | None = None
    filename: str | None = None
    brand: str | None = None
    model: str | None = None
    category: str | None = None
    condition: str | None = None  # "excellent" | "good" | "fair" | "poor"
    # Assistant fields — all optional, additive
    confirmation: str | None = None          # "yes" | "no" | free-text synonym
    previous_valuation_id: str | None = None
    bundle: str | None = None                # "unit_only" | "with_case" | "combo_kit" | "full_kit"
    shipping: str | None = None              # "can_ship" | "local_only" | "either"
    goal: str | None = None                  # "sell_fast" | "max_price" | "balanced"

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: str | None) -> str | None:
        if v is not None and v.lower() not in _VALID_CONDITIONS:
            raise ValueError(f"condition must be one of {sorted(_VALID_CONDITIONS)}")
        return v.lower() if v else v

    @field_validator("images")
    @classmethod
    def validate_images_count(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) > _MAX_IMAGES:
            raise ValueError(f"images must not exceed {_MAX_IMAGES} items")
        return v

    @field_validator("brand", "model", "category", "filename")
    @classmethod
    def validate_text_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) > _MAX_TEXT_FIELD_LEN:
            raise ValueError(f"field must not exceed {_MAX_TEXT_FIELD_LEN} characters")
        return v


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
    # VALOR ML estimates
    valor_estimate_sek: int | None = None
    valor_model_version: str | None = None
    valor_confidence_label: str | None = None
    valor_mae_at_prediction: float | None = None
    valor_available: bool = False
    valor_status: str | None = None
    # Prisassistent conversation layer
    assistant_context: AssistantContext | None = None



# _build_*_user_fields, build_user_fields, enrich_envelope are now in assistant_flow.py


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
    try:
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
            "condition": response_payload.get("_condition"),
            "response_time_ms": response_payload.get("_response_time_ms"),
            "market_data_json": market_data if market_data else None,
            "ocr_provider": (response_payload.get("_ocr_evidence") or {}).get("provider"),
            "ocr_text_found": (response_payload.get("_ocr_evidence") or {}).get("text_found"),
            "valor_estimate_sek": response_payload.get("valor_estimate_sek"),
            "valor_model_version": response_payload.get("valor_model_version"),
            "valor_confidence_label": response_payload.get("valor_confidence_label"),
            "valor_mae_at_prediction": response_payload.get("valor_mae_at_prediction"),
        }

        # Compute and store product_key
        product_key = None
        if brand and model_id:
            product_key = normalize_product_key(brand, model_id)
            db_data["product_key"] = product_key

        await save_valuation(db_data)

        # Cache product + comparables + new price in background
        if product_key:
            await upsert_product(product_key, brand, model_id, category=data.get("category"))

            comparables = market_data.get("comparables") or []
            if comparables:
                # Normalize comparables to have url field
                for comp in comparables:
                    if not comp.get("url") and comp.get("listing_url"):
                        comp["url"] = comp["listing_url"]
                    if not comp.get("url") and comp.get("raw", {}).get("ItemUrl"):
                        comp["url"] = comp["raw"]["ItemUrl"]
                await upsert_comparables(product_key, comparables, source="pipeline")

            new_price_est = new_price_info.get("estimated_new_price")
            if new_price_est:
                new_price_sources = new_price_info.get("sources") or []
                source_name = new_price_info.get("method") or "serper"
                source_url = new_price_sources[0].get("url") if new_price_sources else None
                source_title = new_price_sources[0].get("title") if new_price_sources else None
                await upsert_new_price(
                    product_key,
                    int(new_price_est),
                    source=source_name,
                    currency=new_price_info.get("currency") or "SEK",
                    url=source_url,
                    title=source_title,
                )

        # Save embedding for learning loop (fire-and-forget)
        if product_key and response_payload.get("status") in {"ok", "depreciation_estimate"}:
            image_b64 = response_payload.get("_image_b64")
            if image_b64:
                embedding = compute_embedding_from_base64(image_b64)
                if embedding:
                    import base64 as _b64
                    raw = image_b64.split(",", 1)[-1] if "," in image_b64 else image_b64
                    try:
                        img_hash = compute_image_hash(_b64.b64decode(raw))
                    except Exception:
                        img_hash = None
                    if img_hash:
                        await save_embedding(
                            product_key,
                            valuation_id,
                            img_hash,
                            embedding,
                            verified=False,  # verified=True only after positive feedback
                        )

        if response_payload.get("status") in {"ok", "depreciation_estimate"} and db_data.get("estimated_value"):
            await save_price_snapshot({
                "product_identifier": model_id,
                "estimated_value": db_data["estimated_value"],
                "value_range_low": db_data["value_range_low"],
                "value_range_high": db_data["value_range_high"],
                "new_price": db_data["new_price"],
                "num_comparables": db_data["num_comparables_used"],
                "sources_json": db_data["sources_json"],
                "snapshot_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            })
    except Exception as exc:
        logger.error("persist_valuation.failed", extra={
            "valuation_id": valuation_id,
            "error": f"{type(exc).__name__}: {exc}",
        }, exc_info=True)


limiter = Limiter(key_func=get_remote_address)

@router.post("/value", response_model=ValueEnvelope)
@limiter.limit("10/minute")
def value_image(request: Request, background_tasks: BackgroundTasks, payload: ValueRequest | None = Body(default=None)):
    req = payload or ValueRequest()
    valuation_id = str(uuid.uuid4())
    t0 = time.monotonic()

    # Normalize assistant confirmation (ja/japp/yes → "yes", nej/fel → "no")
    _confirmed = normalize_confirmation(req.confirmation)
    _has_images = bool(req.images or req.image)

    logger.info("request.value.start", extra={
        "valuation_id": valuation_id,
        "has_images": _has_images,
        "brand_override": bool(req.brand),
        "model_override": bool(req.model),
        "condition": req.condition,
        "confirmation": _confirmed,
    })

    try:
        response_payload = enrich_envelope(
            value_engine.value_item(
                images=req.images,
                image=req.image,
                brand=req.brand,
                model=req.model,
                category=req.category,
                condition=req.condition,
            ),
            confirmation=_confirmed,
            has_images=_has_images,
            condition=req.condition,
            bundle=req.bundle,
            shipping=req.shipping,
            goal=req.goal,
        )
        if response_payload.get("status") in {"degraded", "error"}:
            result = _record_failure(
                payload=response_payload,
                request=req,
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
            }, confirmation=_confirmed, has_images=_has_images),
                request=req,
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
            }, confirmation=_confirmed, has_images=_has_images),
                request=req,
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
        }, confirmation=_confirmed, has_images=_has_images),
            request=request,
            error_type=type(exc).__name__,
            technical_message=f"{type(exc).__name__}: {exc}",
        )

    result["valuation_id"] = valuation_id

    # ── VALOR ML estimate (never crashes) ──
    try:
        valor_svc = request.app.state.valor_service
        _valor_threshold = request.app.state.settings.valor_min_samples_for_production
        _valor_ready = valor_svc._training_sample_count >= _valor_threshold if valor_svc else False
        if valor_svc and valor_svc.is_available() and _valor_ready and result.get("status") in {"ok", "depreciation_estimate"}:
            _data = result.get("data") or {}
            _brand = _data.get("brand")
            _model_id = _data.get("model")
            _market = _data.get("market_data") or {}
            _new_price_info = _market.get("new_price") or {}
            _new_price = _new_price_info.get("estimated_new_price")
            _valuation = _data.get("valuation") or {}
            _fair = _valuation.get("fair_estimate")

            _ratio = None
            if _new_price and _fair and _new_price > 0:
                _ratio = _fair / _new_price

            from backend.app.utils.normalization import normalize_product_key as _npk
            _pk = _npk(_brand or "", _model_id or "") if _brand and _model_id else None

            if _pk:
                valor_result = valor_svc.predict(
                    product_key=_pk,
                    condition=req.condition or "unknown",
                    price_to_new_ratio=_ratio,
                    listing_type="fixed",
                )
                if valor_result:
                    result["valor_estimate_sek"] = valor_result["estimated_price_sek"]
                    result["valor_model_version"] = valor_result["model_version"]
                    result["valor_confidence_label"] = valor_result["confidence_label"]
                    result["valor_mae_at_prediction"] = valor_result["mae_at_prediction"]
                    result["valor_available"] = True
        if valor_svc and valor_svc.is_available() and not _valor_ready:
            result["valor_status"] = "training"
    except Exception:
        pass  # VALOR must never crash the value endpoint

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    result.setdefault("response_time_ms", elapsed_ms)
    logger.info("request.value.complete", extra={
        "valuation_id": valuation_id,
        "status": result.get("status"),
        "response_time_ms": elapsed_ms,
    })

    # Confidence calibration logging — structured data for post-hoc analysis
    _status = result.get("status")
    if _status in {"ok", "depreciation_estimate"}:
        _data = result.get("data") or {}
        _val = _data.get("valuation") or {}
        _snap = result.get("market_snapshot") or {}
        logger.info("calibration.valuation", extra={
            "valuation_id": valuation_id,
            "status": _status,
            "brand": _data.get("brand"),
            "model": _data.get("model"),
            "category": _data.get("category"),
            "condition": req.condition,
            "fair_estimate": _val.get("fair_estimate"),
            "low_estimate": _val.get("low_estimate"),
            "high_estimate": _val.get("high_estimate"),
            "confidence": _val.get("confidence"),
            "vision_confidence": _data.get("confidence"),
            "comparable_count": _val.get("comparable_count"),
            "sold_count": _snap.get("sold_count"),
            "new_price": (_data.get("market_data") or {}).get("new_price", {}).get("estimated_new_price"),
            "response_time_ms": elapsed_ms,
        })

    # Dump last result for local dev inspection
    try:
        import pathlib, json as _json
        pathlib.Path("logs").mkdir(exist_ok=True)
        pathlib.Path("logs/last_valuation.json").write_text(
            _json.dumps(result, ensure_ascii=False, indent=2, default=str)
        )
    except Exception:
        pass

    # Pass DB-only metadata separately — don't leak internal fields in the API response
    # Pass first image for embedding computation (fire-and-forget in background)
    first_image = (req.images[0] if req.images else req.image) if (req.images or req.image) else None
    persist_payload = {**result, "_condition": req.condition, "_response_time_ms": elapsed_ms, "_image_b64": first_image}
    background_tasks.add_task(_persist_valuation, persist_payload, valuation_id)
    return result


class FeedbackRequest(BaseModel):
    valuation_id: str
    feedback: Literal["correct", "too_high", "too_low", "wrong_product"]
    corrected_product: str | None = None


@router.post("/feedback")
async def submit_feedback(payload: FeedbackRequest, background_tasks: BackgroundTasks):
    saved = await save_feedback(payload.valuation_id, payload.feedback, payload.corrected_product)
    if not saved:
        return {"ok": False, "detail": "Valuation not found or database unavailable"}

    # Learning loop: update embedding verification based on feedback
    async def _update_embeddings():
        try:
            from backend.app.db.database import async_session as _session
            from backend.app.db.models import Valuation as _Val
            async with _session() as session:
                val = await session.get(_Val, payload.valuation_id)
                if not val or not val.product_key:
                    return

                if payload.feedback == "correct":
                    await mark_embeddings_verified(val.product_key, verified=True)
                    logger.info("feedback.embeddings_verified", extra={"product_key": val.product_key})
                elif payload.feedback == "wrong_product":
                    await invalidate_embeddings(val.product_key)
                    logger.info("feedback.embeddings_invalidated", extra={"product_key": val.product_key})
        except Exception as exc:
            logger.error("feedback.embedding_update_failed", extra={"error": str(exc)})

    background_tasks.add_task(_update_embeddings)
    return {"ok": True}
