import unittest

from backend.app.integrations.new_price_search_client import NewPriceSearchResponse
from backend.app.integrations.serper_new_price_client import SerperNewPriceSearchResponse
from backend.app.services.new_price_service import NewPriceService


class StubSearchClient:
    def __init__(self, response: NewPriceSearchResponse) -> None:
        self.response = response

    def search(self, *, brand: str, model: str, category: str | None = None) -> NewPriceSearchResponse:
        return self.response


class StubSerperClient:
    """Serper stub that is always unconfigured so tests can control the SerpAPI path."""

    is_configured = False

    def search(self, *, brand: str, model: str, category: str | None = None) -> SerperNewPriceSearchResponse:
        return SerperNewPriceSearchResponse(results=[], available=False, reason="stub_unconfigured")


class StubGoogleCSEClient:
    """Google CSE stub that is always unconfigured."""

    is_configured = False

    def search(self, **kwargs) -> SerperNewPriceSearchResponse:
        return SerperNewPriceSearchResponse(results=[], available=False, reason="stub_unconfigured")


def _service_with_serpapi_stub(stub_response: NewPriceSearchResponse) -> NewPriceService:
    """Return a NewPriceService that uses a SerpAPI stub and has Serper/CSE disabled."""
    return NewPriceService(
        search_client=StubSearchClient(stub_response),
        serper_client=StubSerperClient(),
        google_cse_client=StubGoogleCSEClient(),
    )


class NewPriceServiceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
