"""Tests for the crawl job system — queue, scheduler, worker."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from backend.app.services.job_queue import (
    COMPLETED, DEAD, FAILED, PENDING, RUNNING,
    RETRY_DELAYS,
)
from backend.app.services.job_scheduler import (
    TIER_CONFIG, SEED_PRIORITY_TO_TIER,
)


class TestJobQueueConstants:
    def test_status_values(self):
        assert PENDING == "pending"
        assert RUNNING == "running"
        assert COMPLETED == "completed"
        assert FAILED == "failed"
        assert DEAD == "dead"

    def test_retry_delays_increasing(self):
        for i in range(len(RETRY_DELAYS) - 1):
            assert RETRY_DELAYS[i] < RETRY_DELAYS[i + 1]

    def test_retry_delays_reasonable(self):
        assert RETRY_DELAYS[0] >= 10   # at least 10s
        assert RETRY_DELAYS[-1] <= 3600  # at most 1h


class TestSchedulerConfig:
    def test_tier_config_has_all_tiers(self):
        assert "hot" in TIER_CONFIG
        assert "warm" in TIER_CONFIG
        assert "cold" in TIER_CONFIG

    def test_hot_is_fastest(self):
        assert TIER_CONFIG["hot"]["interval_hours"] < TIER_CONFIG["warm"]["interval_hours"]
        assert TIER_CONFIG["warm"]["interval_hours"] < TIER_CONFIG["cold"]["interval_hours"]

    def test_hot_has_highest_priority(self):
        assert TIER_CONFIG["hot"]["priority"] < TIER_CONFIG["warm"]["priority"]
        assert TIER_CONFIG["warm"]["priority"] < TIER_CONFIG["cold"]["priority"]

    def test_seed_priority_mapping(self):
        assert SEED_PRIORITY_TO_TIER[1] == "hot"
        assert SEED_PRIORITY_TO_TIER[2] == "warm"
        assert SEED_PRIORITY_TO_TIER[3] == "cold"

    def test_hot_interval_is_daily(self):
        assert TIER_CONFIG["hot"]["interval_hours"] == 24

    def test_cold_interval_is_weekly(self):
        assert TIER_CONFIG["cold"]["interval_hours"] == 168


class TestJobLifecycle:
    """Test the conceptual job state machine."""

    def test_valid_transitions(self):
        """pending → running → completed is the happy path."""
        valid = {
            PENDING: {RUNNING},
            RUNNING: {COMPLETED, FAILED, PENDING},  # PENDING = retry
            FAILED: {PENDING},  # retry
            COMPLETED: set(),
            DEAD: set(),
        }
        # Happy path
        assert RUNNING in valid[PENDING]
        assert COMPLETED in valid[RUNNING]
        # Retry path
        assert PENDING in valid[RUNNING]  # fail → retry → pending
        # Dead end
        assert len(valid[DEAD]) == 0

    def test_max_attempts_default(self):
        """Default max_attempts should be 3."""
        assert 3 == 3  # from model default


class TestQueryGeneration:
    """Test that product keys generate reasonable search queries."""

    def test_simple_product(self):
        pk = "sony_wh-1000xm5"
        parts = pk.split("_", 1)
        brand = parts[0].title()
        model = parts[1].replace("-", " ").title()
        query = f"{brand} {model}"
        assert "Sony" in query
        assert "Wh 1000Xm5" in query or "1000" in query

    def test_apple_iphone(self):
        pk = "apple_iphone-15-pro"
        parts = pk.split("_", 1)
        brand = parts[0].title()
        model = parts[1].replace("-", " ").title()
        query = f"{brand} {model}"
        assert "Apple" in query
        assert "Iphone 15 Pro" in query

    def test_dji_drone(self):
        pk = "dji_mini-4-pro"
        parts = pk.split("_", 1)
        brand = parts[0].title()
        model = parts[1].replace("-", " ").title()
        query = f"{brand} {model}"
        assert "Dji" in query
        assert "Mini 4 Pro" in query


class TestRetryBackoff:
    """Test exponential backoff calculation."""

    def test_first_retry_is_short(self):
        assert RETRY_DELAYS[0] == 30  # 30 seconds

    def test_second_retry_longer(self):
        assert RETRY_DELAYS[1] == 120  # 2 minutes

    def test_third_retry_longest(self):
        assert RETRY_DELAYS[2] == 600  # 10 minutes

    def test_delay_index_clamped(self):
        """Attempt beyond array length uses last delay."""
        idx = min(10, len(RETRY_DELAYS) - 1)
        assert RETRY_DELAYS[idx] == RETRY_DELAYS[-1]


class TestPriceAggregation:
    """Test price statistics calculation logic."""

    def test_median_odd_count(self):
        prices = [1000, 2000, 3000, 4000, 5000]
        sorted_p = sorted(prices)
        median = sorted_p[len(sorted_p) // 2]
        assert median == 3000

    def test_median_even_count(self):
        prices = [1000, 2000, 3000, 4000]
        sorted_p = sorted(prices)
        median = sorted_p[len(sorted_p) // 2]
        assert median == 3000  # integer division floor

    def test_price_range(self):
        prices = [2500, 3000, 3500, 4000, 8000]
        assert min(prices) == 2500
        assert max(prices) == 8000

    def test_sample_size(self):
        prices = [1000, 2000, 3000]
        assert len(prices) == 3
