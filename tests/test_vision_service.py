import json
import unittest

from backend.app.services.vision_service import VisionService, logger


class VisionServiceValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = VisionService(api_key="test-key", model="test-model")

    def payload(
        self,
        *,
        brand: str | None,
        line: str | None,
        model: str | None,
        category: str | None,
        variant: str | None,
        candidate_models: list[str],
        confidence: float,
        reasoning_summary: str,
        needs_more_images: bool = False,
        requested_additional_angles: list[str] | None = None,
    ) -> dict:
        return {
            "output_text": json.dumps(
                {
                    "brand": brand,
                    "line": line,
                    "model": model,
                    "category": category,
                    "variant": variant,
                    "candidate_models": candidate_models,
                    "confidence": confidence,
                    "reasoning_summary": reasoning_summary,
                    "needs_more_images": needs_more_images,
                    "requested_additional_angles": requested_additional_angles or [],
                }
            )
        }

    def test_parse_response_logs_raw_output_and_removes_primary_candidate(self) -> None:
        payload = self.payload(
            brand="Sony",
            line="WH-1000X",
            model="WH-1000XM4",
            category="headphones",
            variant=None,
            candidate_models=["WH-1000XM4", "WH-1000XM5"],
            confidence=0.96,
            reasoning_summary="Visible model text on the inside headband and Sony logo on the earcup.",
        )

        with self.assertLogs(logger.name, level="INFO") as logs:
            identification = self.service._parse_response(payload, request_id="vision_test_1", image_count=2)

        self.assertTrue(any("vision.identify.raw_output" in entry for entry in logs.output))
        self.assertEqual(identification.candidate_models, ["WH-1000XM5"])
        self.assertEqual(identification.confidence, 0.96)
        self.assertFalse(identification.needs_more_images)
        self.assertEqual(identification.requested_additional_angles, [])

    def test_single_generic_phone_image_is_capped_and_requests_angles(self) -> None:
        payload = self.payload(
            brand="Apple",
            line="iPhone",
            model="iPhone 13",
            category="smartphone",
            variant=None,
            candidate_models=["iPhone 13 Pro", "iPhone 12"],
            confidence=0.72,
            reasoning_summary="Apple logo and camera module are visible, but no model number is readable.",
        )

        identification = self.service._parse_response(payload, request_id="vision_test_2", image_count=1)

        self.assertEqual(identification.confidence, 0.69)
        self.assertTrue(identification.needs_more_images)
        self.assertEqual(
            identification.requested_additional_angles,
            ["back camera module", "charging port / bottom edge", "screen-on showing UI", "model text/IMEI area"],
        )

    def test_conflicting_headphone_clues_reduce_confidence(self) -> None:
        payload = self.payload(
            brand="Sony",
            line="WH-1000X",
            model="WH-1000XM4",
            category="headphones",
            variant=None,
            candidate_models=["WH-1000XM4", "WH-1000XM5", "WH-1000XM3"],
            confidence=0.86,
            reasoning_summary="Sony logo is visible, but the hinge design conflicts with WH-1000XM4.",
        )

        identification = self.service._parse_response(payload, request_id="vision_test_3", image_count=2)

        self.assertEqual(identification.candidate_models, ["WH-1000XM5", "WH-1000XM3"])
        self.assertEqual(identification.confidence, 0.74)
        self.assertTrue(identification.needs_more_images)
        self.assertEqual(
            identification.requested_additional_angles,
            ["inside headband", "hinge", "earcup buttons/ports", "case", "model text"],
        )

    def test_missing_concrete_evidence_lowers_laptop_confidence(self) -> None:
        payload = self.payload(
            brand="Apple",
            line="MacBook Air",
            model="MacBook Air M2",
            category="laptop",
            variant="13-inch",
            candidate_models=[],
            confidence=0.88,
            reasoning_summary="Looks like a MacBook Air based on overall appearance.",
        )

        identification = self.service._parse_response(payload, request_id="vision_test_4", image_count=2)

        self.assertEqual(identification.confidence, 0.69)
        self.assertTrue(identification.needs_more_images)
        self.assertEqual(
            identification.requested_additional_angles,
            ["bottom label", "ports (left side)", "keyboard/trackpad", "model text"],
        )


if __name__ == "__main__":
    unittest.main()
