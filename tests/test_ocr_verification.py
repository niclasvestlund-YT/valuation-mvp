"""Tests for OCR cross-verification against Vision identification."""

from backend.app.schemas.ocr_result import OcrResult
from backend.app.services.ocr_verification import verify_ocr_against_identification


class TestBrandMatching:
    def test_brand_in_text(self):
        ocr = OcrResult(detected_text=["Sony WH-1000XM5 Headphones"])
        result = verify_ocr_against_identification(ocr, brand="Sony", model="WH-1000XM5")
        assert result.brand_match
        assert result.confidence_delta > 0

    def test_brand_in_logos(self):
        ocr = OcrResult(detected_logos=["Sony"])
        result = verify_ocr_against_identification(ocr, brand="Sony", model="WH-1000XM5")
        assert result.brand_match

    def test_brand_not_found(self):
        ocr = OcrResult(detected_text=["Some random text here"])
        result = verify_ocr_against_identification(ocr, brand="Sony", model="WH-1000XM5")
        assert not result.brand_match

    def test_contradicting_brand_in_logos(self):
        ocr = OcrResult(detected_logos=["Samsung"])
        result = verify_ocr_against_identification(ocr, brand="Sony", model="WH-1000XM5")
        assert result.has_contradiction
        assert result.confidence_delta < 0


class TestModelMatching:
    def test_model_tokens_in_text(self):
        ocr = OcrResult(detected_text=["WH 1000XM5 Wireless"])
        result = verify_ocr_against_identification(ocr, brand="Sony", model="WH-1000XM5")
        assert result.model_match

    def test_model_partial_match(self):
        ocr = OcrResult(detected_text=["1000XM5"])
        result = verify_ocr_against_identification(ocr, brand="Sony", model="WH-1000XM5")
        # Should match since significant tokens are present
        assert result.model_match

    def test_model_no_match(self):
        ocr = OcrResult(detected_text=["Completely different text"])
        result = verify_ocr_against_identification(ocr, brand="Sony", model="WH-1000XM5")
        assert not result.model_match


class TestConfidenceAdjustment:
    def test_both_match_positive_delta(self):
        ocr = OcrResult(detected_text=["Sony WH-1000XM5"], detected_logos=["Sony"])
        result = verify_ocr_against_identification(ocr, brand="Sony", model="WH-1000XM5")
        assert result.brand_match and result.model_match
        assert result.confidence_delta == 0.05

    def test_brand_only_small_delta(self):
        ocr = OcrResult(detected_logos=["Sony"])
        result = verify_ocr_against_identification(ocr, brand="Sony", model="WH-1000XM5")
        assert result.brand_match and not result.model_match
        assert result.confidence_delta == 0.02

    def test_contradiction_negative_delta(self):
        ocr = OcrResult(detected_logos=["Apple"])
        result = verify_ocr_against_identification(ocr, brand="Sony", model="WH-1000XM5")
        assert result.has_contradiction
        assert result.confidence_delta == -0.08


class TestEdgeCases:
    def test_no_ocr_data(self):
        ocr = OcrResult.empty()
        result = verify_ocr_against_identification(ocr, brand="Sony", model="WH-1000XM5")
        assert not result.brand_match
        assert not result.model_match
        assert not result.has_contradiction
        assert result.confidence_delta == 0.0
        assert result.details == "no_ocr_data"

    def test_no_brand_provided(self):
        ocr = OcrResult(detected_text=["Sony WH-1000XM5"])
        result = verify_ocr_against_identification(ocr, brand=None, model="WH-1000XM5")
        assert not result.brand_match  # Can't match what wasn't provided

    def test_no_model_provided(self):
        ocr = OcrResult(detected_logos=["Sony"])
        result = verify_ocr_against_identification(ocr, brand="Sony", model=None)
        assert result.brand_match
        assert not result.model_match

    def test_case_insensitive(self):
        ocr = OcrResult(detected_text=["SONY wh-1000xm5"])
        result = verify_ocr_against_identification(ocr, brand="Sony", model="WH-1000XM5")
        assert result.brand_match
        assert result.model_match
