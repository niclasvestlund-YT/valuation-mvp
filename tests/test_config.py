"""Unit tests for config.py — deploy-critical URL normalization and env reading.

These tests verify that DATABASE_URL is correctly normalized for each
environment and that the fail-closed behavior on Railway works as expected.
"""

import os
import unittest
from unittest.mock import patch

from backend.app.core.config import _normalize_database_url, _read_env, _read_bool_env


class TestNormalizeDatabaseUrl(unittest.TestCase):
    """_normalize_database_url must handle Railway, local, and edge cases."""

    @patch.dict(os.environ, {}, clear=False)
    def test_none_locally_returns_localhost_default(self):
        # Remove RAILWAY_ENVIRONMENT if set
        os.environ.pop("RAILWAY_ENVIRONMENT", None)
        result = _normalize_database_url(None)
        self.assertEqual(result, "postgresql+asyncpg://postgres:dev@localhost:5432/valuation")

    @patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "staging"})
    def test_none_on_railway_returns_empty_fail_closed(self):
        result = _normalize_database_url(None)
        self.assertEqual(result, "")

    @patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"})
    def test_none_on_railway_production_returns_empty(self):
        result = _normalize_database_url(None)
        self.assertEqual(result, "")

    def test_postgres_prefix_converted(self):
        result = _normalize_database_url("postgres://user:pass@host:5432/db")
        self.assertEqual(result, "postgresql+asyncpg://user:pass@host:5432/db")

    def test_postgresql_prefix_converted(self):
        result = _normalize_database_url("postgresql://user:pass@host:5432/db")
        self.assertEqual(result, "postgresql+asyncpg://user:pass@host:5432/db")

    def test_psycopg2_prefix_converted(self):
        result = _normalize_database_url("postgresql+psycopg2://user:pass@host:5432/db")
        self.assertEqual(result, "postgresql+asyncpg://user:pass@host:5432/db")

    def test_asyncpg_prefix_preserved(self):
        result = _normalize_database_url("postgresql+asyncpg://user:pass@host:5432/db")
        self.assertEqual(result, "postgresql+asyncpg://user:pass@host:5432/db")

    def test_empty_string_treated_as_none(self):
        os.environ.pop("RAILWAY_ENVIRONMENT", None)
        result = _normalize_database_url("")
        self.assertEqual(result, "postgresql+asyncpg://postgres:dev@localhost:5432/valuation")

    @patch.dict(os.environ, {}, clear=False)
    def test_whitespace_only_returns_empty_string(self):
        """Whitespace-only is truthy so it skips the None fallback.
        After strip() it's empty and matches no prefix — returns ''.
        In practice DATABASE_URL is never whitespace-only."""
        os.environ.pop("RAILWAY_ENVIRONMENT", None)
        result = _normalize_database_url("   ")
        self.assertEqual(result, "")


class TestReadEnv(unittest.TestCase):
    @patch.dict(os.environ, {"TEST_VAR": "hello"})
    def test_reads_existing_var(self):
        self.assertEqual(_read_env("TEST_VAR"), "hello")

    @patch.dict(os.environ, {"TEST_VAR": "  spaced  "})
    def test_strips_whitespace(self):
        self.assertEqual(_read_env("TEST_VAR"), "spaced")

    @patch.dict(os.environ, {"TEST_VAR": ""})
    def test_empty_returns_none(self):
        self.assertIsNone(_read_env("TEST_VAR"))

    def test_missing_returns_none(self):
        os.environ.pop("NONEXISTENT_VAR_12345", None)
        self.assertIsNone(_read_env("NONEXISTENT_VAR_12345"))


class TestReadBoolEnv(unittest.TestCase):
    @patch.dict(os.environ, {"TEST_BOOL": "true"})
    def test_true_variants(self):
        self.assertTrue(_read_bool_env("TEST_BOOL"))

    @patch.dict(os.environ, {"TEST_BOOL": "1"})
    def test_one_is_true(self):
        self.assertTrue(_read_bool_env("TEST_BOOL"))

    @patch.dict(os.environ, {"TEST_BOOL": "false"})
    def test_false(self):
        self.assertFalse(_read_bool_env("TEST_BOOL"))

    def test_missing_uses_default(self):
        os.environ.pop("NONEXISTENT_BOOL_12345", None)
        self.assertTrue(_read_bool_env("NONEXISTENT_BOOL_12345", default=True))
        self.assertFalse(_read_bool_env("NONEXISTENT_BOOL_12345", default=False))


if __name__ == "__main__":
    unittest.main()
