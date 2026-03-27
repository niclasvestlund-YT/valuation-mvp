"""Tests for VALOR Prisassistent conversation layer.

Tests the assistant_context generation logic: phase derivation,
quick reply structure, confirmation normalization, and guardrails.
"""

import unittest

from backend.app.schemas.assistant import AssistantContext, QuickReply
from backend.app.services.assistant_flow import (
    build_assistant_context as _build_assistant_context,
    enrich_envelope,
    is_bundle_eligible as _is_bundle_eligible,
    normalize_confirmation as _normalize_confirmation,
)


# ─── Confirmation normalization ───


class TestNormalizeConfirmation(unittest.TestCase):

    def test_yes_exact(self):
        self.assertEqual(_normalize_confirmation("yes"), "yes")

    def test_ja_swedish(self):
        self.assertEqual(_normalize_confirmation("ja"), "yes")

    def test_japp_swedish(self):
        self.assertEqual(_normalize_confirmation("japp"), "yes")

    def test_stammer_swedish(self):
        self.assertEqual(_normalize_confirmation("stämmer"), "yes")

    def test_korrekt_swedish(self):
        self.assertEqual(_normalize_confirmation("korrekt"), "yes")

    def test_no_exact(self):
        self.assertEqual(_normalize_confirmation("no"), "no")

    def test_nej_swedish(self):
        self.assertEqual(_normalize_confirmation("nej"), "no")

    def test_fel_swedish(self):
        self.assertEqual(_normalize_confirmation("fel"), "no")

    def test_none_returns_none(self):
        self.assertIsNone(_normalize_confirmation(None))

    def test_empty_returns_none(self):
        self.assertIsNone(_normalize_confirmation(""))

    def test_unrecognized_returns_none(self):
        self.assertIsNone(_normalize_confirmation("maybe"))
        self.assertIsNone(_normalize_confirmation("kanske"))
        self.assertIsNone(_normalize_confirmation("abc123"))

    def test_case_insensitive(self):
        self.assertEqual(_normalize_confirmation("JA"), "yes")
        self.assertEqual(_normalize_confirmation("NEJ"), "no")
        self.assertEqual(_normalize_confirmation("Yes"), "yes")

    def test_whitespace_stripped(self):
        self.assertEqual(_normalize_confirmation("  ja  "), "yes")
        self.assertEqual(_normalize_confirmation("  nej  "), "no")


# ─── Phase derivation ───


class TestBuildAssistantContext(unittest.TestCase):

    def test_ok_status_no_confirmation_is_confirming(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony", "model": "WH-1000XM4"}, None, True)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.phase, "confirming")
        self.assertIn("Sony", ctx.prompt)

    def test_confirmation_yes_without_condition_is_awaiting_condition(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony"}, "yes", True)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.phase, "awaiting_condition")

    def test_confirmation_yes_with_condition_no_shipping_is_awaiting_shipping(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony"}, "yes", True, condition="good")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.phase, "awaiting_shipping")

    def test_confirmation_yes_condition_shipping_no_goal_is_awaiting_goal(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony"}, "yes", True, condition="good", shipping="can_ship")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.phase, "awaiting_goal")

    def test_confirmation_yes_all_fields_is_ready(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony"}, "yes", True, condition="good", shipping="can_ship", goal="balanced")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.phase, "ready")

    def test_confirmation_no_is_correcting(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony"}, "no", True)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.phase, "correcting")

    def test_ambiguous_model_is_correcting(self):
        ctx = _build_assistant_context("ambiguous_model", {"requested_additional_angles": ["baksida"]}, None, True)
        self.assertEqual(ctx.phase, "correcting")
        self.assertIn("baksida", ctx.prompt)

    def test_insufficient_evidence_is_correcting(self):
        ctx = _build_assistant_context("insufficient_evidence", {"brand": "Canon", "model": "EOS R6"}, None, True)
        self.assertEqual(ctx.phase, "correcting")

    def test_degraded_returns_none(self):
        ctx = _build_assistant_context("degraded", None, None, True)
        self.assertIsNone(ctx)

    def test_error_returns_none(self):
        ctx = _build_assistant_context("error", None, None, True)
        self.assertIsNone(ctx)

    def test_no_images_no_confirmation_is_unsupported(self):
        ctx = _build_assistant_context("ok", None, None, False)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.phase, "unsupported")
        self.assertIsNotNone(ctx.guardrail_message)

    def test_depreciation_estimate_is_confirming(self):
        ctx = _build_assistant_context("depreciation_estimate", {"brand": "Sony"}, None, True)
        self.assertEqual(ctx.phase, "confirming")


# ─── Quick replies structure ───


class TestQuickReplies(unittest.TestCase):

    def test_confirming_has_yes_and_no(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony"}, None, True)
        actions = [qr.action for qr in ctx.quick_replies]
        self.assertIn("confirm_yes", actions)
        self.assertIn("confirm_no", actions)

    def test_confirm_yes_payload(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony"}, None, True)
        yes_qr = [qr for qr in ctx.quick_replies if qr.action == "confirm_yes"][0]
        self.assertEqual(yes_qr.payload, {"confirmation": "yes"})

    def test_correcting_has_add_images(self):
        ctx = _build_assistant_context("ambiguous_model", {}, None, True)
        actions = [qr.action for qr in ctx.quick_replies]
        self.assertIn("add_images", actions)

    def test_ready_has_start_over(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship", goal="balanced")
        actions = [qr.action for qr in ctx.quick_replies]
        self.assertIn("start_over", actions)

    def test_unsupported_has_start_over(self):
        ctx = _build_assistant_context("ok", None, None, False)
        actions = [qr.action for qr in ctx.quick_replies]
        self.assertIn("start_over", actions)

    def test_all_quick_replies_have_labels(self):
        """Every quick reply must have a non-empty Swedish label."""
        for status in ["ok", "ambiguous_model", "insufficient_evidence"]:
            ctx = _build_assistant_context(status, {"brand": "Test"}, None, True)
            if ctx:
                for qr in ctx.quick_replies:
                    self.assertTrue(len(qr.label) > 0, f"Empty label for {status}/{qr.action}")


# ─── Integration with enrich_envelope ───


class TestEnrichEnvelopeAssistant(unittest.TestCase):

    def _make_ok_payload(self):
        return {
            "status": "ok",
            "data": {
                "brand": "Sony",
                "model": "WH-1000XM4",
                "category": "headphones",
                "valuation": {"fair_estimate": 3000, "low_estimate": 2500, "high_estimate": 3500,
                              "confidence": 0.8, "currency": "SEK", "evidence_summary": "test",
                              "valuation_method": "test", "comparable_count": 5,
                              "source_breakdown": {}},
            },
            "warnings": [],
            "reasons": [],
            "debug_id": "test-123",
        }

    def test_ok_payload_gets_assistant_context(self):
        payload = enrich_envelope(self._make_ok_payload(), confirmation=None, has_images=True)
        self.assertIn("assistant_context", payload)
        self.assertEqual(payload["assistant_context"]["phase"], "confirming")

    def test_ok_payload_without_new_params_still_works(self):
        """Backward compat: calling with no extra params should still work."""
        payload = enrich_envelope(self._make_ok_payload())
        # Should get assistant_context since default has_images=True
        self.assertIn("assistant_context", payload)

    def test_confirmation_yes_no_condition_produces_awaiting_condition(self):
        payload = enrich_envelope(self._make_ok_payload(), confirmation="yes", has_images=True)
        self.assertEqual(payload["assistant_context"]["phase"], "awaiting_condition")

    def test_confirmation_yes_condition_no_shipping_produces_awaiting_shipping(self):
        payload = enrich_envelope(self._make_ok_payload(), confirmation="yes", has_images=True, condition="good")
        self.assertEqual(payload["assistant_context"]["phase"], "awaiting_shipping")

    def test_confirmation_yes_condition_shipping_no_goal_produces_awaiting_goal(self):
        payload = enrich_envelope(self._make_ok_payload(), confirmation="yes", has_images=True, condition="good", shipping="can_ship")
        self.assertEqual(payload["assistant_context"]["phase"], "awaiting_goal")

    def test_all_fields_produces_ready(self):
        payload = enrich_envelope(self._make_ok_payload(), confirmation="yes", has_images=True, condition="good", shipping="can_ship", goal="balanced")
        self.assertEqual(payload["assistant_context"]["phase"], "ready")

    def test_error_payload_no_assistant_context(self):
        payload = enrich_envelope({
            "status": "error",
            "data": None,
            "warnings": [],
            "reasons": [],
            "debug_id": "err-1",
        })
        self.assertNotIn("assistant_context", payload)

    def test_existing_fields_unchanged(self):
        """Core envelope fields must not be affected by assistant layer."""
        payload = enrich_envelope(self._make_ok_payload(), confirmation=None, has_images=True)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("status_title", payload)
        self.assertIn("user_status_title", payload)
        self.assertIn("reason_details", payload)


# ─── Slice 2: Condition question ───


class TestAwaitingCondition(unittest.TestCase):

    def test_phase_is_awaiting_condition(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony", "model": "WH-1000XM4"}, "yes", True)
        self.assertEqual(ctx.phase, "awaiting_condition")

    def test_prompt_contains_product_name(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony", "model": "WH-1000XM4"}, "yes", True)
        self.assertIn("Sony", ctx.prompt)

    def test_has_five_condition_options(self):
        ctx = _build_assistant_context("ok", {}, "yes", True)
        self.assertEqual(len(ctx.quick_replies), 5)

    def test_all_actions_are_set_condition(self):
        ctx = _build_assistant_context("ok", {}, "yes", True)
        for qr in ctx.quick_replies:
            self.assertEqual(qr.action, "set_condition")

    def test_payloads_have_condition_key(self):
        ctx = _build_assistant_context("ok", {}, "yes", True)
        for qr in ctx.quick_replies:
            self.assertIn("condition", qr.payload)

    def test_condition_values_are_valid(self):
        ctx = _build_assistant_context("ok", {}, "yes", True)
        valid = {"excellent", "good", "fair", "poor"}
        for qr in ctx.quick_replies:
            self.assertIn(qr.payload["condition"], valid)

    def test_labels_are_swedish(self):
        ctx = _build_assistant_context("ok", {}, "yes", True)
        labels = [qr.label for qr in ctx.quick_replies]
        self.assertIn("Som ny", labels)
        self.assertIn("Bra skick", labels)
        self.assertIn("Okej skick", labels)
        self.assertIn("Tydligt slitage", labels)
        self.assertIn("Defekt", labels)

    def test_condition_provided_goes_to_shipping(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good")
        self.assertEqual(ctx.phase, "awaiting_shipping")

    def test_condition_with_shipping_goes_to_goal(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="excellent", shipping="either")
        self.assertEqual(ctx.phase, "awaiting_goal")

    def test_condition_shipping_goal_goes_to_ready(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="poor", shipping="local_only", goal="sell_fast")
        self.assertEqual(ctx.phase, "ready")

    def test_no_guardrail_message(self):
        ctx = _build_assistant_context("ok", {}, "yes", True)
        self.assertIsNone(ctx.guardrail_message)

    def test_depreciation_estimate_also_asks_condition(self):
        ctx = _build_assistant_context("depreciation_estimate", {}, "yes", True)
        self.assertEqual(ctx.phase, "awaiting_condition")


# ─── Slice 3: Bundle selection ───


class TestBundleEligibility(unittest.TestCase):

    def test_camera_category_is_eligible(self):
        self.assertTrue(_is_bundle_eligible({"category": "camera"}))

    def test_camera_uppercase_is_eligible(self):
        self.assertTrue(_is_bundle_eligible({"category": "Camera"}))

    def test_dji_brand_is_eligible(self):
        self.assertTrue(_is_bundle_eligible({"brand": "DJI"}))

    def test_gopro_brand_is_eligible(self):
        self.assertTrue(_is_bundle_eligible({"brand": "GoPro"}))

    def test_headphones_not_eligible(self):
        self.assertFalse(_is_bundle_eligible({"category": "headphones"}))

    def test_smartphone_not_eligible(self):
        self.assertFalse(_is_bundle_eligible({"category": "smartphone"}))

    def test_sony_brand_not_eligible(self):
        self.assertFalse(_is_bundle_eligible({"brand": "Sony", "category": "headphones"}))

    def test_none_data_not_eligible(self):
        self.assertFalse(_is_bundle_eligible(None))

    def test_empty_data_not_eligible(self):
        self.assertFalse(_is_bundle_eligible({}))


class TestAwaitingBundle(unittest.TestCase):

    def _camera_data(self):
        return {"brand": "DJI", "model": "Osmo Action 5 Pro", "category": "camera"}

    def test_camera_with_condition_gets_bundle_question(self):
        ctx = _build_assistant_context("ok", self._camera_data(), "yes", True, condition="good")
        self.assertEqual(ctx.phase, "awaiting_bundle")

    def test_bundle_prompt_contains_product_name(self):
        ctx = _build_assistant_context("ok", self._camera_data(), "yes", True, condition="good")
        self.assertIn("DJI", ctx.prompt)

    def test_has_four_bundle_options(self):
        ctx = _build_assistant_context("ok", self._camera_data(), "yes", True, condition="good")
        self.assertEqual(len(ctx.quick_replies), 4)

    def test_all_actions_are_set_bundle(self):
        ctx = _build_assistant_context("ok", self._camera_data(), "yes", True, condition="good")
        for qr in ctx.quick_replies:
            self.assertEqual(qr.action, "set_bundle")

    def test_payloads_have_bundle_key(self):
        ctx = _build_assistant_context("ok", self._camera_data(), "yes", True, condition="good")
        for qr in ctx.quick_replies:
            self.assertIn("bundle", qr.payload)

    def test_bundle_values_are_valid(self):
        ctx = _build_assistant_context("ok", self._camera_data(), "yes", True, condition="good")
        valid = {"unit_only", "with_case", "combo_kit", "full_kit"}
        for qr in ctx.quick_replies:
            self.assertIn(qr.payload["bundle"], valid)

    def test_labels_are_swedish(self):
        ctx = _build_assistant_context("ok", self._camera_data(), "yes", True, condition="good")
        labels = [qr.label for qr in ctx.quick_replies]
        self.assertIn("Bara enheten", labels)
        self.assertIn("Komplett kit (allt medföljer)", labels)

    def test_bundle_provided_goes_to_shipping(self):
        ctx = _build_assistant_context("ok", self._camera_data(), "yes", True, condition="good", bundle="unit_only")
        self.assertEqual(ctx.phase, "awaiting_shipping")

    def test_bundle_with_shipping_goes_to_goal(self):
        ctx = _build_assistant_context("ok", self._camera_data(), "yes", True, condition="good", bundle="full_kit", shipping="can_ship")
        self.assertEqual(ctx.phase, "awaiting_goal")

    def test_bundle_shipping_goal_goes_to_ready(self):
        ctx = _build_assistant_context("ok", self._camera_data(), "yes", True, condition="good", bundle="full_kit", shipping="can_ship", goal="max_price")
        self.assertEqual(ctx.phase, "ready")

    def test_non_camera_skips_bundle_to_shipping(self):
        """Headphones with condition should skip bundle, go to shipping."""
        data = {"brand": "Sony", "model": "WH-1000XM4", "category": "headphones"}
        ctx = _build_assistant_context("ok", data, "yes", True, condition="good")
        self.assertEqual(ctx.phase, "awaiting_shipping")

    def test_gopro_gets_bundle_question(self):
        data = {"brand": "GoPro", "model": "Hero 12", "category": "camera"}
        ctx = _build_assistant_context("ok", data, "yes", True, condition="good")
        self.assertEqual(ctx.phase, "awaiting_bundle")

    def test_dji_without_camera_category_still_eligible(self):
        """DJI brand alone triggers bundle eligibility even without camera category."""
        data = {"brand": "DJI", "model": "Mini 3 Pro"}
        ctx = _build_assistant_context("ok", data, "yes", True, condition="good")
        self.assertEqual(ctx.phase, "awaiting_bundle")


# ─── Slice 4: Shipping preference ───


class TestAwaitingShipping(unittest.TestCase):

    def test_condition_set_no_shipping_is_awaiting_shipping(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony"}, "yes", True, condition="good")
        self.assertEqual(ctx.phase, "awaiting_shipping")

    def test_prompt_is_swedish(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good")
        self.assertIn("sälja", ctx.prompt.lower())

    def test_has_three_shipping_options(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good")
        self.assertEqual(len(ctx.quick_replies), 3)

    def test_all_actions_are_set_shipping(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good")
        for qr in ctx.quick_replies:
            self.assertEqual(qr.action, "set_shipping")

    def test_payloads_have_shipping_key(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good")
        for qr in ctx.quick_replies:
            self.assertIn("shipping", qr.payload)

    def test_shipping_values_are_valid(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good")
        valid = {"can_ship", "local_only", "either"}
        for qr in ctx.quick_replies:
            self.assertIn(qr.payload["shipping"], valid)

    def test_labels_are_swedish(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good")
        labels = [qr.label for qr in ctx.quick_replies]
        self.assertIn("Kan skickas", labels)
        self.assertIn("Endast lokal affär", labels)
        self.assertIn("Båda funkar", labels)

    def test_shipping_provided_goes_to_goal(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship")
        self.assertEqual(ctx.phase, "awaiting_goal")

    def test_local_only_goes_to_goal(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="local_only")
        self.assertEqual(ctx.phase, "awaiting_goal")

    def test_either_goes_to_goal(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="either")
        self.assertEqual(ctx.phase, "awaiting_goal")

    def test_camera_full_flow(self):
        """Full camera flow: condition → bundle → shipping → goal → ready."""
        data = {"brand": "DJI", "category": "camera"}
        ctx = _build_assistant_context("ok", data, "yes", True, condition="good")
        self.assertEqual(ctx.phase, "awaiting_bundle")
        ctx = _build_assistant_context("ok", data, "yes", True, condition="good", bundle="unit_only")
        self.assertEqual(ctx.phase, "awaiting_shipping")
        ctx = _build_assistant_context("ok", data, "yes", True, condition="good", bundle="unit_only", shipping="can_ship")
        self.assertEqual(ctx.phase, "awaiting_goal")
        ctx = _build_assistant_context("ok", data, "yes", True, condition="good", bundle="unit_only", shipping="can_ship", goal="balanced")
        self.assertEqual(ctx.phase, "ready")

    def test_headphones_skips_bundle(self):
        """Non-camera flow: condition → shipping → goal → ready (no bundle step)."""
        data = {"brand": "Sony", "category": "headphones"}
        ctx = _build_assistant_context("ok", data, "yes", True, condition="good")
        self.assertEqual(ctx.phase, "awaiting_shipping")
        ctx = _build_assistant_context("ok", data, "yes", True, condition="good", shipping="either")
        self.assertEqual(ctx.phase, "awaiting_goal")
        ctx = _build_assistant_context("ok", data, "yes", True, condition="good", shipping="either", goal="sell_fast")
        self.assertEqual(ctx.phase, "ready")

    def test_no_guardrail_message(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good")
        self.assertIsNone(ctx.guardrail_message)


# ─── Slice 5: Goal selection ───


class TestAwaitingGoal(unittest.TestCase):

    def test_shipping_set_no_goal_is_awaiting_goal(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship")
        self.assertEqual(ctx.phase, "awaiting_goal")

    def test_prompt_is_swedish(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship")
        self.assertIn("viktigast", ctx.prompt.lower())

    def test_has_three_goal_options(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship")
        self.assertEqual(len(ctx.quick_replies), 3)

    def test_all_actions_are_set_goal(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship")
        for qr in ctx.quick_replies:
            self.assertEqual(qr.action, "set_goal")

    def test_payloads_have_goal_key(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship")
        for qr in ctx.quick_replies:
            self.assertIn("goal", qr.payload)

    def test_goal_values_are_valid(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship")
        valid = {"sell_fast", "max_price", "balanced"}
        for qr in ctx.quick_replies:
            self.assertIn(qr.payload["goal"], valid)

    def test_labels_are_swedish(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship")
        labels = [qr.label for qr in ctx.quick_replies]
        self.assertIn("Sälja snabbt", labels)
        self.assertIn("Få högsta pris", labels)
        self.assertIn("Lagom balans", labels)

    def test_sell_fast_goes_to_ready(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship", goal="sell_fast")
        self.assertEqual(ctx.phase, "ready")

    def test_max_price_goes_to_ready(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship", goal="max_price")
        self.assertEqual(ctx.phase, "ready")

    def test_balanced_goes_to_ready(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship", goal="balanced")
        self.assertEqual(ctx.phase, "ready")

    def test_no_guardrail_message(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="either")
        self.assertIsNone(ctx.guardrail_message)


# ─── Slice 6: Strategy output ───


class TestStrategyOutput(unittest.TestCase):

    def _ready(self, goal: str):
        return _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship", goal=goal)

    def test_sell_fast_has_strategy(self):
        ctx = self._ready("sell_fast")
        self.assertIsNotNone(ctx.strategy_summary)
        self.assertIn("nedre", ctx.strategy_summary.lower())

    def test_max_price_has_strategy(self):
        ctx = self._ready("max_price")
        self.assertIsNotNone(ctx.strategy_summary)
        self.assertIn("övre", ctx.strategy_summary.lower())

    def test_balanced_has_strategy(self):
        ctx = self._ready("balanced")
        self.assertIsNotNone(ctx.strategy_summary)
        self.assertIn("mitten", ctx.strategy_summary.lower())

    def test_all_strategies_are_swedish(self):
        for goal in ("sell_fast", "max_price", "balanced"):
            ctx = self._ready(goal)
            self.assertTrue(len(ctx.strategy_summary) > 20, f"Strategy too short for {goal}")

    def test_unknown_goal_has_no_strategy(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship", goal="unknown_value")
        self.assertEqual(ctx.phase, "ready")
        self.assertIsNone(ctx.strategy_summary)

    def test_non_ready_phases_have_no_strategy(self):
        ctx = _build_assistant_context("ok", {}, "yes", True, condition="good", shipping="can_ship")
        self.assertEqual(ctx.phase, "awaiting_goal")
        self.assertIsNone(ctx.strategy_summary)

    def test_confirming_has_no_strategy(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony"}, None, True)
        self.assertEqual(ctx.phase, "confirming")
        self.assertIsNone(ctx.strategy_summary)

    def test_strategy_does_not_affect_phase(self):
        for goal in ("sell_fast", "max_price", "balanced"):
            ctx = self._ready(goal)
            self.assertEqual(ctx.phase, "ready")

    def test_strategy_does_not_affect_quick_replies(self):
        ctx = self._ready("sell_fast")
        actions = [qr.action for qr in ctx.quick_replies]
        self.assertIn("start_over", actions)

    def test_camera_full_flow_has_strategy(self):
        data = {"brand": "DJI", "category": "camera"}
        ctx = _build_assistant_context("ok", data, "yes", True, condition="good", bundle="unit_only", shipping="can_ship", goal="max_price")
        self.assertEqual(ctx.phase, "ready")
        self.assertIsNotNone(ctx.strategy_summary)
        self.assertIn("övre", ctx.strategy_summary.lower())


if __name__ == "__main__":
    unittest.main()
