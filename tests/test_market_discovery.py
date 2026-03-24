import unittest

from backend.app.integrations.serpapi_used_market_client import SerpApiUsedMarketClient
from backend.app.schemas.market_comparable import MarketComparable
from backend.app.services.market_data_service import MarketDataService


class StubTraderaClient:
    def __init__(self, raw_results: list[dict] | None = None, configured: bool = True) -> None:
        self.raw_results = raw_results or []
        self.is_configured = configured

    def search(self, query: str) -> list[dict]:
        return self.raw_results


class StubSerpApiUsedMarketClient:
    def __init__(self, results: list[MarketComparable] | None = None, configured: bool = True) -> None:
        self.results = results or []
        self.is_configured = configured

    def search(self, *, brand: str, model: str, category: str | None = None) -> list[MarketComparable]:
        return self.results


class MarketDiscoveryTests(unittest.TestCase):
    def test_accepts_blocket_listing_candidate(self) -> None:
        client = SerpApiUsedMarketClient(api_key="test")

        comparable = client._normalize_candidate(
            {
                "result_id": "abc123",
                "title": "DJI Osmo Action 5 Pro säljes",
                "link": "https://www.blocket.se/annons/stockholm/dji_osmo_action_5_pro/1234567890",
                "snippet": "DJI Osmo Action 5 Pro 4 200 kr",
            },
            brand="DJI",
            model="Osmo Action 5 Pro",
            category="camera",
        )

        self.assertIsNotNone(comparable)
        self.assertEqual(comparable.source, "blocket_serpapi")
        self.assertEqual(comparable.currency, "SEK")
        self.assertEqual(comparable.price, 4200.0)
        self.assertEqual(comparable.raw["_fallback_metadata"]["listing_page_confidence"], "high")

    def test_rejects_generic_blocket_search_page(self) -> None:
        client = SerpApiUsedMarketClient(api_key="test")

        comparable = client._normalize_candidate(
            {
                "result_id": "abc124",
                "title": "DJI Osmo Action 5 Pro - annonser i hela Sverige",
                "link": "https://www.blocket.se/annonser/hela_sverige?q=dji+osmo+action+5+pro",
                "snippet": "Köp & sälj DJI Osmo Action 5 Pro i hela Sverige 4 200 kr",
            },
            brand="DJI",
            model="Osmo Action 5 Pro",
            category="camera",
        )

        self.assertIsNone(comparable)

    def test_accepts_blocket_recommerce_item_page(self) -> None:
        client = SerpApiUsedMarketClient(api_key="test")

        comparable = client._normalize_candidate(
            {
                "result_id": "abc125",
                "title": "DJI Osmo Action 5 Pro Standard Combo",
                "link": "https://www.blocket.se/recommerce/forsale/item/21501336",
                "snippet": "DJI Osmo Action 5 Pro Standard Combo 2 900 kr",
            },
            brand="DJI",
            model="Osmo Action 5 Pro",
            category="camera",
        )

        self.assertIsNotNone(comparable)
        self.assertEqual(comparable.source, "blocket_serpapi")
        self.assertEqual(comparable.raw["_fallback_metadata"]["listing_page_confidence"], "high")

    def test_build_queries_include_action_alias_without_osmo(self) -> None:
        client = SerpApiUsedMarketClient(api_key="test")

        queries = client._build_queries(brand="DJI", model="Osmo Action 5 Pro")

        self.assertIn("DJI osmo action 5 pro site:blocket.se", queries)
        self.assertIn("DJI action 5 pro site:blocket.se", queries)

    def test_rejects_implausibly_low_used_market_price(self) -> None:
        client = SerpApiUsedMarketClient(api_key="test")

        comparable = client._normalize_candidate(
            {
                "result_id": "abc126",
                "title": "DJI Osmo Action 5 Pro i nyskick",
                "link": "https://www.tradera.com/item/1000208/714258434/dji-osmo-action-5-pro-i-nyskick",
                "snippet": "DJI Osmo Action 5 Pro 50,35 kr",
            },
            brand="DJI",
            model="Osmo Action 5 Pro",
            category="camera",
        )

        self.assertIsNone(comparable)

    def test_market_data_service_supplements_sparse_tradera_results(self) -> None:
        service = MarketDataService(
            tradera_client=StubTraderaClient(
                raw_results=[
                    {
                        "Id": "111",
                        "ShortDescription": "DJI Osmo Action 5 Pro",
                        "BuyItNowPrice": "3990",
                        "Currency": "SEK",
                        "Status": "active",
                        "ItemUrl": "https://www.tradera.com/item/1000208/111/dji-osmo-action-5-pro",
                    }
                ],
                configured=True,
            ),
            serpapi_used_market_client=StubSerpApiUsedMarketClient(
                results=[
                    MarketComparable(
                        source="blocket_serpapi",
                        listing_id="111",
                        title="DJI Osmo Action 5 Pro",
                        price=4200.0,
                        currency="SEK",
                        status="active",
                        url="https://www.blocket.se/annons/stockholm/dji_osmo_action_5_pro/111",
                        raw={"_fallback_metadata": {"source_quality": "fallback_exactish", "source_quality_rank": 3, "exactness_confidence": 0.82}},
                    )
                ],
                configured=True,
            ),
        )

        comparables = service.get_comparables(
            brand="DJI",
            model="Osmo Action 5 Pro",
            category="camera",
        )

        self.assertEqual(len(comparables), 2)
        self.assertEqual({item.source for item in comparables}, {"Tradera", "blocket_serpapi"})


if __name__ == "__main__":
    unittest.main()
