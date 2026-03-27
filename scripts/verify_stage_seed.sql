-- =============================================================================
-- verify_stage_seed.sql — Verify staging DB has correct seed data
-- =============================================================================
--
-- Run against staging DB:
--   psql "$STAGING_DATABASE_URL" -f scripts/verify_stage_seed.sql
--
-- Checks:
--   1. pgvector extension exists
--   2. All expected tables exist
--   3. Seed data row counts
--   4. No unexpected data in excluded tables
--   5. Basic data quality
--
-- =============================================================================

\echo '=== 1. pgvector extension ==='
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

\echo ''
\echo '=== 2. Table existence ==='
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

\echo ''
\echo '=== 3. Alembic migration status ==='
SELECT version_num FROM alembic_version;

\echo ''
\echo '=== 4. Seed data row counts ==='
SELECT 'product' AS tbl, COUNT(*) AS rows FROM product
UNION ALL SELECT 'market_comparable', COUNT(*) FROM market_comparable
UNION ALL SELECT 'new_price_snapshot', COUNT(*) FROM new_price_snapshot
ORDER BY tbl;

\echo ''
\echo '=== 5. Tables that SHOULD be empty (no seed data) ==='
SELECT 'valuations' AS tbl, COUNT(*) AS rows FROM valuations
UNION ALL SELECT 'price_snapshots', COUNT(*) FROM price_snapshots
UNION ALL SELECT 'product_embedding', COUNT(*) FROM product_embedding
UNION ALL SELECT 'agent_job', COUNT(*) FROM agent_job
UNION ALL SELECT 'price_observation', COUNT(*) FROM price_observation
UNION ALL SELECT 'training_sample', COUNT(*) FROM training_sample
UNION ALL SELECT 'valor_model', COUNT(*) FROM valor_model
UNION ALL SELECT 'valor_estimate', COUNT(*) FROM valor_estimate
UNION ALL SELECT 'price_statistic', COUNT(*) FROM price_statistic
ORDER BY tbl;

\echo ''
\echo '=== 6. Data quality checks ==='

-- Products have brands
SELECT 'products_missing_brand' AS check,
       COUNT(*) AS count
FROM product WHERE brand IS NULL OR brand = '';

-- Comparables in sane price range
SELECT 'comparables_outside_200_150k' AS check,
       COUNT(*) AS count
FROM market_comparable
WHERE price_sek < 200 OR price_sek > 150000;

-- No flagged comparables in seed
SELECT 'flagged_comparables' AS check,
       COUNT(*) AS count
FROM market_comparable WHERE flagged = true;

-- Product coverage (products with comparables)
SELECT 'products_with_comparables' AS check,
       COUNT(DISTINCT mc.product_key) AS count
FROM market_comparable mc;

\echo ''
\echo '=== 7. Sample products ==='
SELECT p.product_key, p.brand, p.model, p.category,
       COUNT(mc.id) AS comparables
FROM product p
LEFT JOIN market_comparable mc ON mc.product_key = p.product_key AND mc.is_active = true
GROUP BY p.product_key, p.brand, p.model, p.category
ORDER BY comparables DESC
LIMIT 10;

\echo ''
\echo '=== Verification complete ==='
