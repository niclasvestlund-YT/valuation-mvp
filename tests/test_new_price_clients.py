"""Tests for Webhallen, Inet, and Serper new-price clients + service layer."""

import json

import pytest

from backend.app.utils.cache import _cache


class _FakeResponse:
    def __init__(self, *, json_payload=None, status_code=200):
        self._json_payload = json_payload
        self.status_code = status_code

    def json(self):
        if self._json_payload is None:
            raise ValueError("No JSON")
        return self._json_payload


@pytest.fixture(autouse=True)
def _clear_caches():
    _cache.clear()
    yield
    _cache.clear()


# ─── Webhallen ────────────────────────────────────────────────────────────


class TestWebhallenClient:
    def test_returns_none_on_404(self, monkeypatch):
        from backend.app.integrations import webhallen_client

        monkeypatch.setattr(webhallen_client, "_last_request_time", 0.0)
        monkeypatch.setattr(webhallen_client, "_RATE_LIMIT_SECONDS", 0)
        monkeypatch.setattr(
            "requests.get",
            lambda *a, **kw: _FakeResponse(status_code=404),
        )
        result = webhallen_client.get_new_price_sek("Sony WH-1000XM4")
        assert result is None

    def test_returns_none_on_403(self, monkeypatch):
        from backend.app.integrations import webhallen_client

        monkeypatch.setattr(webhallen_client, "_last_request_time", 0.0)
        monkeypatch.setattr(webhallen_client, "_RATE_LIMIT_SECONDS", 0)
        monkeypatch.setattr(
            "requests.get",
            lambda *a, **kw: _FakeResponse(status_code=403),
        )
        result = webhallen_client.get_new_price_sek("Sony WH-1000XM4")
        assert result is None

    def test_extracts_price_from_nested_shape(self, monkeypatch):
        from backend.app.integrations import webhallen_client

        monkeypatch.setattr(webhallen_client, "_last_request_time", 0.0)
        monkeypatch.setattr(webhallen_client, "_RATE_LIMIT_SECONDS", 0)
        payload = {
            "products": [
                {
                    "name": "Sony WH-1000XM4",
                    "price": {"price": "3990.00", "currency": "SEK"},
                }
            ]
        }
        monkeypatch.setattr(
            "requests.get",
            lambda *a, **kw: _FakeResponse(json_payload=payload),
        )
        result = webhallen_client.get_new_price_sek("Sony WH-1000XM4")
        assert result == 3990.0

    def test_extracts_price_from_flat_shape(self, monkeypatch):
        from backend.app.integrations import webhallen_client

        monkeypatch.setattr(webhallen_client, "_last_request_time", 0.0)
        monkeypatch.setattr(webhallen_client, "_RATE_LIMIT_SECONDS", 0)
        payload = {"products": [{"name": "Test Product", "price": 2990}]}
        monkeypatch.setattr(
            "requests.get",
            lambda *a, **kw: _FakeResponse(json_payload=payload),
        )
        result = webhallen_client.get_new_price_sek("Test Product")
        assert result == 2990.0

    def test_returns_lowest_price_when_multiple_products(self, monkeypatch):
        from backend.app.integrations import webhallen_client

        monkeypatch.setattr(webhallen_client, "_last_request_time", 0.0)
        monkeypatch.setattr(webhallen_client, "_RATE_LIMIT_SECONDS", 0)
        payload = {
            "products": [
                {"name": "Product A", "price": {"price": "5990.00"}},
                {"name": "Product B", "price": {"price": "3490.00"}},
                {"name": "Product C", "price": {"price": "4290.00"}},
            ]
        }
        monkeypatch.setattr(
            "requests.get",
            lambda *a, **kw: _FakeResponse(json_payload=payload),
        )
        result = webhallen_client.get_new_price_sek("Some Product")
        assert result == 3490.0

    def test_returns_none_on_empty_products(self, monkeypatch):
        from backend.app.integrations import webhallen_client

        monkeypatch.setattr(webhallen_client, "_last_request_time", 0.0)
        monkeypatch.setattr(webhallen_client, "_RATE_LIMIT_SECONDS", 0)
        monkeypatch.setattr(
            "requests.get",
            lambda *a, **kw: _FakeResponse(json_payload={"products": []}),
        )
        result = webhallen_client.get_new_price_sek("Nothing Here")
        assert result is None

    def test_caches_result(self, monkeypatch):
        from backend.app.integrations import webhallen_client

        monkeypatch.setattr(webhallen_client, "_last_request_time", 0.0)
        monkeypatch.setattr(webhallen_client, "_RATE_LIMIT_SECONDS", 0)
        call_count = 0

        def fake_get(*a, **kw):
            nonlocal call_count
            call_count += 1
            return _FakeResponse(
                json_payload={"products": [{"name": "X", "price": {"price": "1990.00"}}]}
            )

        monkeypatch.setattr("requests.get", fake_get)
        r1 = webhallen_client.get_new_price_sek("Cache Test")
        r2 = webhallen_client.get_new_price_sek("Cache Test")
        assert r1 == 1990.0
        assert r2 == 1990.0
        assert call_count == 1


# ─── Inet ─────────────────────────────────────────────────────────────────


class TestInetClient:
    def test_returns_none_on_403(self, monkeypatch):
        from backend.app.integrations import inet_client

        monkeypatch.setattr(inet_client, "_last_request_time", 0.0)
        monkeypatch.setattr(inet_client, "_RATE_LIMIT_SECONDS", 0)
        monkeypatch.setattr(
            "requests.get",
            lambda *a, **kw: _FakeResponse(status_code=403),
        )
        result = inet_client.get_new_price_sek("Sony WH-1000XM4")
        assert result is None

    def test_extracts_price_from_nested_shape(self, monkeypatch):
        from backend.app.integrations import inet_client

        monkeypatch.setattr(inet_client, "_last_request_time", 0.0)
        monkeypatch.setattr(inet_client, "_RATE_LIMIT_SECONDS", 0)
        payload = {
            "products": [
                {
                    "name": "MacBook Air M4",
                    "price": {"price": 10990, "listPrice": 12487},
                }
            ]
        }
        monkeypatch.setattr(
            "requests.get",
            lambda *a, **kw: _FakeResponse(json_payload=payload),
        )
        result = inet_client.get_new_price_sek("MacBook Air")
        assert result == 10990.0

    def test_extracts_price_from_flat_shape(self, monkeypatch):
        from backend.app.integrations import inet_client

        monkeypatch.setattr(inet_client, "_last_request_time", 0.0)
        monkeypatch.setattr(inet_client, "_RATE_LIMIT_SECONDS", 0)
        payload = {"products": [{"name": "Test", "price": 5990}]}
        monkeypatch.setattr(
            "requests.get",
            lambda *a, **kw: _FakeResponse(json_payload=payload),
        )
        result = inet_client.get_new_price_sek("Test")
        assert result == 5990.0

    def test_returns_none_on_empty_products(self, monkeypatch):
        from backend.app.integrations import inet_client

        monkeypatch.setattr(inet_client, "_last_request_time", 0.0)
        monkeypatch.setattr(inet_client, "_RATE_LIMIT_SECONDS", 0)
        monkeypatch.setattr(
            "requests.get",
            lambda *a, **kw: _FakeResponse(json_payload={"products": [], "totalCount": 0}),
        )
        result = inet_client.get_new_price_sek("Nothing")
        assert result is None

    def test_caches_result(self, monkeypatch):
        from backend.app.integrations import inet_client

        monkeypatch.setattr(inet_client, "_last_request_time", 0.0)
        monkeypatch.setattr(inet_client, "_RATE_LIMIT_SECONDS", 0)
        call_count = 0

        def fake_get(*a, **kw):
            nonlocal call_count
            call_count += 1
            return _FakeResponse(
                json_payload={"products": [{"name": "X", "price": {"price": 7990}}]}
            )

        monkeypatch.setattr("requests.get", fake_get)
        r1 = inet_client.get_new_price_sek("Cache Test")
        r2 = inet_client.get_new_price_sek("Cache Test")
        assert r1 == 7990.0
        assert r2 == 7990.0
        assert call_count == 1


# ─── Serper (disabled) ────────────────────────────────────────────────────


class TestSerperDisabled:
    def test_get_new_price_sek_returns_none(self):
        from backend.app.integrations.serper_new_price_client import get_new_price_sek

        assert get_new_price_sek("any product") is None

    def test_get_new_price_sek_returns_none_for_real_query(self):
        from backend.app.integrations.serper_new_price_client import get_new_price_sek

        assert get_new_price_sek("Sony WH-1000XM4") is None


# ─── Service layer ────────────────────────────────────────────────────────


class TestNewPriceServiceSourceChain:
    def test_webhallen_tried_first_inet_not_called(self, monkeypatch):
        from backend.app.services import new_price_service
        from backend.app.services.new_price_service import NewPriceService

        inet_called = False

        def fake_webhallen(query):
            return 3990.0

        def fake_inet(query):
            nonlocal inet_called
            inet_called = True
            return 5990.0

        monkeypatch.setattr(new_price_service, "_get_webhallen_price", fake_webhallen)
        monkeypatch.setattr(new_price_service, "_get_inet_price", fake_inet)

        service = NewPriceService()
        result = service.get_new_price("Sony", "WH-1000XM4")
        assert result["estimated_new_price"] == 3990.0
        assert result["source"] == "Webhallen"
        assert not inet_called

    def test_falls_back_to_inet_when_webhallen_returns_none(self, monkeypatch):
        from backend.app.services import new_price_service
        from backend.app.services.new_price_service import NewPriceService

        monkeypatch.setattr(new_price_service, "_get_webhallen_price", lambda q: None)
        monkeypatch.setattr(new_price_service, "_get_inet_price", lambda q: 10990.0)

        service = NewPriceService()
        result = service.get_new_price("Apple", "MacBook Air M2")
        assert result["estimated_new_price"] == 10990.0
        assert result["source"] == "Inet"

    def test_returns_unavailable_when_all_sources_return_none(self, monkeypatch):
        from backend.app.services import new_price_service
        from backend.app.services.new_price_service import NewPriceService

        monkeypatch.setattr(new_price_service, "_get_webhallen_price", lambda q: None)
        monkeypatch.setattr(new_price_service, "_get_inet_price", lambda q: None)

        service = NewPriceService()
        result = service.get_new_price("Unknown", "Product XYZ")
        assert result["estimated_new_price"] is None
        assert result["method"] in ("unavailable", "no_trustworthy_candidates")

    def test_empty_brand_and_model_returns_none(self, monkeypatch):
        from backend.app.services import new_price_service
        from backend.app.services.new_price_service import NewPriceService

        webhallen_called = False
        inet_called = False

        def fake_webhallen(query):
            nonlocal webhallen_called
            webhallen_called = True
            return None

        def fake_inet(query):
            nonlocal inet_called
            inet_called = True
            return None

        monkeypatch.setattr(new_price_service, "_get_webhallen_price", fake_webhallen)
        monkeypatch.setattr(new_price_service, "_get_inet_price", fake_inet)

        service = NewPriceService()
        result = service.get_new_price("", "")
        assert result["estimated_new_price"] is None
        assert not webhallen_called
        assert not inet_called
