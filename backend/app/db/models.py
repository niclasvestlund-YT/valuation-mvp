import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, func
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

    # OCR tracking
    ocr_provider = Column(String(50), nullable=True, index=True)   # "google_vision" | "easyocr" | None
    ocr_text_found = Column(Boolean, nullable=True)

    # Product identity link
    product_key = Column(String, nullable=True, index=True)  # "sony_wh-1000xm5"

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


class Product(Base):
    __tablename__ = "product"

    product_key = Column(String, primary_key=True)       # "sony_wh-1000xm5"
    brand = Column(String, nullable=False)
    model = Column(String, nullable=False)
    category = Column(String, nullable=True)
    valuation_count = Column(Integer, default=0, server_default="0")
    first_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())


class MarketComparable(Base):
    __tablename__ = "market_comparable"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_key = Column(String, ForeignKey("product.product_key"), nullable=False, index=True)
    source = Column(String, nullable=False)               # "tradera" | "blocket"
    listing_url = Column(String, nullable=False, unique=True)
    title = Column(String, nullable=False)
    price_sek = Column(Integer, nullable=False)
    condition = Column(String, nullable=True)
    relevance_score = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True, server_default="true", index=True)
    flagged = Column(Boolean, default=False, server_default="false")
    flag_reason = Column(String, nullable=True)
    first_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), index=True)
    disappeared_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_comparable_product_active", "product_key", "is_active"),
    )


class NewPriceSnapshot(Base):
    __tablename__ = "new_price_snapshot"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_key = Column(String, ForeignKey("product.product_key"), nullable=False, index=True)
    source = Column(String, nullable=False)               # "serper" | "serpapi"
    price_sek = Column(Integer, nullable=False)
    currency = Column(String, default="SEK", server_default="SEK")
    url = Column(String, nullable=True)
    title = Column(String, nullable=True)
    fetched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())

    __table_args__ = (
        Index("idx_new_price_product", "product_key", "fetched_at"),
    )


class ProductEmbedding(Base):
    __tablename__ = "product_embedding"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_key = Column(String, ForeignKey("product.product_key"), nullable=False, index=True)
    valuation_id = Column(String, nullable=True)
    image_hash = Column(String, nullable=False)           # SHA-256
    embedding = Column(Vector(768), nullable=False)       # pgvector column
    verified = Column(Boolean, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())

    __table_args__ = (
        Index("idx_embedding_verified", "verified", postgresql_where="verified = true"),
    )
