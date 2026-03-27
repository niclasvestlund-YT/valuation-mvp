"""Tests for VALOR Prisassistent conversation layer.

Tests the assistant_context generation logic: phase derivation,
quick reply structure, confirmation normalization, and guardrails.
"""

import unittest

from backend.app.api.value import (
    _build_assistant_context,
    _normalize_confirmation,
    enrich_envelope,
)
from backend.app.schemas.assistant import AssistantContext, QuickReply


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

    def test_confirmation_yes_is_complete(self):
        ctx = _build_assistant_context("ok", {"brand": "Sony"}, "yes", True)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.phase, "complete")

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

    def test_complete_has_start_over(self):
        ctx = _build_assistant_context("ok", {}, "yes", True)
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

    def test_confirmation_yes_produces_complete(self):
        payload = enrich_envelope(self._make_ok_payload(), confirmation="yes", has_images=True)
        self.assertEqual(payload["assistant_context"]["phase"], "complete")

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


if __name__ == "__main__":
    unittest.main()
