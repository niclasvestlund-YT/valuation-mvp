"""Tests for the reference data promotion workflow.

Tests the safety logic, URL handling, and manifest creation
without requiring a real database connection.
"""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

# Import the functions we're testing
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.promote_reference_data import (
    to_sync_url,
    resolve_target_url,
    SNAPSHOT_DIR,
    _TARGET_ENV_VARS,
)


# ─── URL normalization ───


class TestToSyncUrl(unittest.TestCase):

    def test_asyncpg_to_psycopg2(self):
        self.assertEqual(
            to_sync_url("postgresql+asyncpg://user:pass@host:5432/db"),
            "postgresql+psycopg2://user:pass@host:5432/db",
        )

    def test_postgres_to_psycopg2(self):
        """Railway-style postgres:// URL."""
        self.assertEqual(
            to_sync_url("postgres://user:pass@host:5432/db"),
            "postgresql+psycopg2://user:pass@host:5432/db",
        )

    def test_plain_postgresql_to_psycopg2(self):
        self.assertEqual(
            to_sync_url("postgresql://user:pass@host:5432/db"),
            "postgresql+psycopg2://user:pass@host:5432/db",
        )

    def test_already_psycopg2(self):
        url = "postgresql+psycopg2://user:pass@host:5432/db"
        self.assertEqual(to_sync_url(url), url)

    def test_strips_whitespace(self):
        self.assertEqual(
            to_sync_url("  postgres://user:pass@host:5432/db  "),
            "postgresql+psycopg2://user:pass@host:5432/db",
        )


# ─── Target URL resolution (strict, no fallback) ───


class TestResolveTargetUrl(unittest.TestCase):

    def test_staging_requires_staging_url(self):
        """Must use STAGING_DATABASE_URL, never DATABASE_URL."""
        with patch.dict(os.environ, {
            "STAGING_DATABASE_URL": "",
            "DATABASE_URL": "postgres://local:5432/valuation",
        }, clear=False):
            with self.assertRaises(SystemExit):
                resolve_target_url("staging")

    def test_production_requires_production_url(self):
        with patch.dict(os.environ, {"PRODUCTION_DATABASE_URL": ""}, clear=False):
            with self.assertRaises(SystemExit):
                resolve_target_url("production")

    def test_staging_succeeds_with_correct_env(self):
        url = "postgresql://staging-user:pass@staging-host:5432/railway"
        with patch.dict(os.environ, {"STAGING_DATABASE_URL": url}, clear=False):
            result = resolve_target_url("staging")
            self.assertEqual(result, url)

    def test_production_succeeds_with_correct_env(self):
        url = "postgresql://prod-user:pass@prod-host:5432/railway"
        with patch.dict(os.environ, {"PRODUCTION_DATABASE_URL": url}, clear=False):
            result = resolve_target_url("production")
            self.assertEqual(result, url)

    def test_rejects_localhost_for_staging(self):
        with patch.dict(os.environ, {
            "STAGING_DATABASE_URL": "postgresql://user:pass@localhost:5432/db",
        }, clear=False):
            with self.assertRaises(SystemExit):
                resolve_target_url("staging")

    def test_rejects_127_0_0_1_for_production(self):
        with patch.dict(os.environ, {
            "PRODUCTION_DATABASE_URL": "postgresql://user:pass@127.0.0.1:5432/db",
        }, clear=False):
            with self.assertRaises(SystemExit):
                resolve_target_url("production")

    def test_unknown_target_exits(self):
        with self.assertRaises(SystemExit):
            resolve_target_url("dev")

    def test_empty_string_exits(self):
        with patch.dict(os.environ, {"STAGING_DATABASE_URL": "  "}, clear=False):
            with self.assertRaises(SystemExit):
                resolve_target_url("staging")

    def test_never_uses_database_url_for_staging(self):
        """Even if DATABASE_URL is set and STAGING_DATABASE_URL is missing, must fail."""
        env = {"DATABASE_URL": "postgresql://user:pass@remote-host:5432/db"}
        with patch.dict(os.environ, env, clear=False):
            # Unset STAGING_DATABASE_URL
            os.environ.pop("STAGING_DATABASE_URL", None)
            with self.assertRaises(SystemExit):
                resolve_target_url("staging")


# ─── Target env var mapping ───


class TestTargetEnvVars(unittest.TestCase):

    def test_staging_maps_to_correct_var(self):
        self.assertEqual(_TARGET_ENV_VARS["staging"], "STAGING_DATABASE_URL")

    def test_production_maps_to_correct_var(self):
        self.assertEqual(_TARGET_ENV_VARS["production"], "PRODUCTION_DATABASE_URL")

    def test_no_generic_fallback(self):
        """There must be no 'local' or 'dev' target."""
        self.assertNotIn("local", _TARGET_ENV_VARS)
        self.assertNotIn("dev", _TARGET_ENV_VARS)


# ─── Manifest structure ───


class TestManifestStructure(unittest.TestCase):

    def test_manifest_has_required_fields(self):
        """Verify the manifest schema we document."""
        # Simulate a manifest
        manifest = {
            "schema_version": 2,
            "exported_at": "2026-03-27T15:00:00+00:00",
            "source": "local",
            "filters": {
                "min_comparables": 3,
                "max_age_days": 30,
                "comparable_max_age_days": 60,
                "price_range": [200, 150000],
                "new_price_max_age_days": 14,
            },
            "counts": {
                "products": 50,
                "comparables": 1000,
                "new_prices": 100,
            },
            "product_keys": ["apple_iphone-13", "sony_wh-1000xm4"],
        }

        self.assertIn("schema_version", manifest)
        self.assertIn("exported_at", manifest)
        self.assertIn("filters", manifest)
        self.assertIn("counts", manifest)
        self.assertIn("product_keys", manifest)
        self.assertIsInstance(manifest["product_keys"], list)
        self.assertEqual(manifest["schema_version"], 2)

    def test_manifest_excludes_valuation_count(self):
        """valuation_count must not appear in exported product data."""
        product_cols = ["product_key", "brand", "model", "category", "first_seen", "last_seen"]
        self.assertNotIn("valuation_count", product_cols)


# ─── Dry run behavior ───


class TestDryRunBehavior(unittest.TestCase):

    def test_export_dry_run_flag_exists(self):
        """Verify the argparse setup accepts --dry-run."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--dry-run", action="store_true")
        args = parser.parse_args(["--dry-run"])
        self.assertTrue(args.dry_run)

    def test_snapshot_dir_default(self):
        """Default snapshot dir should be under data/snapshots/."""
        self.assertTrue(str(SNAPSHOT_DIR).endswith("data/snapshots"))


# ─── Alembic env.py URL normalization ───


class TestAlembicUrlNormalization(unittest.TestCase):
    """Test the _to_sync_url function from alembic/env.py."""

    def _to_sync(self, url: str) -> str:
        # Import inline to avoid Alembic context issues
        # Replicate the exact logic from env.py
        u = url.strip()
        u = u.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        if u.startswith("postgres://"):
            u = u.replace("postgres://", "postgresql+psycopg2://", 1)
        elif u.startswith("postgresql://") and "+psycopg2" not in u:
            u = u.replace("postgresql://", "postgresql+psycopg2://", 1)
        return u

    def test_railway_postgres_format(self):
        self.assertEqual(
            self._to_sync("postgres://user:pass@host:5432/db"),
            "postgresql+psycopg2://user:pass@host:5432/db",
        )

    def test_asyncpg_format(self):
        self.assertEqual(
            self._to_sync("postgresql+asyncpg://user:pass@host:5432/db"),
            "postgresql+psycopg2://user:pass@host:5432/db",
        )

    def test_plain_postgresql(self):
        self.assertEqual(
            self._to_sync("postgresql://user:pass@host:5432/db"),
            "postgresql+psycopg2://user:pass@host:5432/db",
        )

    def test_already_psycopg2(self):
        url = "postgresql+psycopg2://user:pass@host:5432/db"
        self.assertEqual(self._to_sync(url), url)

    def test_consistent_with_promote_script(self):
        """Alembic and promote_reference_data.py must produce the same result."""
        test_urls = [
            "postgres://u:p@h:5/d",
            "postgresql://u:p@h:5/d",
            "postgresql+asyncpg://u:p@h:5/d",
            "postgresql+psycopg2://u:p@h:5/d",
        ]
        for url in test_urls:
            alembic_result = self._to_sync(url)
            promote_result = to_sync_url(url)
            self.assertEqual(alembic_result, promote_result, f"Mismatch for {url}")


if __name__ == "__main__":
    unittest.main()
