from enum import Enum
from pydantic import BaseModel


class VisionResult(BaseModel):
    product_name: str
    brand: str
    model: str
    confidence: float
    category: str
    year_released: int | None = None
    raw_description: str


class MarketListing(BaseModel):
    title: str
    price: float
    currency: str = "SEK"
    source: str  # "tradera" | "blocket" | "facebook_marketplace" | "google_shopping"
    url: str | None = None
    status: str = "active"  # "sold" | "active"
    date: str | None = None
    relevance_score: float = 0.0


class PricePoint(BaseModel):
    date: str
    price: float
    source: str


class ValuationStatus(str, Enum):
    ok = "ok"
    ambiguous_model = "ambiguous_model"
    insufficient_evidence = "insufficient_evidence"
    estimated_from_depreciation = "estimated_from_depreciation"
    degraded = "degraded"
    error = "error"


class ReasoningStep(BaseModel):
    step: str
    description: str
    confidence: float
    data_points: int


class ValuationResponse(BaseModel):
    status: ValuationStatus
    product_name: str | None = None
    estimated_value: float | None = None
    value_range: tuple[float, float] | None = None
    confidence: float | None = None
    currency: str = "SEK"
    new_price: float | None = None
    new_price_source: str | None = None
    price_history: list[PricePoint] = []
    lowest_new_price_6m: float | None = None
    depreciation_percent: float | None = None
    market_listings: list[MarketListing] = []
    comparables_used: int = 0
    reasoning: list[ReasoningStep] = []
    warnings: list[str] = []
    sources: list[str] = []
    debug: dict | None = None
