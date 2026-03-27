import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

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

    # VALOR ML estimates
    valor_estimate_sek = Column(Integer, nullable=True)
    valor_model_version = Column(Text, nullable=True)
    valor_confidence_label = Column(Text, nullable=True)
    valor_mae_at_prediction = Column(Float, nullable=True)


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


class AgentJob(Base):
    """Tracks external agent/crawler job runs."""
    __tablename__ = "agent_job"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    product_key = Column(Text, nullable=False)
    search_terms = Column(ARRAY(Text), nullable=True)
    source = Column(Text, nullable=False)
    observations_added = Column(Integer, default=0, server_default="0")
    observations_rejected = Column(Integer, default=0, server_default="0")
    status = Column(Text, nullable=False, default="running", server_default="running")
    summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_agent_job_started", "started_at"),
        Index("idx_agent_job_product_started", "product_key", "started_at"),
    )


class PriceObservation(Base):
    """Ingested price data from external agents/crawlers."""
    __tablename__ = "price_observation"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_key = Column(Text, nullable=False, index=True)
    observed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())
    price_sek = Column(Integer, nullable=False)
    condition = Column(Text, default="unknown", server_default="unknown")
    source = Column(Text, nullable=False)
    source_url = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=True)
    agent_run_id = Column(Text, nullable=True)
    is_sold = Column(Boolean, default=False, server_default="false")
    listing_type = Column(Text, default="unknown", server_default="unknown")
    final_price = Column(Boolean, default=False, server_default="false")
    days_since_listed = Column(Integer, nullable=True)
    price_to_new_ratio = Column(Float, nullable=True)
    new_price_at_observation = Column(Integer, nullable=True)
    suspicious = Column(Boolean, default=False, server_default="false")
    suspicious_reason = Column(Text, nullable=True)
    currency = Column(Text, default="SEK", server_default="SEK")

    __table_args__ = (
        Index("idx_obs_product_observed", "product_key", "observed_at"),
        Index("idx_obs_suspicious_product", "suspicious", "product_key"),
    )


class TrainingSample(Base):
    """Deduplicated, quality-scored samples for VALOR training."""
    __tablename__ = "training_sample"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_key = Column(Text, nullable=False)
    price_sek = Column(Integer, nullable=False)
    condition = Column(Text, default="unknown", server_default="unknown")
    condition_encoded = Column(Float, nullable=False)
    source_type = Column(Text, nullable=False)
    source_id = Column(Text, nullable=False, unique=True)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    listing_type = Column(Text, default="unknown", server_default="unknown")
    final_price = Column(Boolean, default=False, server_default="false")
    is_sold = Column(Boolean, default=False, server_default="false")
    price_to_new_ratio = Column(Float, nullable=True)
    new_price_at_observation = Column(Integer, nullable=True)
    days_since_observation = Column(Integer, nullable=True)
    month_of_year = Column(Integer, nullable=True)
    quality_score = Column(Float, default=0.0, server_default="0.0")
    included_in_training = Column(Boolean, default=False, server_default="false")
    excluded_reason = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_training_product_included", "product_key", "included_in_training"),
    )


class ValorModel(Base):
    """Registry of trained VALOR models."""
    __tablename__ = "valor_model"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trained_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())
    model_version = Column(Text, nullable=False, unique=True)
    model_filename = Column(Text, nullable=False)
    training_samples = Column(Integer)
    test_samples = Column(Integer)
    mae_sek = Column(Float)
    mape_pct = Column(Float)
    within_10pct = Column(Float)
    within_20pct = Column(Float)
    vs_baseline_mae = Column(Float, nullable=True)
    vs_baseline_improvement_pct = Column(Float, nullable=True)
    feature_importance = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=False, server_default="false")
    min_samples_met = Column(Boolean, default=False, server_default="false")
    data_quality_warnings = Column(ARRAY(Text), nullable=True)
    rolled_back_at = Column(DateTime(timezone=True), nullable=True)
    rolled_back_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_valor_model_active", "is_active", "trained_at"),
    )


class ValorEstimate(Base):
    """Per-valuation VALOR predictions for tracking."""
    __tablename__ = "valor_estimate"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    valuation_id = Column(String, nullable=False, index=True)
    model_version = Column(Text, nullable=False)
    estimated_price_sek = Column(Integer, nullable=False)
    confidence_label = Column(Text, nullable=True)
    mae_at_prediction = Column(Float, nullable=True)
    feature_values = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())

    __table_args__ = (
        Index("idx_valor_estimate_created", "created_at"),
    )


class PriceStatistic(Base):
    """Cached per-product price statistics."""
    __tablename__ = "price_statistic"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_key = Column(Text, nullable=False)
    calculated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())
    median_price = Column(Integer, nullable=True)
    p15_price = Column(Integer, nullable=True)
    p85_price = Column(Integer, nullable=True)
    sample_size = Column(Integer, nullable=True)
    source_breakdown = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_price_stat_product", "product_key", "calculated_at"),
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
