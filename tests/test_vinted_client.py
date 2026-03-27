"""Tests for Vinted client — all network calls are mocked."""

import asyncio
from unittest.mock import patch

import backend.app.integrations.vinted_client as vc
from backend.app.integrations.vinted_client import (
    VINTED_EUR_TO_SEK,
    fetch_vinted,
)


def _reset_cache():
    """Clear the in-memory cache between tests."""
    from backend.app.utils.cache import _cache
    _cache.clear()


def _raw_item(price_eur: float, title: str = "Test Item") -> dict:
    return {"title": title, "price_eur": price_eur, "url": "https://vinted.se/item/123", "raw": {}}


def _mock_fetch_sync(items: list[dict]):
    """Returns a function that yields the given items."""
    def _inner(product_name: str) -> list[dict]:
        return items
    return _inner


class TestVintedClient:
    def test_returns_empty_on_403(self):
        _reset_cache()
        with patch.object(vc, "_fetch_sync", new=lambda n: (_ for _ in ()).throw(Exception("403 Forbidden"))):
            result = asyncio.run(fetch_vinted("Sony WH-1000XM4"))
        assert result == []

    def test_returns_empty_on_timeout(self):
        _reset_cache()
        with patch("backend.app.integrations.vinted_client.asyncio.wait_for",
                    side_effect=asyncio.TimeoutError()):
            result = asyncio.run(fetch_vinted("Sony WH-1000XM4"))
        assert result == []

    def test_filters_out_low_prices(self):
        _reset_cache()
        with patch.object(vc, "_fetch_sync", new=_mock_fetch_sync([_raw_item(1.0)])):
            result = asyncio.run(fetch_vinted("Test Low Price"))
        # 1.0 EUR * 11.5 = 11.5 SEK < 100 minimum
        assert result == []

    def test_filters_out_high_prices(self):
        _reset_cache()
        with patch.object(vc, "_fetch_sync", new=_mock_fetch_sync([_raw_item(20000.0)])):
            result = asyncio.run(fetch_vinted("Test High Price"))
        # 20000.0 EUR * 11.5 = 230000 SEK > 200000 maximum
        assert result == []

    def test_converts_eur_to_sek_correctly(self):
        _reset_cache()
        with patch.object(vc, "_fetch_sync", new=_mock_fetch_sync([_raw_item(200.0)])):
            result = asyncio.run(fetch_vinted("Test EUR Convert"))
        expected = round(200.0 * VINTED_EUR_TO_SEK)  # 2300
        assert len(result) == 1
        assert result[0].price == expected
        assert result[0].source == "Vinted"

    def test_cache_prevents_second_api_call(self):
        _reset_cache()
        call_count = 0
        original = _mock_fetch_sync([_raw_item(200.0)])
        def counting_fetch(name):
            nonlocal call_count
            call_count += 1
            return original(name)

        with patch.object(vc, "_fetch_sync", new=counting_fetch):
            asyncio.run(fetch_vinted("Cache Test Product"))
            asyncio.run(fetch_vinted("Cache Test Product"))
        assert call_count == 1
