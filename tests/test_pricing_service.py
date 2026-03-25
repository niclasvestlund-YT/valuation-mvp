import unittest

from backend.app.schemas.product_identification import ProductIdentificationResult
from backend.app.services.comparable_scoring import score_comparable_relevance
from backend.app.services.pricing_service import PricingService


class PricingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PricingService()

    def identification(
        self,
        *,
        brand: str = "Apple",
        line: str = "iPhone",
        model: str,
        category: str = "smartphone",
        variant: str | None = None,
        confidence: float = 0.9,
        candidate_models: list[str] | None = None,
    ) -> ProductIdentificationResult:
        return ProductIdentificationResult(
            brand=brand,
            line=line,
            model=model,
            category=category,
            variant=variant,
            candidate_models=candidate_models or [],
            confidence=confidence,
            reasoning_summary="Test identification",
            needs_more_images=False,
            requested_additional_angles=[],
            source="Test",
            request_id="test_request",
        )

    def comparable(self, title: str, price: int, listing_type: str = "sold") -> dict:
        return {
            "title": title,
            "price": price,
            "listing_type": listing_type,
            "source": "test_market",
        }

    def test_strong_exact_model_listing_scores_high(self) -> None:
        score = score_comparable_relevance(
            self.comparable("Apple iPhone 13 128GB sold", 430),
            self.identification(model="iPhone 13"),
        )

        self.assertFalse(score.hard_reject)
        self.assertGreaterEqual(score.score, 0.8)
        self.assertIn("exact_model_match", score.reasons)

    def test_generic_family_listing_scores_low(self) -> None:
        score = score_comparable_relevance(
            self.comparable("Apple iPhone sold", 410),
            self.identification(model="iPhone 13"),
        )

        self.assertFalse(score.hard_reject)
        self.assertLess(score.score, 0.55)
        self.assertIn("missing_exact_model_match", score.reasons)

    def test_alternative_model_listing_is_rejected(self) -> None:
        score = score_comparable_relevance(
            self.comparable("Sony WH-1000XM5 sold", 240),
            self.identification(
                brand="Sony",
                line="WH-1000X",
                model="WH-1000XM4",
                category="headphones",
                candidate_models=["WH-1000XM5", "WH-XB910N"],
            ),
        )

        self.assertTrue(score.hard_reject)
        self.assertEqual(score.score, 0.0)
        self.assertIn("matched_alternative_candidate_model", score.reasons)

    def test_junk_listing_is_rejected(self) -> None:
        score = score_comparable_relevance(
            self.comparable("Apple iPhone 13 for parts locked", 99),
            self.identification(model="iPhone 13"),
        )

        self.assertTrue(score.hard_reject)
        self.assertEqual(score.score, 0.0)
        self.assertIn("listing_for_parts", score.reasons)
        self.assertIn("listing_locked", score.reasons)

    def test_exact_osmo_action_match_scores_high(self) -> None:
        score = score_comparable_relevance(
            self.comparable("DJI Osmo Action 4 sold", 2500),
            self.identification(
                brand="DJI",
                line="Osmo",
                model="Osmo Action 4",
                category="camera",
            ),
        )

        self.assertFalse(score.hard_reject)
        self.assertGreaterEqual(score.score, 0.8)
        self.assertIn("exact_model_match", score.reasons)

    def test_osmo_action_4_vs_generic_osmo_action_is_downgraded(self) -> None:
        score = score_comparable_relevance(
            self.comparable("DJI Osmo Action 4 sold", 2500),
            self.identification(
                brand="DJI",
                line="Osmo",
                model="Osmo Action",
                category="camera",
            ),
        )

        self.assertFalse(score.hard_reject)
        self.assertLess(score.score, 0.55)
        self.assertIn("osmo_generation_specific_for_broad_target", score.reasons)

    def test_osmo_pocket_mismatch_is_rejected(self) -> None:
        score = score_comparable_relevance(
            self.comparable("DJI Osmo Pocket 3 sold", 4200),
            self.identification(
                brand="DJI",
                line="Osmo",
                model="Osmo Action 4",
                category="camera",
            ),
        )

        self.assertTrue(score.hard_reject)
        self.assertEqual(score.score, 0.0)
        self.assertIn("osmo_family_mismatch", score.reasons)

    def test_adventure_combo_is_downgraded_for_plain_osmo_model(self) -> None:
        plain_score = score_comparable_relevance(
            self.comparable("DJI Osmo Action 4 sold", 2500),
            self.identification(
                brand="DJI",
                line="Osmo",
                model="Osmo Action 4",
                category="camera",
            ),
        )
        combo_score = score_comparable_relevance(
            self.comparable("DJI Osmo Action 4 Adventure Combo sold", 2741),
            self.identification(
                brand="DJI",
                line="Osmo",
                model="Osmo Action 4",
                category="camera",
            ),
        )

        self.assertFalse(combo_score.hard_reject)
        self.assertLess(combo_score.score, plain_score.score)
        self.assertIn("bundle_variant_for_plain_target", combo_score.reasons)

    def test_camera_listing_with_extra_accessories_is_downgraded(self) -> None:
        plain_score = score_comparable_relevance(
            self.comparable("DJI Osmo Action 5 Pro sold", 4100),
            self.identification(
                brand="DJI",
                line="Osmo",
                model="Action 5 Pro",
                category="camera",
            ),
        )
        bundle_score = score_comparable_relevance(
            self.comparable("DJI Osmo Action 5 Pro med Sandisk Extreme Pro 128GB", 1100, listing_type="active"),
            self.identification(
                brand="DJI",
                line="Osmo",
                model="Action 5 Pro",
                category="camera",
            ),
        )

        self.assertFalse(bundle_score.hard_reject)
        self.assertLess(bundle_score.score, plain_score.score)
        self.assertIn("bundle_variant_for_plain_target", bundle_score.reasons)

    def test_sparse_data_returns_insufficient_evidence(self) -> None:
        result = self.service.calculate_valuation(
            product_identification=self.identification(model="iPhone 13"),
            used_market_comparables=[
                self.comparable("Apple iPhone 13 128GB sold", 430),
            ],
            new_price_estimate={"estimated_new_price": 799, "currency": "USD"},
        )

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["valuation"])
        self.assertIn("not_enough_relevant_comparables", result["reasons"])
        self.assertEqual(result["evidence"]["comparable_count"], 1)

    def test_outlier_heavy_data_returns_ok(self) -> None:
        result = self.service.calculate_valuation(
            product_identification=self.identification(model="iPhone 13"),
            used_market_comparables=[
                self.comparable("Apple iPhone 13 sold", 420),
                self.comparable("Apple iPhone 13 sold", 430),
                self.comparable("Apple iPhone 13 sold", 440),
                self.comparable("Apple iPhone 13 sold", 1180),
                self.comparable("Apple iPhone 13 active", 1250, listing_type="active"),
            ],
            new_price_estimate={"estimated_new_price": 799, "currency": "USD"},
        )

        self.assertEqual(result["status"], "ok")
        self.assertLess(result["valuation"]["fair_estimate"], 600)
        self.assertEqual(result["valuation"]["source_breakdown"]["outliers_removed"], 2)

    def test_active_only_comparables_are_accepted_as_valid_evidence(self) -> None:
        """MIN_SOLD_COMPARABLES=0: active-only listings are valid market data."""
        result = self.service.calculate_valuation(
            product_identification=self.identification(model="iPhone 13"),
            used_market_comparables=[
                self.comparable("Apple iPhone 13 active", 420, listing_type="active"),
                self.comparable("Apple iPhone 13 active", 430, listing_type="active"),
                self.comparable("Apple iPhone 13 active", 440, listing_type="active"),
            ],
            new_price_estimate={"estimated_new_price": 799, "currency": "USD"},
        )

        # Active listings are valid with MIN_SOLD_COMPARABLES=0 — pipeline returns ok
        self.assertEqual(result["status"], "ok")
        self.assertIsNotNone(result["valuation"])
        self.assertEqual(result["valuation"]["source_breakdown"]["sold_listings"], 0)
        self.assertEqual(result["valuation"]["source_breakdown"]["active_listings"], 3)

    def test_candidate_model_ambiguity_caps_pricing_confidence(self) -> None:
        result = self.service.calculate_valuation(
            product_identification=self.identification(
                model="iPhone 13",
                confidence=0.92,
                candidate_models=["iPhone 13 mini"],
            ),
            used_market_comparables=[
                self.comparable("Apple iPhone 13 sold", 420),
                self.comparable("Apple iPhone 13 sold", 425),
                self.comparable("Apple iPhone 13 sold", 430),
                self.comparable("Apple iPhone 13 active", 435, listing_type="active"),
            ],
            new_price_estimate={"estimated_new_price": 799, "currency": "USD"},
        )

        self.assertEqual(result["status"], "ok")
        self.assertLessEqual(result["valuation"]["confidence"], 0.78)

    def test_new_price_only_returns_insufficient_evidence(self) -> None:
        result = self.service.calculate_valuation(
            product_identification=self.identification(model="iPhone 13"),
            used_market_comparables=[],
            new_price_estimate={"estimated_new_price": 799, "currency": "USD"},
        )

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["valuation"])
        self.assertIn("no_relevant_comparables", result["reasons"])
        self.assertIn("cannot_value_from_new_price_only", result["reasons"])

    def test_strong_evidence_case_returns_ok(self) -> None:
        result = self.service.calculate_valuation(
            product_identification=self.identification(model="iPhone 13", confidence=0.94),
            used_market_comparables=[
                self.comparable("Apple iPhone 13 128GB sold", 420),
                self.comparable("Apple iPhone 13 128GB sold", 425),
                self.comparable("Apple iPhone 13 128GB sold", 430),
                self.comparable("Apple iPhone 13 128GB sold", 435),
                self.comparable("Apple iPhone 13 128GB sold", 440),
                self.comparable("Apple iPhone 13 active listing", 445, listing_type="active"),
            ],
            new_price_estimate={"estimated_new_price": 799, "currency": "USD"},
        )

        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["valuation"]["confidence"], 0.75)
        self.assertGreaterEqual(result["valuation"]["fair_estimate"], 425)
        self.assertLessEqual(result["valuation"]["fair_estimate"], 440)


if __name__ == "__main__":
    unittest.main()
