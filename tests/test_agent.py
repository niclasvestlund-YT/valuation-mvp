"""Tests for the agent service — all DB calls mocked, no external APIs."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ["USE_MOCK_AGENT"] = "true"
os.environ["USE_MOCK_EMBEDDING"] = "true"

from backend.app.services.agent_service import (
    AgentIntent,
    build_context_block,
    build_no_data_context,
    parse_user_intent,
)


def _make_product(product_key="sony_wh-1000xm5", brand="Sony", model="WH-1000XM5",
                  category="headphones", valuation_count=5):
    p = MagicMock()
    p.product_key = product_key
    p.brand = brand
    p.model = model
    p.category = category
    p.valuation_count = valuation_count
    return p


def _make_comparable(title="Sony WH-1000XM5", price_sek=2500, source="tradera",
                     is_active=True, flagged=False, disappeared_at=None,
                     relevance_score=0.8):
    c = MagicMock()
    c.title = title
    c.price_sek = price_sek
    c.source = source
    c.is_active = is_active
    c.flagged = flagged
    c.disappeared_at = disappeared_at
    c.relevance_score = relevance_score
    from datetime import datetime, timezone
    c.last_seen = datetime.now(timezone.utc)
    c.first_seen = datetime.now(timezone.utc)
    return c


class TestParseUserIntent:
    def test_known_product_matches(self):
        """Product in DB with matching tokens -> returns product_key"""
        product = _make_product()
        with patch("backend.app.services.agent_service.async_session") as mock_session:
            session_ctx = AsyncMock()
            session_obj = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [product]
            session_obj.execute = AsyncMock(return_value=mock_result)
            session_ctx.__aenter__ = AsyncMock(return_value=session_obj)
            session_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session.return_value = session_ctx

            intent = asyncio.run(parse_user_intent("vad är min Sony WH-1000XM5 värd?"))
        assert intent.product_key == "sony_wh-1000xm5"

    def test_unknown_product_returns_none(self):
        """Product not in DB -> product_key is None"""
        with patch("backend.app.services.agent_service.async_session") as mock_session:
            session_ctx = AsyncMock()
            session_obj = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            session_obj.execute = AsyncMock(return_value=mock_result)
            session_ctx.__aenter__ = AsyncMock(return_value=session_obj)
            session_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session.return_value = session_ctx

            intent = asyncio.run(parse_user_intent("vad kostar en Nokia 3310?"))
        assert intent.product_key is None
        assert intent.candidates == []


class TestBuildContext:
    def test_no_data_context_no_candidates(self):
        context = asyncio.run(build_no_data_context("Nokia 3310"))
        assert "INGEN DATA" in context
        assert "Nokia 3310" in context

    def test_no_data_context_with_candidates(self):
        candidates = [_make_product("sony_wh-1000xm4", "Sony", "WH-1000XM4"),
                      _make_product("sony_wh-1000xm5", "Sony", "WH-1000XM5")]
        context = asyncio.run(build_no_data_context("sony hörlurar", candidates))
        assert "INGEN EXAKT MATCHNING" in context
        assert "WH-1000XM4" in context
        assert "WH-1000XM5" in context


class TestAgentResponseFormat:
    def test_response_always_has_data_source(self):
        """AgentResponse always says data_source='own_database'"""
        from backend.app.api.agent import AgentResponse
        resp = AgentResponse(reply="test", has_data=True, comparables_count=5)
        assert resp.data_source == "own_database"

    def test_response_default_no_data(self):
        from backend.app.api.agent import AgentResponse
        resp = AgentResponse(reply="no data")
        assert resp.has_data is False
        assert resp.comparables_count == 0


class TestContextBlockFormat:
    def test_context_has_required_fields(self):
        """Context block must contain product info, price stats, data freshness."""
        product = _make_product()
        comps = [
            _make_comparable(price_sek=2500, source="tradera"),
            _make_comparable(price_sek=2800, source="blocket"),
            _make_comparable(price_sek=3000, source="tradera"),
        ]

        with patch("backend.app.services.agent_service.async_session") as mock_session:
            session_ctx = AsyncMock()
            session_obj = AsyncMock()

            # First call: get product
            # Second call: get comparables
            # Third call: get new price
            call_count = 0
            async def mock_get(model, key):
                return product

            mock_comp_result = MagicMock()
            mock_comp_result.scalars.return_value.all.return_value = comps
            mock_np_result = MagicMock()
            mock_np_result.scalar_one_or_none.return_value = None

            session_obj.get = AsyncMock(side_effect=mock_get)
            execute_results = [mock_comp_result, mock_np_result]
            session_obj.execute = AsyncMock(side_effect=execute_results)

            session_ctx.__aenter__ = AsyncMock(return_value=session_obj)
            session_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session.return_value = session_ctx

            context = asyncio.run(build_context_block("sony_wh-1000xm5"))

        assert "PRODUKT: Sony WH-1000XM5" in context
        assert "Tradera:" in context
        assert "Blocket:" in context
        assert "DATAFÖRSKHET:" in context
        assert "Median:" in context


class TestNoExternalCalls:
    def test_agent_never_calls_external_apis(self):
        """Verify agent service has no imports of external API clients."""
        import inspect
        import backend.app.services.agent_service as mod
        source = inspect.getsource(mod)
        # Must NOT import any external API client
        forbidden = ["tradera_client", "blocket_client", "serper", "serpapi"]
        for name in forbidden:
            assert name not in source, f"agent_service.py imports {name} — violates own-data-only rule"
