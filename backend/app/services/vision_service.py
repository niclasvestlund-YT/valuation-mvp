import json
import time
from textwrap import dedent
from uuid import uuid4

import requests

from backend.app.core.config import settings
from backend.app.schemas.product_identification import (
    ProductIdentification,
    ProductIdentificationResult,
    VisionServiceError,
    product_identification_json_schema,
)
from backend.app.services.image_preprocess import ImagePreprocessError, preprocess_images
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
STRONG_IDENTIFICATION_CONFIDENCE = 0.75
EXACT_MODEL_WITHOUT_TEXT_CAP = 0.89
GENERIC_SINGLE_IMAGE_CONFIDENCE_CAP = 0.69
MULTIPLE_ALTERNATIVES_CONFIDENCE_CAP = 0.74
MISSING_CONCRETE_EVIDENCE_CAP = 0.69

BRAND_CANONICAL = {
    "dji": "DJI",
    "sony": "Sony",
    "apple": "Apple",
    "samsung": "Samsung",
    "google": "Google",
    "microsoft": "Microsoft",
    "lg": "LG",
    "hp": "HP",
    "asus": "ASUS",
    "jbl": "JBL",
    "bose": "Bose",
    "lenovo": "Lenovo",
    "dell": "Dell",
    "huawei": "Huawei",
    "xiaomi": "Xiaomi",
    "oneplus": "OnePlus",
    "gopro": "GoPro",
    "nintendo": "Nintendo",
}

STRONG_TEXT_EVIDENCE_KEYWORDS = {
    "text",
    "label",
    "model number",
    "model text",
    "marking",
    "markings",
    "engraving",
    "engraved",
    "printed",
    "serial",
    "sticker",
    "packaging",
    "box",
    "regulatory",
    "branding",
    "branded",
    "writing",
    "inscription",
    "reads",
    "says",
    "visible on",
    "printed on",
    "stamped",
    "embossed",
}

CONCRETE_EVIDENCE_KEYWORDS = STRONG_TEXT_EVIDENCE_KEYWORDS | {
    "logo",
    "hinge",
    "ports",
    "port",
    "camera module",
    "camera",
    "underside",
    "bottom edge",
    "inside headband",
    "earcup",
    "buttons",
    "button layout",
    "keyboard deck",
    "regulatory",
}

CONFLICT_EVIDENCE_KEYWORDS = {
    "conflict",
    "conflicts",
    "contradict",
    "contradicts",
    "contradictory",
    "inconsistent",
    "mismatch",
}

CATEGORY_REQUESTED_ANGLES = {
    "smartphone": ["back", "camera module", "bottom edge", "screen on", "model label"],
    "laptop": ["underside", "ports", "keyboard deck", "screen on", "model label"],
    "headphones": ["inside headband", "hinge", "earcup buttons/ports", "case", "model text"],
    "default": ["front", "back", "label", "ports"],
}


def build_identification_prompt() -> str:
    return dedent(
        """
        Role:
        You are an expert consumer-tech product identification engine. Your task is identification only, not valuation.
        You have deep knowledge of product lines and generations — use it. Your goal is to identify the FULL marketed product name
        including brand, product line, and generation/version number.

        Objective:
        Identify one consumer tech product shown across 1..N images of the same item.
        Always aim for the most specific identification possible. We need the exact generation and version.

        Specificity examples:
        - BAD: "DJI camera" — too vague, missing product line and generation
        - BAD: "DJI Osmo" — missing which Osmo product (Pocket? Action? Mobile?) and which generation
        - GOOD: "DJI Osmo Pocket 3" — full product line + generation
        - GOOD: "Apple iPhone 14 Pro" — brand + line + generation + variant
        - GOOD: "Sony WH-1000XM5" — brand + exact model number
        - BAD: "Sony headphones" — too vague
        - BAD: "MacBook" — missing which MacBook and which generation

        Chain-of-thought procedure (follow these steps in order):
        1. BRAND: Look for brand logos, brand text, or brand-distinctive design language.
           Check: logo placement, brand name printed/engraved, brand-specific design cues.
        2. PRODUCT LINE: Identify the product family/series.
           Check: printed line name (e.g. "OSMO"), form factor (gimbal camera vs action camera vs drone), product category.
        3. GENERATION/VERSION: Determine the specific generation or version number.
           Check: screen size and type (OLED vs LCD, rotatable vs fixed), button layout and count, body shape and proportions,
           sensor size indicators, port types (USB-C, Lightning), color options unique to a generation,
           any visible text like version numbers. Compare against your knowledge of how each generation differs.
        4. VARIANT: Note any storage, color, connectivity, or trim details visible.
        5. CROSS-CHECK: Verify that all visual evidence is consistent with your identified model.
           If the screen design says "Pocket 3" but the body shape says "Pocket 2", flag the conflict.

        Evidence priority:
        - Strongest: visible model text, model numbers, packaging labels, printed labels, regulatory labels, engravings.
        - Strong: brand logos, line/family markings (e.g. "OSMO" printed on body), combined with design-generation cues.
        - Medium: form factor, screen design, button layout, port placement — these often uniquely identify a generation.
        - Secondary: overall shape, color, size when other evidence is unavailable.
        - IMPORTANT: A brand/line marking (e.g. "OSMO") combined with generation-specific design features (e.g. 2-inch rotatable
          OLED screen, specific button layout) IS strong evidence for an exact model. Do not treat partial text as the full model name.
          "OSMO" on the body of a gimbal camera with a 2-inch rotatable screen means "DJI Osmo Pocket 3", not just "DJI Osmo".

        Product knowledge you should apply:
        - DJI Osmo Pocket 1: small 1-inch screen, no rotation, squared body
        - DJI Osmo Pocket 2: small 1-inch screen, no rotation, rounded grip, single button
        - DJI Osmo Pocket 3: large 2-inch rotatable OLED touchscreen, "OSMO" printed on grip, orange-ringed record button, 1-inch CMOS sensor
        - DJI Osmo Action 5 Pro: action camera form factor, front+rear screens, "ACTION 5 PRO" text
        - DJI Osmo Action 4: action camera, single rear screen
        - Sony WH-1000XM5: smooth headband, no visible hinges, touch panel on right cup
        - Sony WH-1000XM4: stepped headband, folding hinges, touch panel on right cup
        - iPhone generations differ by camera module layout, notch vs Dynamic Island, button placement

        Multi-image reasoning:
        - Combine evidence across all images before deciding.
        - Prefer label/back/underside/ports evidence over generic front appearance.
        - If one image shows text and another shows design cues, combine them.
        - If one image conflicts with another, say so in reasoning_summary and reduce confidence.

        Confidence calibration:
        - 0.90–1.00: exact model text or model number is visibly printed/engraved AND matches design cues.
        - 0.80–0.89: no exact model text, but brand marking + generation-specific design features strongly indicate one model.
        - 0.65–0.79: brand identified, product line likely, but generation is uncertain between 2 options.
        - 0.50–0.64: brand/family match but exact model is genuinely ambiguous among 3+ options.
        - Below 0.50: broad category guess or very weak evidence.
        - IMPORTANT: If you can confidently identify the generation from design features (screen type, button layout, body shape)
          even without explicit model text, use the 0.80–0.89 range. Do NOT default to low confidence just because
          the full model name isn't printed on the device — most products only print the brand or line name.

        Field rules:
        - brand: return if the brand logo or name is visible, OR if the visible model identifier unambiguously belongs to one manufacturer. Examples: "Osmo Action 5 Pro" → DJI, "Action 5 Pro" → DJI, "Action 4" → DJI, "Action 3" → DJI, "Osmo Action" → DJI, "Osmo Pocket" → DJI, "Osmo Mobile" → DJI, "Mini 4 Pro" → DJI, "WH-1000XM5" → Sony, "WF-1000XM5" → Sony, "Galaxy S24" → Samsung, "Galaxy Buds" → Samsung, "AirPods" → Apple, "MacBook" → Apple, "iPad" → Apple, "Surface Pro" → Microsoft, "Pixel 9" → Google. Otherwise null.
        - line: product family/series (e.g. "Osmo Pocket", "WH-1000X", "iPhone"). Always fill this if you can identify the product line.
        - model: the FULL marketed product name including generation/version (e.g. "DJI Osmo Pocket 3", not "DJI Osmo" or "Osmo Pocket").
          Use your product knowledge to infer the generation from design features when the full name isn't printed.
          Only null if you truly cannot determine even the product line.
        - category: broad product type such as smartphone, laptop, headphones, tablet, camera, console, smartwatch, router, accessory.
        - variant: storage, color, size, connectivity, chipset, or trim only when supported by visible evidence.
        - candidate_models: plausible alternative exact models only (with full names including generation), ranked best-first, exclude the chosen primary model.
        - reasoning_summary: short, factual, and MUST mention: (1) what brand evidence you see, (2) what product line evidence you see,
          (3) what generation-specific features you see, (4) any text/labels/logos visible. Mention concrete evidence like text, label,
          logo, screen type, button layout, ports, markings, packaging.
        - needs_more_images: true if exact generation identification is weak.
        - requested_additional_angles: specific missing views needed to disambiguate the product.

        Suggested additional angles by category:
        - smartphone: back, camera module, bottom edge, screen on, model label
        - laptop: underside, ports, keyboard deck, screen on, model label
        - headphones: inside headband, hinge, earcup buttons/ports, case, model text
        - camera: model label or engraving, back/underside showing regulatory labels, packaging or box labels

        Output rules:
        - Return strict JSON only.
        - Do not output markdown.
        - Do not output any prose before or after the JSON.
        - Return exactly one JSON object with the required schema.
        """
    ).strip()


def build_retry_delay(attempt: int, base_delay_seconds: float = 1.0) -> float:
    return min(8.0, base_delay_seconds * (2**attempt))


def merge_image_inputs(images: list[str] | None = None, image: str | None = None) -> list[str]:
    merged = [item for item in (images or []) if item]
    if image:
        merged.insert(0, image)
    return merged


def clamp_confidence(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(str(value).split())
    return cleaned or None


def normalize_comparison_text(value: str | None) -> str:
    return " ".join((value or "").lower().replace("-", " ").split())


def contains_keyword(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    for keyword in keywords:
        if keyword not in lowered:
            continue

        negative_forms = (
            f"no {keyword}",
            f"not {keyword}",
            f"without {keyword}",
            f"missing {keyword}",
        )
        if any(negative_form in lowered for negative_form in negative_forms):
            continue

        return True

    return False


def normalize_candidate_models(primary_model: str | None, candidate_models: list[str]) -> list[str]:
    primary_key = normalize_comparison_text(primary_model)
    normalized: list[str] = []
    seen: set[str] = set()

    for candidate in candidate_models:
        cleaned = clean_optional_text(candidate)
        if not cleaned:
            continue

        candidate_key = normalize_comparison_text(cleaned)
        if not candidate_key or candidate_key == primary_key or candidate_key in seen:
            continue

        seen.add(candidate_key)
        normalized.append(cleaned)

    return normalized[:5]


def default_requested_additional_angles(category: str | None) -> list[str]:
    normalized_category = normalize_comparison_text(category)
    category_tokens = set(normalized_category.split())

    if "headphone" in normalized_category or "headset" in normalized_category or "earbud" in normalized_category:
        return CATEGORY_REQUESTED_ANGLES["headphones"]

    if normalized_category == "smartphone" or normalized_category == "phone" or "smartphone" in category_tokens:
        return CATEGORY_REQUESTED_ANGLES["smartphone"]

    if "laptop" in normalized_category or "notebook" in normalized_category:
        return CATEGORY_REQUESTED_ANGLES["laptop"]

    return CATEGORY_REQUESTED_ANGLES["default"]


def merge_requested_additional_angles(category: str | None, requested_angles: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    for angle in requested_angles + default_requested_additional_angles(category):
        cleaned = clean_optional_text(angle)
        if not cleaned:
            continue

        key = normalize_comparison_text(cleaned)
        if key in seen:
            continue

        seen.add(key)
        merged.append(cleaned)

    return merged[:5]


class VisionService:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.api_key = (api_key or settings.openai_api_key or "").strip() or None
        self.model = model or settings.openai_vision_model
        self.timeout_seconds = timeout_seconds or settings.openai_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.openai_max_retries
        self.use_mock_vision = settings.use_mock_vision

    def detect_product(
        self,
        images: list[str] | None = None,
        image: str | None = None,
        request_id: str | None = None,
    ) -> ProductIdentificationResult:
        resolved_request_id = request_id or self._new_request_id()
        incoming_images = merge_image_inputs(images=images, image=image)

        logger.info(
            "vision.identify.start request_id=%s image_count=%s use_mock_vision=%s",
            resolved_request_id,
            len(incoming_images),
            self.use_mock_vision,
        )

        if self.use_mock_vision:
            mock_result = self._mock_identify(incoming_images, resolved_request_id)
            validated = self._validate_identification(
                mock_result,
                image_count=max(1, len(incoming_images)),
            )
            result = ProductIdentificationResult(
                **validated.model_dump(),
                source=mock_result.source,
                request_id=resolved_request_id,
            )
            logger.info(
                "vision.identify.mock_success request_id=%s brand=%s model=%s",
                resolved_request_id,
                result.brand,
                result.model,
            )
            return result

        if not self.api_key:
            raise self._error(
                request_id=resolved_request_id,
                code="missing_openai_api_key",
                message="OPENAI_API_KEY is required unless USE_MOCK_VISION=true.",
                status_code=503,
            )

        if not incoming_images:
            raise self._error(
                request_id=resolved_request_id,
                code="no_images_provided",
                message="At least one uploaded image is required for identification.",
                status_code=422,
            )

        try:
            processed_images = preprocess_images(incoming_images)
        except ImagePreprocessError as exc:
            raise self._error(
                request_id=resolved_request_id,
                code="image_preprocess_failed",
                message=str(exc),
                status_code=422,
            ) from exc

        payload = self._build_request_payload(processed_images)
        response_json = self._post_with_retry(payload, request_id=resolved_request_id)
        identification = self._parse_response(
            response_json,
            request_id=resolved_request_id,
            image_count=len(processed_images),
        )

        result = ProductIdentificationResult(
            **identification.model_dump(),
            source="OpenAI Responses API",
            request_id=resolved_request_id,
        )

        logger.info(
            "vision.identify.success request_id=%s brand=%s model=%s confidence=%s",
            resolved_request_id,
            result.brand,
            result.model,
            result.confidence,
        )
        return result

    def _build_request_payload(self, processed_images: list) -> dict:
        content = [{"type": "input_text", "text": build_identification_prompt()}]

        for processed_image in processed_images:
            content.append(
                {
                    "type": "input_image",
                    "image_url": processed_image.data_url,
                    "detail": "high",
                }
            )

        return {
            "model": self.model,
            "input": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_output_tokens": 500,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "product_identification",
                    "strict": True,
                    "schema": product_identification_json_schema(),
                }
            },
        }

    def _post_with_retry(self, payload: dict, request_id: str) -> dict:
        last_error: VisionServiceError | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(
                    "https://api.openai.com/v1/responses",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except requests.Timeout as exc:
                last_error = self._error(
                    request_id=request_id,
                    code="openai_timeout",
                    message="Timed out while calling OpenAI vision.",
                    status_code=504,
                    retryable=True,
                )
                if attempt >= self.max_retries:
                    raise last_error from exc

                self._sleep_before_retry(attempt, request_id, last_error.message)
                continue
            except requests.RequestException as exc:
                raise self._error(
                    request_id=request_id,
                    code="openai_network_error",
                    message=f"Network error while calling OpenAI vision: {exc}",
                    status_code=502,
                ) from exc

            if response.status_code in RETRYABLE_STATUS_CODES:
                last_error = self._error(
                    request_id=request_id,
                    code="openai_retryable_error",
                    message=self._extract_error_message(response),
                    status_code=503,
                    retryable=True,
                )
                if attempt >= self.max_retries:
                    raise last_error

                self._sleep_before_retry(attempt, request_id, last_error.message)
                continue

            if response.status_code >= 400:
                raise self._error(
                    request_id=request_id,
                    code="openai_request_failed",
                    message=self._extract_error_message(response),
                    status_code=422 if response.status_code == 400 else 502,
                )

            try:
                return response.json()
            except ValueError as exc:
                raise self._error(
                    request_id=request_id,
                    code="invalid_openai_http_response",
                    message="OpenAI returned a non-JSON response.",
                    status_code=502,
                ) from exc

        if last_error:
            raise last_error

        raise self._error(
            request_id=request_id,
            code="openai_unknown_failure",
            message="OpenAI vision request failed unexpectedly.",
            status_code=503,
        )

    def _parse_response(self, payload: dict, request_id: str, image_count: int) -> ProductIdentification:
        output_text = payload.get("output_text") or self._extract_output_text(payload)
        if not output_text:
            raise self._error(
                request_id=request_id,
                code="invalid_openai_response",
                message="OpenAI response did not contain structured output text.",
                status_code=502,
            )

        logger.info(
            "vision.identify.raw_output request_id=%s output=%s",
            request_id,
            output_text,
        )

        try:
            parsed = json.loads(output_text)
            identification = ProductIdentification.model_validate(parsed)
        except (json.JSONDecodeError, ValueError) as exc:
            raise self._error(
                request_id=request_id,
                code="invalid_openai_json",
                message=f"Could not parse OpenAI structured output: {exc}",
                status_code=502,
            ) from exc

        return self._validate_identification(identification, image_count=image_count)

    def _extract_output_text(self, payload: dict) -> str | None:
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text")

        return None

    def _extract_error_message(self, response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return f"OpenAI returned HTTP {response.status_code}."

        error = payload.get("error", {})
        return error.get("message") or f"OpenAI returned HTTP {response.status_code}."

    def _sleep_before_retry(self, attempt: int, request_id: str, reason: str) -> None:
        delay = build_retry_delay(attempt)
        logger.warning(
            "vision.identify.retry request_id=%s attempt=%s delay_seconds=%s reason=%s",
            request_id,
            attempt + 1,
            delay,
            reason,
        )
        time.sleep(delay)

    def _mock_identify(
        self,
        incoming_images: list[str],
        request_id: str,
    ) -> ProductIdentificationResult:
        combined_hint = " ".join(incoming_images).lower()

        catalog = {
            "iphone": {
                "brand": "Apple",
                "model": "iPhone 13",
                "category": "smartphone",
                "variant": None,
                "candidate_models": ["iPhone 13", "iPhone 13 Pro", "iPhone 12"],
                "confidence": 0.84,
            },
            "macbook": {
                "brand": "Apple",
                "model": "MacBook Air M2",
                "category": "laptop",
                "variant": "M2",
                "candidate_models": ["MacBook Air M2", "MacBook Air M1"],
                "confidence": 0.82,
            },
            "sony": {
                "brand": "Sony",
                "model": "WH-1000XM4",
                "category": "headphones",
                "variant": None,
                "candidate_models": ["WH-1000XM4", "WH-1000XM5"],
                "confidence": 0.8,
            },
        }

        for keyword, item in catalog.items():
            if keyword in combined_hint:
                return ProductIdentificationResult(
                    **item,
                    reasoning_summary="USE_MOCK_VISION=true matched a mock catalog keyword.",
                    needs_more_images=False,
                    requested_additional_angles=[],
                    source="Mock vision service",
                    request_id=request_id,
                )

        return ProductIdentificationResult(
            brand="Unknown",
            line=None,
            model="Unknown Tech Product",
            category="unknown",
            variant=None,
            candidate_models=[],
            confidence=0.2,
            reasoning_summary="USE_MOCK_VISION=true and the mock catalog found no clear match.",
            needs_more_images=True,
            requested_additional_angles=["front", "back", "label", "ports"],
            source="Mock vision service",
            request_id=request_id,
        )

    def _validate_identification(
        self,
        identification: ProductIdentification,
        image_count: int,
    ) -> ProductIdentification:
        brand = BRAND_CANONICAL.get((clean_optional_text(identification.brand) or "").lower(), clean_optional_text(identification.brand))
        line = clean_optional_text(identification.line)
        model = clean_optional_text(identification.model)
        category = clean_optional_text(identification.category)
        variant = clean_optional_text(identification.variant)
        reasoning_summary = clean_optional_text(identification.reasoning_summary) or "No evidence summary provided."
        candidate_models = normalize_candidate_models(model, identification.candidate_models)
        requested_additional_angles = merge_requested_additional_angles(
            category,
            identification.requested_additional_angles,
        )

        confidence = clamp_confidence(float(identification.confidence))
        has_text_evidence = contains_keyword(reasoning_summary, STRONG_TEXT_EVIDENCE_KEYWORDS)
        has_concrete_evidence = contains_keyword(reasoning_summary, CONCRETE_EVIDENCE_KEYWORDS)
        has_conflict = contains_keyword(reasoning_summary, CONFLICT_EVIDENCE_KEYWORDS)
        exact_model_claimed = bool(model)
        multiple_alternatives = len(candidate_models) >= 2

        if exact_model_claimed and not has_text_evidence:
            confidence = min(confidence, EXACT_MODEL_WITHOUT_TEXT_CAP)

        if image_count <= 1 and not has_text_evidence:
            confidence = min(confidence, GENERIC_SINGLE_IMAGE_CONFIDENCE_CAP)

        if multiple_alternatives:
            confidence = min(confidence, MULTIPLE_ALTERNATIVES_CONFIDENCE_CAP)

        if exact_model_claimed and not has_concrete_evidence:
            confidence = min(confidence, MISSING_CONCRETE_EVIDENCE_CAP)

        if not exact_model_claimed and line:
            confidence = min(confidence, MULTIPLE_ALTERNATIVES_CONFIDENCE_CAP)
        elif not exact_model_claimed:
            confidence = min(confidence, 0.49)

        if has_conflict:
            confidence = min(confidence, MULTIPLE_ALTERNATIVES_CONFIDENCE_CAP)

        confidence = clamp_confidence(confidence)
        needs_more_images = bool(
            identification.needs_more_images
            or confidence < STRONG_IDENTIFICATION_CONFIDENCE
            or multiple_alternatives
            or has_conflict
        )

        if needs_more_images:
            requested_additional_angles = merge_requested_additional_angles(category, requested_additional_angles)
        else:
            requested_additional_angles = []

        return identification.model_copy(
            update={
                "brand": brand,
                "line": line,
                "model": model,
                "category": category,
                "variant": variant,
                "candidate_models": candidate_models,
                "confidence": confidence,
                "reasoning_summary": reasoning_summary,
                "needs_more_images": needs_more_images,
                "requested_additional_angles": requested_additional_angles,
            }
        )

    def _error(
        self,
        request_id: str,
        code: str,
        message: str,
        status_code: int,
        retryable: bool = False,
    ) -> VisionServiceError:
        logger.error(
            "vision.identify.failure request_id=%s code=%s status_code=%s retryable=%s reason=%s",
            request_id,
            code,
            status_code,
            retryable,
            message,
        )
        return VisionServiceError(
            request_id=request_id,
            code=code,
            message=message,
            status_code=status_code,
            retryable=retryable,
        )

    def _new_request_id(self) -> str:
        return f"vision_{uuid4().hex[:12]}"
