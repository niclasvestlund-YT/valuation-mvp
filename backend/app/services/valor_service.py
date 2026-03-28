"""
VALOR ML pricing service — experimental XGBoost-based price prediction.

IMPORTANT: Every operation is wrapped in try/except.
This service must NEVER crash or propagate exceptions to the value engine.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

MODELS_DIR = Path(os.getenv("VALOR_MODEL_DIR", str(Path(__file__).resolve().parents[3] / "models")))
MODEL_PATH = MODELS_DIR / "valor_latest.pkl"
FEATURES_PATH = MODELS_DIR / "valor_features.json"

CONDITION_MAP = {
    "like_new": 1.0,
    "excellent": 0.9,
    "good": 0.8,
    "used": 0.6,
    "fair": 0.5,
    "poor": 0.3,
    "unknown": 0.5,
}

MIN_PREDICTION = 50
MAX_PREDICTION = 200_000


class ValorService:
    """Singleton wrapper for VALOR XGBoost model."""

    def __init__(self):
        self.model = None
        self.features: list[str] | None = None
        self.model_version: str | None = None
        self.mae_at_load: float | None = None
        self._loaded_at: str | None = None
        self._training_sample_count: int = 0
        self._load_model()

    def _load_model(self):
        """Load model and features from disk. Never raises."""
        try:
            if not MODEL_PATH.exists() or not FEATURES_PATH.exists():
                logger.info("valor.no_model — collecting training data")
                return

            import joblib
            self.model = joblib.load(MODEL_PATH)
            self.features = json.loads(FEATURES_PATH.read_text())
            self.model_version = "valor_latest"

            # Try to read MAE from active model in DB
            try:
                from backend.app.db.database import async_session
                from backend.app.db.models import ValorModel
                import asyncio

                async def _get_mae():
                    async with async_session() as session:
                        from sqlalchemy import select
                        result = await session.execute(
                            select(ValorModel.mae_sek, ValorModel.model_version,
                                   ValorModel.training_samples)
                            .where(ValorModel.is_active.is_(True))
                            .order_by(ValorModel.trained_at.desc())
                            .limit(1)
                        )
                        row = result.first()
                        if row:
                            self.mae_at_load = row[0]
                            self.model_version = row[1]
                            self._training_sample_count = row[2] or 0

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    pass  # Can't await in sync init — mae_at_load stays None
                else:
                    asyncio.run(_get_mae())
            except Exception:
                pass  # DB not available — fine

            self._loaded_at = datetime.utcnow().isoformat()
            logger.info("valor.model_loaded", extra={
                "version": self.model_version,
                "features": len(self.features) if self.features else 0,
                "mae": self.mae_at_load,
            })
        except Exception as exc:
            logger.error(f"valor.load_failed: {exc}")
            self.model = None
            self.features = None

    def reload_model(self):
        """Reload model from disk — call after training completes."""
        self.model = None
        self.features = None
        self.model_version = None
        self._load_model()
        logger.info("valor.model.reloaded", extra={
            "available": self.is_available(),
            "version": self.model_version,
        })

    def is_available(self) -> bool:
        return self.model is not None and self.features is not None

    def predict(
        self,
        product_key: str,
        condition: str = "unknown",
        price_to_new_ratio: float | None = None,
        is_sold: bool = False,
        listing_type: str = "unknown",
    ) -> dict | None:
        """
        Predict price for a product. Returns dict or None.
        NEVER raises — all errors caught internally.
        """
        try:
            # Mock mode — does NOT require a real model file
            if os.getenv("USE_MOCK_VALOR", "").lower() == "true":
                return {
                    "estimated_price_sek": 2500,
                    "confidence_label": "low",
                    "model_version": "mock",
                    "mae_at_prediction": 500.0,
                    "feature_values": {},
                    "is_mock": True,
                }

            if not self.is_available():
                return None

            fv = {
                "condition_encoded": CONDITION_MAP.get(condition, 0.5),
                "month_of_year": datetime.now().month,
                "days_since_observation": 0,
                "price_to_new_ratio": min(max(price_to_new_ratio or 0.6, 0.1), 1.0),
                "is_sold_int": 1 if is_sold else 0,
                "listing_type_fixed": 1 if listing_type == "fixed" else 0,
                "listing_type_auction": 1 if listing_type == "auction" else 0,
                "source_valuation": 0,
                "source_crawler": 0,
                "source_agent": 0,
            }

            X = [[fv.get(f, 0) for f in self.features]]
            raw_pred = float(self.model.predict(X)[0])

            # Sanity check
            if raw_pred < MIN_PREDICTION or raw_pred > MAX_PREDICTION:
                logger.warning(f"valor.bad_prediction: {raw_pred} for {product_key}")
                return None

            # Round to nearest 50 kr
            prediction = round(raw_pred / 50) * 50

            # Confidence based on model's MAE
            mae = self.mae_at_load or 999
            confidence_label = (
                "high" if mae < 300 else
                "medium" if mae < 700 else
                "low"
            )

            return {
                "estimated_price_sek": prediction,
                "confidence_label": confidence_label,
                "model_version": self.model_version,
                "mae_at_prediction": mae,
                "feature_values": fv,
            }
        except Exception as exc:
            logger.error(f"valor.predict_failed: {exc}")
            return None
