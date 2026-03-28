"""Tests for quota-aware API client blocking before external requests."""

import pytest

from backend.app.core.config import settings
from backend.app.integrations.google_cse_client import GoogleCSEClient
from backend.app.integrations.tradera_client import TraderaClient
from backend.app.utils import api_counter
from backend.app.utils.cache import _cache


class _FakeResponse:
    def __init__(self, *, json_payload=None, text="", status_code=200):
        self._json_payload = json_payload or {}
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._json_payload


@pytest.fixture(autouse=True)
def _reset_environment():
    original_google_cse_api_key = settings.google_cse_api_key
    original_google_cse_cx = settings.google_cse_cx
    original_google_cse_limit = settings.google_cse_free_daily_queries
    original_tradera_app_id = settings.tradera_app_id
    original_tradera_app_key = settings.tradera_app_key
    original_tradera_limit = settings.tradera_free_daily_calls

    _cache.clear()
    api_counter.reset()
    yield
    object.__setattr__(settings, "google_cse_api_key", original_google_cse_api_key)
    object.__setattr__(settings, "google_cse_cx", original_google_cse_cx)
    object.__setattr__(settings, "google_cse_free_daily_queries", original_google_cse_limit)
    object.__setattr__(settings, "tradera_app_id", original_tradera_app_id)
    object.__setattr__(settings, "tradera_app_key", original_tradera_app_key)
    object.__setattr__(settings, "tradera_free_daily_calls", original_tradera_limit)
    _cache.clear()
    api_counter.reset()


def test_google_cse_stops_before_second_network_call_when_free_limit_is_hit(monkeypatch):
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return _FakeResponse(
            json_payload={
                "items": [
                    {
                        "title": "Apple iPhone 13 128GB",
                        "snippet": "Pris 7999 kr",
                        "link": "https://example.com/iphone-13",
                        "displayLink": "example.com",
                    }
                ]
            }
        )

    object.__setattr__(settings, "google_cse_api_key", "test-key")
    object.__setattr__(settings, "google_cse_cx", "test-cx")
    object.__setattr__(settings, "google_cse_free_daily_queries", 1)
    monkeypatch.setattr("backend.app.integrations.google_cse_client.requests.get", fake_get)

    client = GoogleCSEClient()
    first = client.search(brand="Apple", model="iPhone 13")
    second = client.search(brand="Apple", model="iPhone 14")

    stats = api_counter.get_stats()["sources"]["google_cse"]
    assert first.available is True
    assert second.available is False
    assert second.reason == "free_quota_exhausted"
    assert len(calls) == 1
    assert stats["total_calls"] == 1
    assert stats["quota_used"] == 1
    assert stats["blocked_total"] == 1


def test_tradera_stops_before_second_network_call_when_daily_limit_is_hit(monkeypatch):
    calls = []

    def fake_post(url, data, timeout):
        calls.append((url, data, timeout))
        return _FakeResponse(
            text=(
                '<SearchResponse xmlns="http://api.tradera.com">'
                "<Items><Id>123</Id><ShortDescription>Sony WH-1000XM5</ShortDescription></Items>"
                "</SearchResponse>"
            )
        )

    object.__setattr__(settings, "tradera_app_id", 123)
    object.__setattr__(settings, "tradera_app_key", "test-key")
    object.__setattr__(settings, "tradera_free_daily_calls", 1)
    monkeypatch.setattr("backend.app.integrations.tradera_client.requests.post", fake_post)

    client = TraderaClient()
    first = client.search("Sony WH-1000XM5")
    second = client.search("Apple iPhone 13")

    stats = api_counter.get_stats()["sources"]["tradera"]
    assert len(first) == 1
    assert second == []
    assert len(calls) == 1
    assert stats["total_calls"] == 1
    assert stats["quota_used"] == 1
    assert stats["blocked_total"] == 1
