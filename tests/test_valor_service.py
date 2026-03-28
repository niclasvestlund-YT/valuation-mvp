"""Tests for VALOR ML pricing service."""

import importlib
import os
import tempfile
import unittest
from unittest.mock import patch


class TestValorService(unittest.TestCase):

    def test_valor_returns_none_without_model(self):
        """Without model files, predict() should return None."""
        # Ensure no mock mode
        with patch.dict(os.environ, {"USE_MOCK_VALOR": "false"}, clear=False):
            from backend.app.services.valor_service import ValorService
            svc = ValorService()
            svc.model = None
            svc.features = None
            result = svc.predict("sony_wh-1000xm4", condition="good")
            self.assertIsNone(result)

    def test_valor_mock_mode(self):
        """With USE_MOCK_VALOR=true, predict() should return a dict."""
        with patch.dict(os.environ, {"USE_MOCK_VALOR": "true"}, clear=False):
            from backend.app.services.valor_service import ValorService
            svc = ValorService()
            # Force model to appear available
            svc.model = "fake"
            svc.features = ["condition_encoded"]
            result = svc.predict("sony_wh-1000xm4", condition="good")
            self.assertIsNotNone(result)
            self.assertEqual(result["estimated_price_sek"], 2500)
            self.assertEqual(result["confidence_label"], "low")
            self.assertEqual(result["model_version"], "mock")

    def test_valor_does_not_crash_on_bad_input(self):
        """predict() with None/None should return None, never crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {"USE_MOCK_VALOR": "false", "VALOR_MODEL_DIR": tmpdir},
                clear=False,
            ):
                import backend.app.services.valor_service as vs
                importlib.reload(vs)
                svc = vs.ValorService()
                result = svc.predict(None, None)
                self.assertIsNone(result)
                importlib.reload(vs)

    def test_valor_is_not_available_without_model(self):
        """is_available() should be False without loaded model."""
        from backend.app.services.valor_service import ValorService
        svc = ValorService()
        svc.model = None
        self.assertFalse(svc.is_available())

    def test_valor_sanity_check_rejects_extreme_predictions(self):
        """Predictions <50 or >200000 should be filtered to None."""
        from backend.app.services.valor_service import ValorService
        with patch.dict(os.environ, {"USE_MOCK_VALOR": "false"}, clear=False):
            svc = ValorService()

            # Mock a model that returns 10 (too low)
            class FakeModel:
                def predict(self, X):
                    return [10.0]

            svc.model = FakeModel()
            svc.features = [
                "condition_encoded", "month_of_year", "days_since_observation",
                "price_to_new_ratio", "is_sold_int", "listing_type_fixed",
                "listing_type_auction", "source_valuation", "source_crawler",
                "source_agent",
            ]
            result = svc.predict("test_product")
            self.assertIsNone(result)

    def test_valor_condition_map(self):
        """Verify condition encoding values."""
        from backend.app.services.valor_service import CONDITION_MAP
        self.assertEqual(CONDITION_MAP["like_new"], 1.0)
        self.assertEqual(CONDITION_MAP["good"], 0.8)
        self.assertEqual(CONDITION_MAP["unknown"], 0.5)
        self.assertEqual(CONDITION_MAP["poor"], 0.3)

    def test_valor_reload_does_not_crash(self):
        """reload_model() should never crash."""
        from backend.app.services.valor_service import ValorService
        svc = ValorService()
        svc.reload_model()  # Should not raise


if __name__ == "__main__":
    unittest.main()
