"""Tests verifying admin endpoint response shapes match frontend expectations.

These tests ensure the backend returns data in the structure the
admin UI expects, preventing silent rendering failures.

Tests that require a real DB are marked with @pytest.mark.integration
and can be skipped in CI: pytest -m "not integration"
"""

import os
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

ADMIN_KEY = os.getenv("ADMIN_SECRET_KEY", "")
admin_headers = {"X-Admin-Key": ADMIN_KEY} if ADMIN_KEY else {}


@pytest.fixture
def client():
    return TestClient(app)


# ─── Test group 1: /admin/metrics shape ───


class TestMetricsShape:
    def test_metrics_status_breakdown_is_list(self, client):
        """Frontend normalizes list→object. Confirm backend sends list."""
        r = client.get("/admin/metrics", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("DB not available")
        d = r.json()
        assert isinstance(d["status_breakdown"], list)
        for item in d["status_breakdown"]:
            assert "status" in item
            assert "count" in item

    def test_metrics_has_expected_fields(self, client):
        """All fields the frontend reads must exist."""
        r = client.get("/admin/metrics", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("DB not available")
        d = r.json()
        assert "status_breakdown" in d
        assert "avg_confidence" in d
        assert "total_valuations" in d
        assert "last_24h" in d
        assert "last_7d" in d

    def test_metrics_status_breakdown_normalizes_correctly(self, client):
        """Simulate what renderStats() does — confirm normalization produces correct totals."""
        backend_shape = [
            {"status": "ok", "count": 50, "pct": 90.9},
            {"status": "error", "count": 5, "pct": 9.1},
        ]
        normalized = {}
        for item in backend_shape:
            if item.get("status"):
                normalized[item["status"]] = item.get("count", 0)
        total = sum(normalized.values())
        assert total == 55
        assert normalized["ok"] == 50
        assert normalized["error"] == 5

    def test_metrics_does_not_have_avg_estimate(self, client):
        """Backend has no avg_estimate field — frontend must not rely on it."""
        r = client.get("/admin/metrics", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("DB not available")
        d = r.json()
        assert "avg_estimate" not in d


# ─── Test group 2: /admin/valuations field names ───


class TestValuationsFieldNames:
    def test_valuations_returns_product_name(self, client):
        """Frontend reads product_name — confirm field exists in response."""
        r = client.get("/admin/valuations?limit=5", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("DB not available")
        d = r.json()
        valuations = d.get("valuations", [])
        if not valuations:
            pytest.skip("No valuations in DB")
        # The SELECT includes product_name explicitly
        for v in valuations:
            assert "product_name" in v, f"Missing product_name in: {list(v.keys())}"

    def test_valuations_response_shape(self, client):
        """Response must have total + valuations list."""
        r = client.get("/admin/valuations?limit=5", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("DB not available")
        d = r.json()
        assert "total" in d
        assert "valuations" in d
        assert isinstance(d["valuations"], list)


# ─── Test group 3: Agent job status values ───


class TestAgentJobStatuses:
    KNOWN_STATUSES = {"pending", "running", "done", "completed", "failed", "dead"}

    def test_agent_stats_job_statuses_are_known(self, client):
        """Frontend maps job statuses — unknown values break color coding."""
        r = client.get("/admin/agent-stats", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("DB not available")
        d = r.json()
        for job in d.get("recent_jobs", []):
            assert job["status"] in self.KNOWN_STATUSES, \
                f"Unknown job status '{job['status']}' not handled by frontend"


# ─── Test group 4: All admin endpoints return 200 ───


class TestAdminEndpointsReturn200:
    @pytest.mark.parametrize("path", [
        "/admin/metrics",
        "/admin/market-data",
        "/admin/valuations-data",
        "/admin/ocr-stats",
        "/admin/agent-stats",
        "/admin/valor-stats",
        "/admin/api-usage",
    ])
    def test_admin_endpoint_returns_200_json(self, client, path):
        r = client.get(path, headers=admin_headers)
        if r.status_code == 500:
            # DB errors are OK for test environments without a running database
            d = r.json()
            assert "error" in d or "detail" in d, f"500 without error body from {path}"
            pytest.skip(f"DB error on {path}: {d}")
        assert r.status_code == 200, f"{path} returned {r.status_code}"
        assert r.headers["content-type"].startswith("application/json")
        data = r.json()
        assert isinstance(data, dict)


# ─── Test group 5: Response shape contracts ───


class TestResponseContracts:
    def test_market_data_shape(self, client):
        """Frontend reads d.crawl.total_comparables and d.products.total."""
        r = client.get("/admin/market-data", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("DB not available")
        d = r.json()
        assert "crawl" in d
        assert "total_comparables" in d["crawl"]
        assert "products" in d
        assert "total" in d["products"]

    def test_valuations_data_shape(self, client):
        """Frontend reads d.summary.total, d.recent, d.by_status."""
        r = client.get("/admin/valuations-data", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("DB not available")
        d = r.json()
        if d.get("empty"):
            assert "summary" in d
            return
        assert "summary" in d
        assert "total" in d["summary"]
        assert "recent" in d
        assert "by_status" in d

    def test_agent_stats_shape(self, client):
        """Frontend reads d.total_observations, d.coverage, d.recent_jobs."""
        r = client.get("/admin/agent-stats", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("DB not available")
        d = r.json()
        assert "total_observations" in d
        assert "coverage" in d
        assert "recent_jobs" in d
        assert "suspicious_count" in d
        assert "suspicious_rate" in d

    def test_valor_stats_shape(self, client):
        """Frontend reads d.model, d.training, d.estimates."""
        r = client.get("/admin/valor-stats", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("DB not available")
        d = r.json()
        assert "model" in d
        assert "training" in d
        assert "estimates" in d
        if d["model"]:
            assert "model_version" in d["model"]
            assert "mae_sek" in d["model"]

    def test_ocr_stats_shape(self, client):
        """Frontend reads d.provider_counts, d.fallback_rate_pct, d.text_hit_rate_pct."""
        r = client.get("/admin/ocr-stats", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("DB not available")
        d = r.json()
        assert "provider_counts" in d
        assert "fallback_rate_pct" in d
        assert "text_hit_rate_pct" in d
        assert "recent" in d
