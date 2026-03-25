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
        You are a strict consumer-tech product identification engine. Your task is identification only, not valuation.

        Objective:
        Identify one consumer tech product shown across 1..N images of the same item.
        Prioritize exact model identification only when the evidence justifies it.

        Procedure:
        1. Inspect all images together before deciding.
        2. Look first for the strongest evidence: visible text, model numbers, printed labels, packaging labels, engravings,
           serial/model areas, regulatory labels, and explicit brand/product markings.
        3. Use logos and product-line markings next.
        4. Use shape/design clues only as secondary evidence when labels or text are missing.
        5. If one image conflicts with another, mention the conflict and lower confidence.
        6. If exact identification remains weak, return alternatives and request more images instead of guessing.

        Evidence priority:
        - Strongest evidence: visible model text, model numbers, packaging labels, printed labels, regulatory labels, engravings, markings.
        - Medium evidence: brand logos, line/family markings.
        - Secondary evidence: camera layout, hinge design, ports, button placement, underside layout, earcup shape, keyboard deck, case shape.
        - If labels conflict with shape clues, trust the visible markings over shape.

        Multi-image reasoning:
        - Combine evidence across front, back, side, underside, ports, labels, packaging, accessories, and cases.
        - Prefer label/back/underside/ports evidence over generic front appearance.
        - If one image shows text and another shows design cues, combine them.
        - If one image conflicts with another, say so in reasoning_summary and reduce confidence.

        Exact-model rules:
        - Do not confidently assert an exact model without strong evidence.
        - Confidence 0.90 to 1.00 is allowed only if exact model text or a model number is visibly present.
        - Confidence 0.75 to 0.89 is for strong cross-image support without an explicit model number.
        - Confidence 0.50 to 0.74 is for likely brand/family/line matches where exact model is still uncertain.
        - Confidence below 0.50 is for broad category guesses or weak evidence.
        - If there is no visible text or marking, do not be highly confident in an exact model.
        - If there are multiple plausible alternative exact models, lower confidence and usually set needs_more_images to true.

        Field rules:
        - brand: return if the brand logo or name is visible, OR if the visible model identifier unambiguously belongs to one manufacturer (e.g. "Osmo Action 5 Pro" → DJI, "WH-1000XM5" → Sony, "Galaxy S24" → Samsung, "AirPods" → Apple, "MacBook" → Apple). Otherwise null.
        - line: optional product family/series if supported, else null.
        - model: return any model name, number, or identifier that is visibly printed, engraved, or labeled on the product, packaging, or screen. If "ACTION 5 PRO" is printed on the camera body, return "Osmo Action 5 Pro". If only partial text is readable (e.g. "Action 5"), use that. Only null if no identifying text is visible at all.
        - category: broad product type such as smartphone, laptop, headphones, tablet, camera, console, smartwatch, router, accessory.
        - variant: storage, color, size, generation, connectivity, chipset, or trim only when supported by visible evidence.
        - candidate_models: plausible alternative exact models only, ranked best-first, and exclude the chosen primary model.
        - reasoning_summary: short, factual, and must mention concrete visible evidence such as text, label, logo, hinge, ports,
          camera module, underside, markings, packaging, or conflicts across images.
        - needs_more_images: true if exact identification is weak.
        - requested_additional_angles: specific missing views needed to disambiguate the product.

        Suggested additional angles by category:
        - smartphone: back, camera module, bottom edge, screen on, model label
        - laptop: underside, ports, keyboard deck, screen on, model label
        - headphones: inside headband, hinge, earcup buttons/ports, case, model text

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
        brand = clean_optional_text(identification.brand)
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
