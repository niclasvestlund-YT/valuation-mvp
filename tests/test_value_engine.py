import unittest

from backend.app.core.value_engine import ValueEngine
from backend.app.schemas.product_identification import ProductIdentificationResult


class StubVisionService:
    def __init__(self, result: ProductIdentificationResult) -> None:
        self.result = result

    def detect_product(self, images=None, image=None) -> ProductIdentificationResult:
        return self.result


class StubMarketService:
    def __init__(self, comparables: list[dict] | None = None) -> None:
        self.comparables = comparables or []

    def get_comparables(self, brand: str, model: str, category: str | None = None) -> list[dict]:
        return self.comparables


class StubNewPriceService:
    def __init__(self, payload: dict | None = None) -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self.payload = payload or {
            "estimated_new_price": None,
            "currency": None,
            "confidence": 0.0,
            "source_count": 0,
            "sources": [],
            "method": "unavailable",
        }

    def get_new_price(self, brand: str, model: str, category: str | None = None) -> dict:
        self.calls.append((brand, model, category))
        return self.payload


class StubPricingService:
    def __init__(self, payload: dict | None = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    def calculate_valuation(self, product_identification, used_market_comparables, new_price_estimate=None, condition=None):
        if self.error is not None:
            raise self.error
        return self.payload or {
            "status": "insufficient_evidence",
            "valuation": None,
            "warnings": ["Not enough market evidence to produce a trustworthy valuation"],
            "reasons": ["not_enough_relevant_comparables"],
            "evidence": {
                "comparable_count": 0,
                "sold_comparable_count": 0,
                "active_comparable_count": 0,
                "average_relevance": 0.0,
                "outlier_ratio": 0.0,
            },
        }


class ValueEngineTests(unittest.TestCase):
    def identification(
        self,
        *,
        brand: str = "Apple",
        model: str = "iPhone 13",
        category: str = "smartphone",
        confidence: float = 0.92,
        candidate_models: list[str] | None = None,
        needs_more_images: bool = False,
        source: str = "Vision",
        request_id: str = "test_request",
    ) -> ProductIdentificationResult:
        return ProductIdentificationResult(
            brand=brand,
            line="iPhone",
            model=model,
            category=category,
            variant=None,
            candidate_models=candidate_models or [],
            confidence=confidence,
            reasoning_summary="Test identification",
            needs_more_images=needs_more_images,
            requested_additional_angles=[],
            source=source,
            request_id=request_id,
        )

    def test_pipeline_continues_with_multiple_candidate_models_as_soft_warning(self) -> None:
        """With multiple plausible models, the pipeline runs (not hard-blocked) and surfaces a warning."""
        new_price_service = StubNewPriceService(
            payload={
                "estimated_new_price": None,
                "currency": None,
                "confidence": 0.0,
                "source_count": 0,
                "sources": [],
                "method": "unavailable",
            }
        )
        engine = ValueEngine(
            vision_service=StubVisionService(
                self.identification(confidence=0.84, candidate_models=["iPhone 13 mini"])
            ),
            market_service=StubMarketService(),
            new_price_service=new_price_service,
            pricing_service=StubPricingService(),
        )

        result = engine.value_item(images=["data:image/jpeg;base64,test"])

        # Pipeline now continues for candidate_models (soft warning, not hard block)
        self.assertIn(result["status"], {"insufficient_evidence", "ok"})
        # The soft ambiguity warning must be visible in the response
        all_warnings = result.get("warnings", [])
        self.assertTrue(
            any("möjliga modeller" in w.lower() for w in all_warnings),
            f"Expected multiple-models warning in {all_warnings}",
        )
        self.assertIsNone(result["data"]["price"])
        # Market was looked up
        self.assertTrue(result["debug_summary"]["market_lookup_attempted"])

    def test_returns_ambiguous_model_when_brand_or_model_is_missing(self) -> None:
        """Missing brand/model is the only hard-block that produces ambiguous_model."""
        engine = ValueEngine(
            vision_service=StubVisionService(
                ProductIdentificationResult(
                    brand=None,
                    line=None,
                    model=None,
                    category="smartphone",
                    variant=None,
                    candidate_models=[],
                    confidence=0.3,
                    reasoning_summary="No product recognised.",
                    needs_more_images=True,
                    requested_additional_angles=[],
                    source="Vision",
                    request_id="test_request",
                )
            ),
            market_service=StubMarketService(),
            new_price_service=StubNewPriceService(),
            pricing_service=StubPricingService(),
        )

        result = engine.value_item(images=["data:image/jpeg;base64,test"])

        self.assertEqual(result["status"], "ambiguous_model")
        self.assertIn("missing_brand_or_model", result["reasons"])
        self.assertFalse(result["debug_summary"]["market_lookup_attempted"])

    def test_new_price_context_available_in_insufficient_evidence_response(self) -> None:
        """When pipeline runs but finds no comparables, new_price_data is included in market_data."""
        new_price_service = StubNewPriceService(
            payload={
                "estimated_new_price": 2799,
                "currency": "SEK",
                "confidence": 0.65,
                "source_count": 3,
                "sources": [{"source": "NetOnNet"}, {"source": "Webhallen"}, {"source": "Elgiganten"}],
                "method": "serpapi_google_shopping_median",
            }
        )
        engine = ValueEngine(
            vision_service=StubVisionService(
                self.identification(
                    brand="DJI",
                    model="Osmo Action",
                    category="camera",
                    confidence=0.8,
                    candidate_models=[],
                    needs_more_images=True,
                )
            ),
            market_service=StubMarketService(),
            new_price_service=new_price_service,
            pricing_service=StubPricingService(),
        )

        result = engine.value_item(images=["data:image/jpeg;base64,test"])

        # With brand+model present and no candidate_models, pipeline proceeds
        self.assertEqual(result["status"], "insufficient_evidence")
        # New price context is included in market_data
        new_price = result["data"]["market_data"]["new_price"]
        self.assertEqual(new_price["estimated_new_price"], 2799)
        self.assertEqual(new_price["currency"], "SEK")
        # New price service was called once during market lookup
        self.assertEqual(len(new_price_service.calls), 1)
        # Market was attempted (brand+model were available)
        self.assertTrue(result["debug_summary"]["market_lookup_attempted"])

    def test_returns_insufficient_evidence_when_pricing_gate_fails(self) -> None:
        engine = ValueEngine(
            vision_service=StubVisionService(self.identification()),
            market_service=StubMarketService(
                comparables=[{"title": "Apple iPhone 13 sold", "price": 420, "listing_type": "sold", "source": "Tradera", "raw": {"BidCount": "0"}}]
            ),
            new_price_service=StubNewPriceService(),
            pricing_service=StubPricingService(
                payload={
                    "status": "insufficient_evidence",
                    "valuation": None,
                    "warnings": ["Not enough market evidence to produce a trustworthy valuation"],
                    "reasons": ["not_enough_relevant_comparables"],
                    "evidence": {
                        "comparable_count": 1,
                        "sold_comparable_count": 1,
                        "active_comparable_count": 0,
                        "average_relevance": 0.83,
                        "outlier_ratio": 0.0,
                    },
                }
            ),
        )

        result = engine.value_item(images=["data:image/jpeg;base64,test"])

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIn("not_enough_relevant_comparables", result["reasons"])
        self.assertIsNone(result["data"]["valuation"])
        self.assertEqual(result["data"]["market_data"]["pricing_evidence"]["comparable_count"], 1)
        self.assertTrue(result["debug_summary"]["market_lookup_attempted"])
        self.assertEqual(result["debug_summary"]["total_comparables_fetched"], 1)
        self.assertEqual(result["debug_summary"]["relevant_comparables_kept"], 1)
        self.assertEqual(result["market_snapshot"]["fetched_count"], 1)
        self.assertEqual(result["market_snapshot"]["relevant_count"], 1)
        self.assertEqual(result["market_snapshot"]["sold_count"], 1)

    def test_returns_preliminary_estimate_when_identification_is_strong_but_evidence_is_incomplete(self) -> None:
        engine = ValueEngine(
            vision_service=StubVisionService(
                self.identification(
                    brand="DJI",
                    model="Osmo Action 5 Pro",
                    category="camera",
                    confidence=0.93,
                )
            ),
            market_service=StubMarketService(
                comparables=[
                    {
                        "title": "DJI Osmo Action 5 Pro",
                        "price": 4200,
                        "listing_type": "active",
                        "source": "blocket_serpapi",
                        "url": "https://www.blocket.se/annons/stockholm/dji_osmo_action_5_pro/111",
                        "raw": {"BidCount": "0"},
                    },
                    {
                        "title": "DJI Osmo Action 5 Pro Adventure Combo",
                        "price": 4390,
                        "listing_type": "active",
                        "source": "Tradera",
                        "url": "https://www.tradera.com/item/1000208/111/dji-osmo-action-5-pro-adventure-combo",
                        "raw": {"BidCount": "0"},
                    },
                    {
                        "title": "DJI Osmo Action 5 Pro",
                        "price": 4100,
                        "listing_type": "sold",
                        "source": "Tradera",
                        "url": "https://www.tradera.com/item/1000208/112/dji-osmo-action-5-pro",
                        "raw": {"BidCount": "2", "HasBids": "true"},
                    },
                ]
            ),
            new_price_service=StubNewPriceService(
                payload={
                    "estimated_new_price": 5799,
                    "currency": "SEK",
                    "confidence": 0.66,
                    "source_count": 3,
                    "sources": [{"source": "Webhallen"}, {"source": "NetOnNet"}, {"source": "Elgiganten"}],
                    "method": "serpapi_google_shopping_median",
                }
            ),
            pricing_service=StubPricingService(
                payload={
                    "status": "insufficient_evidence",
                    "valuation": None,
                    "warnings": ["Not enough sold evidence for a normal valuation"],
                    "reasons": ["not_enough_relevant_comparables"],
                    "evidence": {
                        "comparable_count": 2,
                        "sold_comparable_count": 1,
                        "active_comparable_count": 1,
                        "average_relevance": 0.79,
                        "outlier_ratio": 0.0,
                    },
                }
            ),
        )

        result = engine.value_item(images=["data:image/jpeg;base64,test"])

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["data"]["valuation"])
        self.assertIsNotNone(result["data"]["preliminary_estimate"])
        self.assertGreater(result["data"]["preliminary_estimate"]["estimate"], 0)
        self.assertEqual(result["data"]["preliminary_estimate"]["currency"], "SEK")
        self.assertIn("grov uppskattning", result["warnings"][0].lower())
        self.assertEqual(result["market_snapshot"]["fetched_count"], 3)
        self.assertEqual(result["market_snapshot"]["active_count"], 2)
        self.assertEqual(result["market_snapshot"]["sold_count"], 1)

    def test_preliminary_estimate_can_use_single_new_price_source_as_anchor(self) -> None:
        engine = ValueEngine(
            vision_service=StubVisionService(
                self.identification(
                    brand="DJI",
                    model="Osmo Action 5 Pro",
                    category="camera",
                    confidence=0.93,
                )
            ),
            market_service=StubMarketService(
                comparables=[
                    {
                        "title": "DJI Osmo Action 5 Pro med Sandisk Extreme Pro 128GB",
                        "price": 1100,
                        "listing_type": "active",
                        "source": "Tradera",
                        "url": "https://www.tradera.com/item/1000208/111/dji-osmo-action-5-pro-med-sandisk",
                        "raw": {"BidCount": "0"},
                    },
                    {
                        "title": "DJI Osmo Action 5 Pro Standard Combo",
                        "price": 2900,
                        "listing_type": "active",
                        "source": "blocket_serpapi",
                        "url": "https://www.blocket.se/recommerce/forsale/item/21501336",
                        "raw": {"BidCount": "0"},
                    },
                    {
                        "title": "DJI Osmo Action 5 Pro Adventure Combo",
                        "price": 4800,
                        "listing_type": "active",
                        "source": "blocket_serpapi",
                        "url": "https://www.blocket.se/recommerce/forsale/item/21583052",
                        "raw": {"BidCount": "0"},
                    },
                ]
            ),
            new_price_service=StubNewPriceService(
                payload={
                    "estimated_new_price": None,
                    "currency": "SEK",
                    "confidence": 0.2,
                    "source_count": 1,
                    "sources": [{
                        "source": "ActionKing.se",
                        "title": "DJI Osmo Action 5 Pro Standard Actionkamera",
                        "price": 4590.0,
                        "currency": "SEK",
                        "url": "https://example.com/action-5-pro",
                    }],
                    "method": "single_source_insufficient",
                }
            ),
            pricing_service=StubPricingService(
                payload={
                    "status": "insufficient_evidence",
                    "valuation": None,
                    "warnings": ["Not enough sold evidence for a normal valuation"],
                    "reasons": ["no_sold_comparables"],
                    "evidence": {
                        "comparable_count": 3,
                        "sold_comparable_count": 0,
                        "active_comparable_count": 3,
                        "average_relevance": 0.68,
                        "outlier_ratio": 0.0,
                    },
                }
            ),
        )

        result = engine.value_item(images=["data:image/jpeg;base64,test"])

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNotNone(result["data"]["preliminary_estimate"])
        self.assertEqual(result["data"]["preliminary_estimate"]["new_price_anchor"], 4590)
        self.assertGreater(result["data"]["preliminary_estimate"]["estimate"], 0)
        self.assertIn("grov uppskattning", result["warnings"][0].lower())

    def test_returns_ok_when_pricing_returns_market_backed_valuation(self) -> None:
        engine = ValueEngine(
            vision_service=StubVisionService(self.identification()),
            market_service=StubMarketService(
                comparables=[
                    {"title": "Apple iPhone 13 sold", "price": 420, "listing_type": "sold", "source": "Tradera", "raw": {"BidCount": "0"}},
                    {"title": "Apple iPhone 13 sold", "price": 430, "listing_type": "sold", "source": "Tradera", "raw": {"BidCount": "1"}},
                    {"title": "Apple iPhone 13 active", "price": 440, "listing_type": "active", "source": "Tradera", "raw": {"BidCount": "0"}},
                ]
            ),
            new_price_service=StubNewPriceService(
                payload={
                    "estimated_new_price": 8299,
                    "currency": "SEK",
                    "confidence": 0.75,
                    "source_count": 2,
                    "sources": [{"source": "Webhallen"}, {"source": "Elgiganten"}],
                    "method": "serpapi_google_shopping_median",
                }
            ),
            pricing_service=StubPricingService(
                payload={
                    "status": "ok",
                    "valuation": {
                        "low_estimate": 410,
                        "fair_estimate": 425,
                        "high_estimate": 440,
                        "confidence": 0.81,
                        "currency": "SEK",
                        "evidence_summary": "Used 3 relevant comparables.",
                        "valuation_method": "relevance_weighted_median_with_robust_outlier_filter",
                        "comparable_count": 3,
                        "source_breakdown": {
                            "sold_listings": 2,
                            "active_listings": 1,
                            "outliers_removed": 0,
                            "used_new_price": True,
                        },
                    },
                    "warnings": [],
                    "reasons": [],
                    "evidence": {
                        "comparable_count": 3,
                        "sold_comparable_count": 2,
                        "active_comparable_count": 1,
                        "average_relevance": 0.84,
                        "outlier_ratio": 0.0,
                        "pricing_confidence": 0.81,
                    },
                }
            ),
        )

        result = engine.value_item(images=["data:image/jpeg;base64,test"])

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["price"], 425)
        self.assertEqual(result["data"]["valuation"]["confidence"], 0.81)
        self.assertIn("Webhallen", result["data"]["sources"])
        self.assertTrue(result["debug_summary"]["market_lookup_attempted"])
        self.assertEqual(result["debug_summary"]["total_comparables_fetched"], 3)
        self.assertEqual(result["debug_summary"]["relevant_comparables_kept"], 3)
        self.assertEqual(result["market_snapshot"]["fetched_count"], 3)
        self.assertEqual(result["market_snapshot"]["sold_count"], 2)
        self.assertEqual(result["market_snapshot"]["active_count"], 1)
        self.assertEqual(result["market_snapshot"]["bidding_count"], 1)

    def test_returns_degraded_when_valuation_pipeline_raises(self) -> None:
        engine = ValueEngine(
            vision_service=StubVisionService(self.identification()),
            market_service=StubMarketService(),
            new_price_service=StubNewPriceService(),
            pricing_service=StubPricingService(error=RuntimeError("pricing failure")),
        )

        result = engine.value_item(images=["data:image/jpeg;base64,test"])

        self.assertEqual(result["status"], "degraded")
        self.assertIn("valuation_pipeline_failure", result["reasons"])
        self.assertIsNone(result["data"]["price"])
        self.assertTrue(result["debug_summary"]["market_lookup_attempted"])

    def test_condition_is_forwarded_to_pricing_service(self) -> None:
        """condition= passed to value_item must reach calculate_valuation."""
        received: list[str | None] = []

        class CapturingPricingService:
            def calculate_valuation(self, product_identification, used_market_comparables, new_price_estimate=None, condition=None):
                received.append(condition)
                return {
                    "status": "insufficient_evidence",
                    "valuation": None,
                    "warnings": [],
                    "reasons": ["not_enough_relevant_comparables"],
                    "evidence": {"comparable_count": 0, "sold_comparable_count": 0, "active_comparable_count": 0, "average_relevance": 0.0, "outlier_ratio": 0.0},
                }

        engine = ValueEngine(
            vision_service=StubVisionService(self.identification()),
            market_service=StubMarketService(),
            new_price_service=StubNewPriceService(),
            pricing_service=CapturingPricingService(),
        )

        engine.value_item(images=["data:image/jpeg;base64,test"], condition="poor")

        self.assertEqual(received, ["poor"])

    def test_enrich_envelope_ok_status(self) -> None:
        from backend.app.api.value import enrich_envelope

        payload = enrich_envelope({
            "status": "ok",
            "data": {
                "brand": "Apple",
                "model": "iPhone 13",
                "category": "smartphone",
                "confidence": 0.94,
                "valuation": {"fair_estimate": 430, "evidence_summary": "3 comparables."},
                "market_data": None,
                "sources": ["Tradera"],
                "line": None, "variant": None, "candidate_models": [],
                "reasoning_summary": None, "needs_more_images": False,
                "requested_additional_angles": [], "price": 430, "preliminary_estimate": None,
            },
            "warnings": [],
            "reasons": [],
            "debug_id": "test_ok",
        })

        self.assertEqual(payload["status_title"], "Begagnatvärde uppskattat")
        self.assertEqual(payload["user_status_title"], "Begagnatvärdet är klart")
        self.assertTrue(payload["user_explanation"])

    def test_enrich_envelope_ambiguous_status(self) -> None:
        from backend.app.api.value import enrich_envelope

        payload = enrich_envelope({
            "status": "ambiguous_model",
            "data": {
                "brand": "Apple", "model": None, "category": "smartphone",
                "confidence": 0.4, "valuation": None, "market_data": None, "sources": [],
                "line": None, "variant": None, "candidate_models": [],
                "reasoning_summary": None, "needs_more_images": True,
                "requested_additional_angles": ["back", "front"], "price": None,
            },
            "warnings": [],
            "reasons": ["missing_brand_or_model"],
            "debug_id": "test_ambiguous",
        })

        self.assertEqual(payload["status_title"], "Fler bilder behövs")
        self.assertIn("back", payload["recommended_action"])

    def test_enrich_envelope_adds_reason_details(self) -> None:
        from backend.app.api.value import enrich_envelope

        payload = enrich_envelope({
            "status": "insufficient_evidence",
            "data": None,
            "warnings": [],
            "reasons": ["no_relevant_comparables", "cannot_value_from_new_price_only"],
            "debug_id": "test_reasons",
        })

        self.assertEqual(len(payload["reason_details"]), 2)
        self.assertTrue(all(payload["reason_details"]))

    def test_enrich_envelope_deduplicates_reasons_and_warnings(self) -> None:
        from backend.app.api.value import enrich_envelope

        payload = enrich_envelope({
            "status": "ok",
            "data": None,
            "warnings": ["duplicate warning", "duplicate warning", "unique warning"],
            "reasons": ["dup_reason", "dup_reason"],
            "debug_id": "test_dedup",
        })

        self.assertEqual(len(payload["warnings"]), 2)
        self.assertEqual(len(payload["reasons"]), 1)

    def test_enrich_envelope_adds_user_facing_fields(self) -> None:
        from backend.app.api.value import enrich_envelope

        payload = enrich_envelope({
            "status": "insufficient_evidence",
            "data": {
                "brand": "DJI",
                "line": "Osmo",
                "model": "Action",
                "category": "camera",
                "variant": None,
                "candidate_models": [],
                "confidence": 0.86,
                "reasoning_summary": "Test",
                "needs_more_images": False,
                "requested_additional_angles": [],
                "price": None,
                "valuation": None,
                "market_data": None,
                "sources": [],
            },
            "warnings": [],
            "reasons": ["not_enough_relevant_comparables"],
            "market_snapshot": {
                "fetched_count": 12,
                "relevant_count": 1,
                "sold_count": 0,
                "active_count": 12,
                "bidding_count": 0,
                "accessory_like_count": 2,
                "bundle_like_count": 1,
            },
            "debug_id": "test_debug",
        })

        self.assertEqual(payload["user_status_title"], "Underlaget räcker inte för begagnatvärde")
        self.assertIn("Vi hittade 12 annonser", payload["user_explanation"])
        self.assertTrue(payload["recommended_action"])


if __name__ == "__main__":
    unittest.main()
