import unittest
from unittest.mock import patch

from backend.app.integrations.google_cse_client import GoogleCSESearchResponse
from backend.app.integrations.new_price_search_client import NewPriceSearchResponse
from backend.app.integrations.serper_new_price_client import SerperNewPriceSearchResponse
from backend.app.services.new_price_service import NewPriceService


class StubSearchClient:
    is_configured = True

    def __init__(self, response: NewPriceSearchResponse) -> None:
        self.response = response

    def search(self, *, brand: str, model: str, category: str | None = None) -> NewPriceSearchResponse:
        return self.response


class StubSerperClient:
    """Serper stub that is always unconfigured so tests can control the SerpAPI path."""

    is_configured = False

    def search(self, *, brand: str, model: str, category: str | None = None) -> SerperNewPriceSearchResponse:
        return SerperNewPriceSearchResponse(results=[], available=False, reason="stub_unconfigured")


class TrackingSerperClient:
    def __init__(self, response: SerperNewPriceSearchResponse, *, configured: bool = True) -> None:
        self.response = response
        self.is_configured = configured
        self.calls = 0

    def search(self, *, brand: str, model: str, category: str | None = None) -> SerperNewPriceSearchResponse:
        self.calls += 1
        return self.response


class StubGoogleCSEClient:
    """Google CSE stub that is always unconfigured."""

    is_configured = False

    def search(self, **kwargs) -> GoogleCSESearchResponse:
        return GoogleCSESearchResponse(results=[], available=False, reason="stub_unconfigured")


class TrackingGoogleCSEClient:
    def __init__(self, response: GoogleCSESearchResponse, *, configured: bool = True) -> None:
        self.response = response
        self.is_configured = configured
        self.calls = 0

    def search(self, **kwargs) -> GoogleCSESearchResponse:
        self.calls += 1
        return self.response


def _service_with_serpapi_stub(stub_response: NewPriceSearchResponse) -> NewPriceService:
    """Return a NewPriceService that uses a SerpAPI stub and has Serper/CSE disabled."""
    return NewPriceService(
        search_client=StubSearchClient(stub_response),
        serper_client=StubSerperClient(),
        google_cse_client=StubGoogleCSEClient(),
    )


class NewPriceServiceTests(unittest.TestCase):
    def setUp(self):
        # Bypass Webhallen/Inet sources so these tests exercise the SerpAPI/CSE/Serper paths
        self._wh_patch = patch("backend.app.services.new_price_service._get_webhallen_price", return_value=None)
        self._inet_patch = patch("backend.app.services.new_price_service._get_inet_price", return_value=None)
        self._wh_patch.start()
        self._inet_patch.start()

    def tearDown(self):
        self._wh_patch.stop()
        self._inet_patch.stop()

    def candidate(
        self,
        *,
        title: str,
        price: float,
        currency: str = "SEK",
        source: str = "Retailer",
        url: str = "https://example.com/product",
        snippet: str | None = None,
        delivery: str | None = None,
        second_hand_condition: str | None = None,
        is_swedish_result: bool = False,
    ) -> dict:
        return {
            "title": title,
            "price": price,
            "currency": currency,
            "source": source,
            "url": url,
            "snippet": snippet,
            "delivery": delivery,
            "second_hand_condition": second_hand_condition,
            "is_swedish_result": is_swedish_result,
            "raw": {},
        }

    def test_returns_unavailable_when_provider_is_unavailable(self) -> None:
        service = _service_with_serpapi_stub(
            NewPriceSearchResponse(results=[], available=False, reason="missing_api_key")
        )

        result = service.get_new_price("Apple", "iPhone 13", "smartphone")

        self.assertIsNone(result["estimated_new_price"])
        self.assertIsNone(result["currency"])
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["source_count"], 0)
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["method"], "unavailable")

    def test_prefers_valid_sek_candidates_and_uses_median(self) -> None:
        service = _service_with_serpapi_stub(
            NewPriceSearchResponse(
                results=[
                    self.candidate(title="Apple iPhone 13 128GB", price=8299, currency="SEK", source="Webhallen"),
                    self.candidate(title="Apple iPhone 13 128GB", price=7999, currency="SEK", source="Elgiganten"),
                    self.candidate(title="Apple iPhone 13 128GB", price=699, currency="USD", source="Best Buy"),
                ]
            )
        )

        result = service.get_new_price("Apple", "iPhone 13", "smartphone")

        self.assertEqual(result["estimated_new_price"], 7999.0)
        self.assertEqual(result["currency"], "SEK")
        self.assertEqual(result["source_count"], 2)
        self.assertEqual(result["method"], "serpapi_google_shopping_median")

    def test_prefers_swedish_sek_candidates_when_mixed_results_exist(self) -> None:
        service = _service_with_serpapi_stub(
            NewPriceSearchResponse(
                results=[
                    self.candidate(
                        title="Apple iPhone 13 128GB",
                        price=7999,
                        currency="SEK",
                        source="Webhallen",
                        url="https://www.webhallen.se/se/product/iphone-13",
                        is_swedish_result=True,
                    ),
                    self.candidate(
                        title="Apple iPhone 13 128GB",
                        price=8299,
                        currency="SEK",
                        source="Elgiganten",
                        url="https://www.elgiganten.se/product/iphone-13",
                        is_swedish_result=True,
                    ),
                    self.candidate(
                        title="Apple iPhone 13 128GB",
                        price=699,
                        currency="USD",
                        source="Best Buy",
                        url="https://www.bestbuy.com/site/iphone-13",
                        is_swedish_result=False,
                    ),
                ]
            )
        )

        result = service.get_new_price("Apple", "iPhone 13", "smartphone")

        self.assertEqual(result["estimated_new_price"], 7999.0)
        self.assertEqual(result["currency"], "SEK")
        self.assertEqual(result["source_count"], 2)
        self.assertTrue(all(source["currency"] == "SEK" for source in result["sources"]))
        self.assertTrue(
            all(
                source["source"] in {"Webhallen", "Elgiganten"}
                for source in result["sources"]
            )
        )

    def test_rejects_used_refurbished_and_accessory_pages(self) -> None:
        service = _service_with_serpapi_stub(
            NewPriceSearchResponse(
                results=[
                    self.candidate(title="Apple iPhone 13 begagnad", price=4999, currency="SEK", source="Blocket"),
                    self.candidate(title="Apple iPhone 13 refurbished", price=5799, currency="SEK", source="Back Market"),
                    self.candidate(title="Apple iPhone 13 case only", price=299, currency="SEK", source="Accessory Shop"),
                    self.candidate(title="Apple iPhone 13 128GB", price=8299, currency="SEK", source="Webhallen"),
                ]
            )
        )

        result = service.get_new_price("Apple", "iPhone 13", "smartphone")

        self.assertIsNone(result["estimated_new_price"])
        self.assertEqual(result["currency"], "SEK")
        self.assertEqual(result["confidence"], 0.2)
        self.assertEqual(result["source_count"], 1)
        self.assertEqual(result["method"], "single_source_insufficient")

    def test_rejects_model_mismatch_and_implausibly_low_prices(self) -> None:
        service = _service_with_serpapi_stub(
            NewPriceSearchResponse(
                results=[
                    self.candidate(title="Sony WH-1000XM5", price=4990, currency="SEK", source="HiFi Klubben"),
                    self.candidate(title="Sony WH-1000XM4", price=79, currency="SEK", source="Retailer"),
                ]
            )
        )

        result = service.get_new_price("Sony", "WH-1000XM4", "headphones")

        self.assertIsNone(result["estimated_new_price"])
        self.assertIsNone(result["currency"])
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["source_count"], 0)
        self.assertEqual(result["method"], "no_trustworthy_candidates")

    def test_serpapi_fallback_used_when_webhallen_and_inet_return_none(self) -> None:
        """When Webhallen and Inet return None, SerpAPI fallback is used."""
        service = _service_with_serpapi_stub(
            NewPriceSearchResponse(
                results=[
                    self.candidate(title="Apple iPhone 13 128GB", price=7999, currency="SEK", source="Webhallen"),
                    self.candidate(title="Apple iPhone 13 128GB", price=8299, currency="SEK", source="Elgiganten"),
                ],
                available=True,
                reason="ok",
            )
        )

        result = service.get_new_price("Apple", "iPhone 13", "smartphone")

        self.assertEqual(result["method"], "serpapi_google_shopping_median")
        self.assertEqual(result["estimated_new_price"], 7999.0)

    def test_returns_unavailable_when_serpapi_also_fails(self) -> None:
        """When all sources fail (Webhallen, Inet patched to None, SerpAPI unavailable), returns unavailable."""
        service = _service_with_serpapi_stub(
            NewPriceSearchResponse(results=[], available=False, reason="missing_api_key")
        )

        result = service.get_new_price("Apple", "iPhone 13", "smartphone")

        self.assertIsNone(result["estimated_new_price"])
        self.assertEqual(result["method"], "unavailable")


if __name__ == "__main__":
    unittest.main()
