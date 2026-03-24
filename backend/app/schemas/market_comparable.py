from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MarketComparable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    listing_id: str
    title: str
    price: float
    currency: str
    status: str
    url: str | None = None
    ended_at: datetime | None = None
    shipping_cost: float | None = None
    condition_hint: str | None = None
    raw: dict[str, Any]
