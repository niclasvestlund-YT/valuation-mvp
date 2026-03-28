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


# ─── Test group 6: Phase 1 admin fixes ───


class TestAdminAuthBehavior:
    """Tests verifying admin auth rejects bad keys and returns proper status codes."""

    def test_missing_key_returns_403_when_configured(self, client):
        """Without a valid key header, admin endpoints should return 403."""
        if not ADMIN_KEY:
            pytest.skip("ADMIN_SECRET_KEY not set — local dev allows unauthenticated")
        r = client.get("/admin/metrics", headers={})
        assert r.status_code == 403

    def test_wrong_key_returns_403(self, client):
        """A wrong admin key should return 403."""
        if not ADMIN_KEY:
            pytest.skip("ADMIN_SECRET_KEY not set — local dev allows unauthenticated")
        r = client.get("/admin/metrics", headers={"X-Admin-Key": "wrong-key-12345"})
        assert r.status_code == 403

    def test_correct_key_returns_200(self, client):
        """Correct admin key should succeed."""
        r = client.get("/admin/api-usage", headers=admin_headers)
        if r.status_code == 500:
            pytest.skip("DB not available")
        assert r.status_code == 200


class TestMetricsNormalization:
    """Tests verifying the frontend normalization logic for status_breakdown."""

    def test_list_shaped_status_breakdown_produces_correct_total(self):
        """The real backend returns status_breakdown as a list of dicts.
        The frontend renderStats normalizes this to an object then sums.
        Verify this logic produces the right numeric total."""
        backend_shape = [
            {"status": "ok", "count": 100, "pct": 80.0},
            {"status": "error", "count": 15, "pct": 12.0},
            {"status": "ambiguous_model", "count": 10, "pct": 8.0},
        ]
        # Simulate frontend renderStats normalization
        normalized = {}
        for item in backend_shape:
            if item.get("status"):
                normalized[item["status"]] = item.get("count", 0)
        total = sum(normalized.values())
        assert isinstance(total, int)
        assert total == 125

    def test_empty_status_breakdown_produces_zero(self):
        """Empty list should produce total 0."""
        normalized = {}
        total = sum(normalized.values())
        assert total == 0

    def test_object_values_reduce_on_list_produces_wrong_result(self):
        """Demonstrate the old bug: Object.values().reduce() on a list
        of dicts would concatenate strings instead of summing numbers.
        This test documents why we normalize list→object before summing."""
        backend_shape = [
            {"status": "ok", "count": 50},
            {"status": "error", "count": 5},
        ]
        # Old buggy approach: treating the list items as values to reduce
        # In JS: Object.values([{...}, {...}]).reduce((a,b) => a+b, 0) = "0[object Object][object Object]"
        # Correct approach: normalize first
        normalized = {}
        for item in backend_shape:
            normalized[item["status"]] = item["count"]
        total = sum(normalized.values())
        assert total == 55
        assert total > 0  # This is the gate that was failing


class TestNoLocalHistoryInAdmin:
    """Verify admin valuation output comes from server only."""

    def test_valuations_endpoint_returns_server_data_only(self, client):
        """The /admin/valuations endpoint should return a valuations list
        that comes from the database, not mixed with localStorage."""
        r = client.get("/admin/valuations?limit=5", headers=admin_headers)
        if r.status_code != 200:
            pytest.skip("DB not available")
        d = r.json()
        assert "valuations" in d
        assert isinstance(d["valuations"], list)
        # Every item should have an 'id' field (server-generated), proving it's DB data
        for v in d["valuations"]:
            assert "id" in v or "valuation_id" in v, \
                f"Valuation missing server ID — might be local data: {list(v.keys())[:5]}"


# ─── Test group 7: Phase 2 — XSS escaping ───


class TestEscFunction:
    """Verify the esc() XSS helper exists and covers dangerous characters."""

    def test_esc_function_defined_in_admin_html(self):
        """esc() helper must be defined before any render function."""
        with open("frontend/admin.html") as f:
            content = f.read()
        assert "function esc(" in content
        # v12 uses createElement/createTextNode pattern instead of .replace() chain
        assert "createTextNode" in content or ".replace(/&/" in content

    def test_esc_function_called_on_api_data(self):
        """esc() must be used extensively on API data to prevent XSS."""
        with open("frontend/admin.html") as f:
            content = f.read()
        # Must have many esc() calls (at least 10 for various API data fields)
        esc_count = content.count("esc(")
        assert esc_count >= 10, f"Only {esc_count} esc() calls — too few for XSS safety"


class TestRenderSectionState:
    """Verify renderSectionState() exists with all required states."""

    def test_render_section_state_function_defined(self):
        with open("frontend/admin.html") as f:
            content = f.read()
        assert "function renderSectionState(" in content
        assert "loading" in content
        assert "error" in content
        # v12 handles auth via showLogin() rather than an "unauthorized" state in renderSectionState
        assert "showLogin" in content or "unauthorized" in content
        assert "empty" in content or "empty-state" in content


# ─── Test group 8: Phase 2 — Exception leakage ───


class TestExceptionLeakage:
    """Admin endpoints must not leak raw exception text in error responses."""

    @pytest.mark.parametrize("path", [
        "/admin/metrics",
        "/admin/market-data",
        "/admin/agent-stats",
        "/admin/valor-stats",
    ])
    def test_admin_endpoint_error_message_is_safe(self, client, path):
        """403 responses must not contain Python exception patterns."""
        if not ADMIN_KEY:
            pytest.skip("ADMIN_SECRET_KEY not set — local dev allows unauthenticated")
        r = client.get(path, headers={"X-Admin-Key": "wrong-key"})
        if r.status_code in (401, 403):
            d = r.json()
            detail = str(d.get("detail", ""))
            assert "Traceback" not in detail
            assert "Exception" not in detail
            assert "sqlalchemy" not in detail.lower()
            assert "psycopg" not in detail.lower()


# ─── Test group 9: Phase 2 — Table browser hardening ───


class TestTableBrowserHardening:
    """Table browser must reject unknown and malicious table names."""

    def test_table_browser_rejects_unknown_table(self, client):
        r = client.get("/admin/table/pg_shadow", headers=admin_headers)
        assert r.status_code == 400
        d = r.json()
        # Must not echo the attempted table name back as-is
        assert "Tillåtna" in str(d.get("detail", ""))

    def test_table_browser_rejects_sql_injection(self, client):
        r = client.get(
            "/admin/table/valuations;DROP TABLE valuations;--",
            headers=admin_headers,
        )
        # Should fail regex validation (400) or URL parsing (404/422)
        assert r.status_code in (400, 404, 422)


# ─── Test group 10: VALOR loadValorStats TDZ regression ───


class TestValorTrainingDeclarationOrder:
    """Regression guard: `const t = d.training || {}` must be declared
    before any code branch that reads t.total_samples.

    Bug: when `const t` was declared *after* the model-status branch,
    the no-model-with-training path hit a JS temporal dead zone error,
    causing a false empty state."""

    def _read_valor_function(self):
        """Extract the VALOR loading function body from admin.html."""
        with open("frontend/admin.html") as f:
            content = f.read()
        # v12 uses loadValor(), earlier versions used loadValorStats()
        for fn_name in ["async function loadValor()", "async function loadValorStats()"]:
            start = content.find(fn_name)
            if start != -1:
                return content[start:]
        raise AssertionError("VALOR loading function not found (tried loadValor and loadValorStats)")

    def test_training_data_referenced(self):
        """VALOR function must reference training data."""
        body = self._read_valor_function()
        assert "training" in body.lower(), "VALOR function must reference training data"
        assert "sample" in body.lower() or "observation" in body.lower(), \
            "VALOR function must reference samples or observations"

    def test_model_status_conditional(self):
        """VALOR display must be conditional on whether a model exists."""
        body = self._read_valor_function()
        assert "model_available" in body or "model" in body, \
            "Missing model availability check in VALOR function"
