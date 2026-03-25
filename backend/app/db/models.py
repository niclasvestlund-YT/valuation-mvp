import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB

from .database import Base


class Valuation(Base):
    __tablename__ = "valuations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        index=True,
    )

    # Product identification
    product_name = Column(String, index=True)        # "Sony WH-1000XM4"
    product_identifier = Column(String, index=True)  # "WH-1000XM4"
    brand = Column(String, index=True)
    category = Column(String, index=True)
    vision_confidence = Column(Float)

    # Valuation result
    status = Column(String, index=True)              # "ok", "ambiguous_model", etc.
    estimated_value = Column(Integer, nullable=True)
    value_range_low = Column(Integer, nullable=True)
    value_range_high = Column(Integer, nullable=True)
    new_price = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=True)

    # Request context
    condition = Column(String, nullable=True)        # "excellent", "good", "fair", "poor"
    response_time_ms = Column(Integer, nullable=True)

    # Data quality metrics
    num_comparables_raw = Column(Integer)
    num_comparables_used = Column(Integer)
    sources_json = Column(JSONB)
    market_data_json = Column(JSONB, nullable=True)

    # User feedback
    feedback = Column(String, nullable=True)         # "correct", "too_high", "too_low", "wrong_product"
    corrected_product = Column(String, nullable=True)

    # Correction tracking
    is_correction = Column(Boolean, default=False, server_default="false")
    original_valuation_id = Column(String, ForeignKey("valuations.id"), nullable=True)


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    product_identifier = Column(String, index=True)
    estimated_value = Column(Integer, nullable=True)
    value_range_low = Column(Integer, nullable=True)
    value_range_high = Column(Integer, nullable=True)
    new_price = Column(Integer, nullable=True)
    num_comparables = Column(Integer)
    sources_json = Column(JSONB)
    snapshot_date = Column(String, index=True)       # "2026-03-24"
    source = Column(String, default="user_scan", server_default="user_scan")

    __table_args__ = (
        Index("ix_price_snapshots_product_date", "product_identifier", "snapshot_date"),
    )
