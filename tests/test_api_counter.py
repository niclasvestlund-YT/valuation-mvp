"""Tests for persistent API usage and free-tier quota tracking."""

import threading
import time
from pathlib import Path

import pytest

from backend.app.core.config import settings
from backend.app.utils import api_counter


@pytest.fixture(autouse=True)
def _reset_counter_and_limits():
    original_google_cse = settings.google_cse_free_daily_queries
    original_google_vision = settings.google_vision_free_monthly_units
    original_tradera = settings.tradera_free_daily_calls

    api_counter.reset()
    yield
    object.__setattr__(settings, "google_cse_free_daily_queries", original_google_cse)
    object.__setattr__(settings, "google_vision_free_monthly_units", original_google_vision)
    object.__setattr__(settings, "tradera_free_daily_calls", original_tradera)
    api_counter.reset()


class TestApiCounter:
    def test_increment_increases_total(self):
        api_counter.increment("tradera")
        api_counter.increment("tradera")
        stats = api_counter.get_stats()
        assert stats["sources"]["tradera"]["total_calls"] == 2

    def test_increment_error_increases_error_count(self):
        api_counter.increment_error("blocket")
        stats = api_counter.get_stats()
        assert stats["sources"]["blocket"]["error_calls"] == 1

    def test_success_rate_calculated_correctly(self):
        for _ in range(9):
            api_counter.increment("tradera")
        api_counter.increment_error("tradera")
        stats = api_counter.get_stats()
        assert stats["sources"]["tradera"]["success_rate_pct"] == 90

    def test_today_count_only_counts_today(self):
        api_counter.increment("vinted")
        stats = api_counter.get_stats()
        assert stats["sources"]["vinted"]["today"] == 1

    def test_reset_clears_all_counters(self):
        api_counter.increment("tradera")
        api_counter.increment_error("tradera")
        api_counter.reserve_quota("google_cse")
        api_counter.reset()
        stats = api_counter.get_stats()
        assert stats["sources"]["tradera"]["total_calls"] == 0
        assert stats["sources"]["tradera"]["error_calls"] == 0
        assert stats["sources"]["google_cse"]["quota_total"] == 0
        assert stats["total_all_sources"] == 0

    def test_reset_resets_started_at(self):
        old_since = api_counter.get_stats()["since"]
        time.sleep(0.01)
        api_counter.reset()
        new_since = api_counter.get_stats()["since"]
        assert new_since != old_since
        assert new_since > old_since

    def test_thread_safety(self):
        def worker():
            for _ in range(100):
                api_counter.increment("tradera")

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        stats = api_counter.get_stats()
        assert stats["sources"]["tradera"]["total_calls"] == 1000

    def test_persist_path_is_inside_project(self):
        persist_path = api_counter.get_persist_path()
        project_root = Path(__file__).resolve().parents[1]
        assert str(persist_path).startswith(str(project_root))
        assert persist_path.name == "api_counter.json"
        assert persist_path.parent.name == "logs"

    def test_daily_quota_blocks_after_limit(self):
        object.__setattr__(settings, "google_cse_free_daily_queries", 2)

        assert api_counter.reserve_quota("google_cse")["allowed"]
        assert api_counter.reserve_quota("google_cse")["allowed"]
        blocked = api_counter.reserve_quota("google_cse")

        stats = api_counter.get_stats()["sources"]["google_cse"]
        assert not blocked["allowed"]
        assert stats["quota_period"] == "day"
        assert stats["quota_limit"] == 2
        assert stats["quota_used"] == 2
        assert stats["quota_remaining"] == 0
        assert stats["blocked_total"] == 1
        assert stats["quota_exhausted"] is True

    def test_monthly_quota_tracks_units(self):
        object.__setattr__(settings, "google_vision_free_monthly_units", 6)

        assert api_counter.reserve_quota("google_vision_ocr", amount=3)["allowed"]
        assert api_counter.reserve_quota("google_vision_ocr", amount=3)["allowed"]
        blocked = api_counter.reserve_quota("google_vision_ocr", amount=3)

        stats = api_counter.get_stats()["sources"]["google_vision_ocr"]
        assert not blocked["allowed"]
        assert stats["quota_period"] == "month"
        assert stats["quota_unit_label"] == "units"
        assert stats["quota_limit"] == 6
        assert stats["quota_used"] == 6
        assert stats["quota_this_month"] == 6
        assert stats["blocked_this_month"] == 1

    def test_period_reset_only_clears_active_quota_windows(self):
        object.__setattr__(settings, "google_cse_free_daily_queries", 2)
        object.__setattr__(settings, "google_vision_free_monthly_units", 6)

        api_counter.increment("vision_openai")
        api_counter.reserve_quota("google_cse")
        api_counter.reserve_quota("google_vision_ocr", amount=3)
        api_counter.reserve_quota("google_vision_ocr", amount=3)
        api_counter.reserve_quota("google_vision_ocr", amount=3)

        api_counter.reset(scope="period")
        stats = api_counter.get_stats()

        assert stats["sources"]["vision_openai"]["total_calls"] == 1
        assert stats["sources"]["google_cse"]["quota_used"] == 0
        assert stats["sources"]["google_cse"]["blocked_today"] == 0
        assert stats["sources"]["google_cse"]["quota_total"] == 1
        assert stats["sources"]["google_vision_ocr"]["quota_used"] == 0
        assert stats["sources"]["google_vision_ocr"]["blocked_this_month"] == 0
        assert stats["sources"]["google_vision_ocr"]["quota_total"] == 6
