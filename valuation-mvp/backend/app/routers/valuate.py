import asyncio
import io
import logging
import re as _re
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from PIL import Image
from pydantic import BaseModel
from ..config import settings
from ..middleware.rate_limit import limiter
from ..models import ValuationResponse, ValuationStatus, VisionResult
from ..services import vision, tradera, blocket, marketplace, serpapi, serper, prisjakt, scoring, pricing, depreciation, value_engine

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _strip_exif(data: bytes) -> bytes:
    """Return image data with EXIF metadata removed. Raises on failure (fail closed)."""
    img = Image.open(io.BytesIO(data))
    fmt = img.format or "JPEG"
    clean = Image.new(img.mode, img.size)
    clean.putdata(list(img.getdata()))
    buf = io.BytesIO()
    clean.save(buf, format=fmt)
    return buf.getvalue()


async def _run_market_pipeline(query: str, vision_result: VisionResult) -> ValuationResponse:
    """Steps 2-8: market search, scoring, pricing, response building."""
    # 2. New price + price history (parallel)
    if settings.search_provider == "serper":
        new_price_task = asyncio.create_task(serper.search_new_price(query, settings.serper_dev_api_key))
    else:
        new_price_task = asyncio.create_task(serpapi.search_new_price(query, settings.serpapi_api_key))
    price_history_task = asyncio.create_task(prisjakt.get_price_history(query, settings.serpapi_api_key))

    # 3. Market data (all parallel) — only genuine used-market sources
    tradera_task = asyncio.create_task(tradera.search_listings(query, settings.tradera_app_id, settings.tradera_app_key))
    blocket_task = asyncio.create_task(blocket.search_listings(query))
    marketplace_task = asyncio.create_task(marketplace.search_listings(query, settings.serpapi_api_key))

    (new_price, new_price_source), (price_history, lowest_new_price_6m), tradera_results, blocket_results, marketplace_results = await asyncio.gather(
        new_price_task, price_history_task,
        tradera_task, blocket_task, marketplace_task,
    )

    sources_used: list[str] = []
    all_listings = []

    for results, source_name in [
        (tradera_results, "tradera"),
        (blocket_results, "blocket"),
        (marketplace_results, "facebook_marketplace"),
    ]:
        if results:
            sources_used.append(source_name)
            all_listings.extend(results)

    if new_price:
        sources_used.append(new_price_source or "google_shopping")

    # 4. Score
    scored = scoring.score_listings(all_listings, vision_result, new_price)

    # 5. Depreciation fallback
    dep_estimate = depreciation.estimate_from_depreciation(
        new_price or 0,
        vision_result.category,
        vision_result.year_released,
    ) if new_price else None

    # 6. Pricing
    pricing_result = pricing.calculate_pricing(scored, new_price, dep_estimate)

    # 7. Debug info — never include API keys
    debug_info = None
    if settings.debug:
        debug_info = {
            "vision": vision_result.model_dump(),
            "query": query,
            "new_price": new_price,
            "new_price_source": new_price_source,
            "depreciation_estimate": dep_estimate,
            "total_listings_found": len(all_listings),
            "listings_after_scoring": len(scored),
            "pricing": pricing_result,
        }

    # 8. Build response
    return value_engine.build_response(
        vision=vision_result,
        pricing=pricing_result,
        all_listings=scored,
        price_history=price_history,
        lowest_new_price_6m=lowest_new_price_6m,
        new_price_source=new_price_source,
        sources=list(dict.fromkeys(sources_used)),
        debug=debug_info,
        debug_enabled=settings.debug,
    )


@router.post("/valuate", response_model=ValuationResponse)
@limiter.limit("10/minute")
async def valuate(request: Request, images: list[UploadFile] = File(...)):
    if not images:
        raise HTTPException(status_code=400, detail="Minst en bild krävs")
    if len(images) > 5:
        raise HTTPException(status_code=400, detail="Max 5 bilder")

    image_bytes_list = []
    for img in images:
        if img.content_type not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail=f"Filtyp stöds ej: {img.content_type}")
        content = await img.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"{img.filename} överstiger 10MB")
        try:
            image_bytes_list.append(_strip_exif(content))
        except Exception:
            raise HTTPException(status_code=422, detail=f"Kunde inte behandla bilden: {img.filename}")

    # 1. Vision
    try:
        vision_result = await vision.identify_product(image_bytes_list)
    except Exception as e:
        logger.error(f"Vision failed: {e}")
        if settings.debug:
            raise
        return ValuationResponse(
            status=ValuationStatus.error,
            warnings=["Bildanalys misslyckades. Försök igen."],
        )

    return await _run_market_pipeline(vision_result.product_name, vision_result)


class RevaluateRequest(BaseModel):
    product_name: str


@router.post("/revaluate", response_model=ValuationResponse)
@limiter.limit("10/minute")
async def revaluate(request: Request, req: RevaluateRequest):
    query = req.product_name.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Produktnamn krävs")

    # Synthetic vision result — product name is user-provided, skip image analysis
    words = query.split()
    brand = words[0] if words else query
    # Extract model code (e.g. "WH-1000XM4" from "Sony WH-1000XM4") so that
    # _is_wrong_model() can detect sibling model numbers in comparables.
    model_match = _re.search(r'\b([A-Za-z]{2,5}-[A-Z0-9][A-Z0-9-]+)\b', query, _re.IGNORECASE)
    model = model_match.group(1) if model_match else query
    vision_result = VisionResult(
        product_name=query,
        brand=brand,
        model=model,
        confidence=1.0,
        category="other",
        year_released=None,
        raw_description=f"User-corrected product: {query}",
    )

    return await _run_market_pipeline(query, vision_result)
