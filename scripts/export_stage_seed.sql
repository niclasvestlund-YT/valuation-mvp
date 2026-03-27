-- =============================================================================
-- export_stage_seed.sql — Export curated seed data for Railway staging
-- =============================================================================
--
-- Run against your LOCAL database:
--   psql -d valuation -f scripts/export_stage_seed.sql
--
-- Produces three CSV files in /tmp/stage_seed/:
--   products.csv
--   comparables.csv
--   new_prices.csv
--
-- Filters:
--   - Only products seen in the last 30 days
--   - Only products with >= 3 active, unflagged comparables
--   - Only comparables with sane prices (200-150000 SEK)
--   - Only unflagged comparables
--   - Only new_price_snapshots from last 14 days
--   - No embeddings, valuations, feedback, agent data, or VALOR tables
--
-- =============================================================================

-- Create output directory
\! mkdir -p /tmp/stage_seed

-- Step 1: Identify qualifying product_keys
CREATE TEMP TABLE _seed_keys AS
SELECT p.product_key
FROM product p
JOIN market_comparable mc ON mc.product_key = p.product_key
WHERE mc.is_active = true
  AND mc.flagged = false
  AND mc.price_sek BETWEEN 200 AND 150000
  AND p.last_seen >= NOW() - INTERVAL '30 days'
GROUP BY p.product_key
HAVING COUNT(*) >= 3;

-- Report what we're exporting
SELECT COUNT(*) AS qualifying_products FROM _seed_keys;

-- Step 2: Export products
\copy (SELECT p.* FROM product p JOIN _seed_keys s ON s.product_key = p.product_key ORDER BY p.product_key) TO '/tmp/stage_seed/products.csv' WITH CSV HEADER;

-- Step 3: Export comparables (unflagged, sane price, active)
\copy (SELECT mc.* FROM market_comparable mc JOIN _seed_keys s ON s.product_key = mc.product_key WHERE mc.is_active = true AND mc.flagged = false AND mc.price_sek BETWEEN 200 AND 150000 ORDER BY mc.product_key, mc.last_seen DESC) TO '/tmp/stage_seed/comparables.csv' WITH CSV HEADER;

-- Step 4: Export new price snapshots (recent only)
\copy (SELECT nps.* FROM new_price_snapshot nps JOIN _seed_keys s ON s.product_key = nps.product_key WHERE nps.fetched_at >= NOW() - INTERVAL '14 days' ORDER BY nps.product_key, nps.fetched_at DESC) TO '/tmp/stage_seed/new_prices.csv' WITH CSV HEADER;

-- Report counts
SELECT 'products' AS table_name, COUNT(*) AS rows FROM product p JOIN _seed_keys s ON s.product_key = p.product_key
UNION ALL
SELECT 'comparables', COUNT(*) FROM market_comparable mc JOIN _seed_keys s ON s.product_key = mc.product_key WHERE mc.is_active = true AND mc.flagged = false AND mc.price_sek BETWEEN 200 AND 150000
UNION ALL
SELECT 'new_prices', COUNT(*) FROM new_price_snapshot nps JOIN _seed_keys s ON s.product_key = nps.product_key WHERE nps.fetched_at >= NOW() - INTERVAL '14 days';

DROP TABLE _seed_keys;

\echo ''
\echo 'Seed files written to /tmp/stage_seed/'
\echo 'Next: import into staging with scripts/import_stage_seed.sh'
