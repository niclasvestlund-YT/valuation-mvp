#!/bin/sh
# stage_ready_check.sh — focused local gate for safe develop -> staging merges.
set -eu

REPO_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

if [ -x "$REPO_DIR/.venv/bin/python" ]; then
    PY="$REPO_DIR/.venv/bin/python"
else
    PY="python"
fi

echo "Running stage-ready test suite..."
"$PY" -m pytest \
    -m "not integration" \
    tests/test_admin_html.py \
    tests/test_admin_ui_data.py \
    tests/test_golden_cases.py \
    tests/test_config.py \
    -q

echo ""
echo "Stage-ready local checks passed."
echo "Before calling a change staging-ready, also verify:"
echo "  1. Railway vars: DATABASE_URL, ADMIN_SECRET_KEY, ALLOWED_ORIGINS, USE_MOCK_EMBEDDING, USE_MOCK_EASYOCR, CRAWLER_ENABLED"
echo "  2. Migrations: railway run -e staging bash -c \"cd backend && alembic upgrade head\""
echo "  3. Reference data import: STAGING_DATABASE_URL=... python scripts/promote_reference_data.py import --target staging"
echo "  4. Reference data verify: STAGING_DATABASE_URL=... python scripts/promote_reference_data.py verify --target staging"
echo "  5. Smoke test: /health, /admin, /admin/overview, /admin/metrics, /admin/market-data, /admin/valor-stats"
