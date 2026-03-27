#!/usr/bin/env bash
# =============================================================================
# import_stage_seed.sh — Import curated seed data into Railway staging DB
# =============================================================================
#
# Prerequisites:
#   1. Alembic migrations already applied to staging DB
#   2. Seed CSV files in /tmp/stage_seed/ (from export_stage_seed.sql)
#   3. STAGING_DATABASE_URL set (psycopg2/libpq format, NOT asyncpg)
#
# Usage:
#   STAGING_DATABASE_URL="postgresql://user:pass@host:port/db" bash scripts/import_stage_seed.sh
#
# Or with Railway CLI:
#   railway run --environment staging bash scripts/import_stage_seed.sh
#   (uses $DATABASE_URL from Railway env)
#
# =============================================================================

set -euo pipefail

DB_URL="${STAGING_DATABASE_URL:-${DATABASE_URL:-}}"

if [ -z "$DB_URL" ]; then
    echo "ERROR: Set STAGING_DATABASE_URL or DATABASE_URL"
    exit 1
fi

# Normalize URL for psql (strip asyncpg driver prefix if present)
DB_URL="${DB_URL/postgresql+asyncpg:\/\//postgresql:\/\/}"
DB_URL="${DB_URL/postgresql+psycopg2:\/\//postgresql:\/\/}"

SEED_DIR="/tmp/stage_seed"

if [ ! -d "$SEED_DIR" ]; then
    echo "ERROR: $SEED_DIR not found. Run export_stage_seed.sql first."
    exit 1
fi

echo "=== Importing seed data into staging ==="
echo "DB: ${DB_URL%%@*}@***"
echo ""

# Import order matters: products first (FK parent), then children
echo "1/3  Importing products..."
psql "$DB_URL" -c "\copy product FROM '$SEED_DIR/products.csv' WITH CSV HEADER"

echo "2/3  Importing comparables..."
psql "$DB_URL" -c "\copy market_comparable FROM '$SEED_DIR/comparables.csv' WITH CSV HEADER"

echo "3/3  Importing new price snapshots..."
psql "$DB_URL" -c "\copy new_price_snapshot FROM '$SEED_DIR/new_prices.csv' WITH CSV HEADER"

echo ""
echo "=== Import complete ==="
echo ""

# Run verification
echo "=== Verifying import ==="
psql "$DB_URL" -f scripts/verify_stage_seed.sql
