"""API-level tests for the chat agent endpoint."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.app.main import app


def _make_product():
    product = MagicMock()
    product.product_key = "sony_wh-1000xm5"
    product.brand = "Sony"
    product.model = "WH-1000XM5"
    product.category = "headphones"
    product.valuation_count = 4
    return product


def _make_comparable(title: str, price_sek: int, source: str, *, sold: bool):
    row = MagicMock()
    row.title = title
    row.price_sek = price_sek
    row.source = source
    row.flagged = False
    row.is_active = not sold
    row.relevance_score = 0.9
    row.first_seen = datetime(2026, 3, 20, tzinfo=timezone.utc)
    row.last_seen = datetime(2026, 3, 27, tzinfo=timezone.utc)
    row.disappeared_at = datetime(2026, 3, 27, tzinfo=timezone.utc) if sold else None
    return row


def test_agent_chat_returns_result_end_to_end():
    """POST /agent/chat should return a result when own-data context exists."""
    product = _make_product()
    comparables = [
        _make_comparable("Sony WH-1000XM5", 2500, "tradera", sold=False),
        _make_comparable("Sony WH-1000XM5", 2700, "blocket", sold=True),
    ]

    parse_result = MagicMock()
    parse_result.scalars.return_value.all.return_value = [product]

    comparables_result = MagicMock()
    comparables_result.scalars.return_value.all.return_value = comparables

    new_price_row = MagicMock()
    new_price_row.price_sek = 3990
    new_price_row.source = "prisjakt"
    new_price_row.fetched_at = datetime(2026, 3, 27, tzinfo=timezone.utc)
    new_price_result = MagicMock()
    new_price_result.scalar_one_or_none.return_value = new_price_row

    count_result = MagicMock()
    count_result.scalar.return_value = len(comparables)

    session_obj = AsyncMock()
    session_obj.execute = AsyncMock(
        side_effect=[parse_result, comparables_result, new_price_result, count_result]
    )
    session_obj.get = AsyncMock(return_value=product)

    session_ctx = AsyncMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session_obj)
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "backend.app.api.agent.settings",
            SimpleNamespace(agent_enabled=True, use_mock_agent=True),
        ),
        patch("backend.app.services.agent_service.async_session", return_value=session_ctx),
    ):
        client = TestClient(app)
        response = client.post(
            "/agent/chat",
            json={"message": "Vad är min Sony WH-1000XM5 värd?"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["product_key"] == "sony_wh-1000xm5"
    assert data["data_source"] == "own_database"
    assert data["has_data"] is True
    assert data["comparables_count"] == 2
    assert "sony_wh-1000xm5" in data["reply"]
    assert "2 jämförelseobjekt" in data["reply"]
