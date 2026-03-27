"""Tests for the API call counter."""

import threading
from pathlib import Path

from backend.app.utils import api_counter


class TestApiCounter:
    def test_increment_increases_total(self):
        api_counter.reset()
        api_counter.increment("tradera")
        api_counter.increment("tradera")
        stats = api_counter.get_stats()
        assert stats["sources"]["tradera"]["total_calls"] == 2

    def test_increment_error_increases_error_count(self):
        api_counter.reset()
        api_counter.increment_error("blocket")
        stats = api_counter.get_stats()
        assert stats["sources"]["blocket"]["error_calls"] == 1

    def test_success_rate_calculated_correctly(self):
        api_counter.reset()
        for _ in range(9):
            api_counter.increment("tradera")
        api_counter.increment_error("tradera")
        stats = api_counter.get_stats()
        assert stats["sources"]["tradera"]["success_rate_pct"] == 90

    def test_today_count_only_counts_today(self):
        api_counter.reset()
        api_counter.increment("vinted")
        stats = api_counter.get_stats()
        assert stats["sources"]["vinted"]["today"] == 1

    def test_reset_clears_all_counters(self):
        api_counter.increment("tradera")
        api_counter.increment_error("tradera")
        api_counter.reset()
        stats = api_counter.get_stats()
        assert stats["sources"]["tradera"]["total_calls"] == 0
        assert stats["sources"]["tradera"]["error_calls"] == 0
        assert stats["total_all_sources"] == 0

    def test_reset_resets_started_at(self):
        """reset() should update the 'since' timestamp to now."""
        api_counter.reset()
        old_since = api_counter.get_stats()["since"]
        # Small delay to ensure timestamp differs
        import time
        time.sleep(0.01)
        api_counter.reset()
        new_since = api_counter.get_stats()["since"]
        assert new_since != old_since, "reset() should update started_at"
        assert new_since > old_since, "new timestamp should be later"

    def test_thread_safety(self):
        api_counter.reset()

        def worker():
            for _ in range(100):
                api_counter.increment("tradera")

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        stats = api_counter.get_stats()
        assert stats["sources"]["tradera"]["total_calls"] == 1000

    def test_persist_path_is_inside_project(self):
        """Persist file must be inside the project root, not a parent directory."""
        persist_path = api_counter.get_persist_path()
        project_root = Path(__file__).resolve().parents[1]  # tests/ -> project root
        assert str(persist_path).startswith(str(project_root)), (
            f"Persist path {persist_path} is outside project root {project_root}"
        )
        assert persist_path.name == "api_counter.json"
        assert persist_path.parent.name == "logs"
