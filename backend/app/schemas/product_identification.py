from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field


class ProductIdentification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand: str | None = None
    line: str | None = None
    model: str | None = None
    category: str | None = None
    variant: str | None = None
    candidate_models: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str
    needs_more_images: bool = False
    requested_additional_angles: list[str] = Field(default_factory=list)


class ProductIdentificationResult(ProductIdentification):
    source: str
    request_id: str


class ProductIdentificationErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    code: str
    message: str
    retryable: bool = False


@dataclass
class VisionServiceError(Exception):
    request_id: str
    code: str
    message: str
    status_code: int = 503
    retryable: bool = False

    def __str__(self) -> str:
        return f"{self.code}: {self.message} (request_id={self.request_id})"

    def to_payload(self) -> ProductIdentificationErrorPayload:
        return ProductIdentificationErrorPayload(
            request_id=self.request_id,
            code=self.code,
            message=self.message,
            retryable=self.retryable,
        )


def product_identification_json_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "brand": {
                "type": ["string", "null"],
                "description": "Brand only if supported by visible evidence such as text, logos, or markings.",
            },
            "line": {
                "type": ["string", "null"],
                "description": "Optional product family or series if supported by visible evidence.",
            },
            "model": {
                "type": ["string", "null"],
                "description": "Exact marketed model only when justified by strong evidence.",
            },
            "category": {
                "type": ["string", "null"],
                "description": "Broad device category such as smartphone, laptop, headphones, tablet, or camera.",
            },
            "variant": {
                "type": ["string", "null"],
                "description": "Storage, color, size, generation, connectivity, or trim only if visibly supported.",
            },
            "candidate_models": {
                "type": "array",
                "description": "Plausible alternative exact models only. Exclude the chosen primary model.",
                "items": {"type": "string"},
                "maxItems": 5,
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Calibrated confidence tied to evidence quality. Use 0.90+ only when exact model text or model number is visible.",
            },
            "reasoning_summary": {
                "type": "string",
                "description": "Short factual summary that mentions concrete visible evidence such as text, labels, logos, hinge, ports, markings, underside, camera module, packaging, or conflicts across images.",
            },
            "needs_more_images": {
                "type": "boolean",
                "description": "True when exact identification is weak or additional views are needed to disambiguate candidates.",
            },
            "requested_additional_angles": {
                "type": "array",
                "description": "Specific missing views needed to disambiguate the product. Empty only when no more images are needed.",
                "items": {"type": "string"},
                "maxItems": 5,
            },
        },
        "required": [
            "brand",
            "line",
            "model",
            "category",
            "variant",
            "candidate_models",
            "confidence",
            "reasoning_summary",
            "needs_more_images",
            "requested_additional_angles",
        ],
    }
