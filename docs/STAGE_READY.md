# Stage Ready

Keep `develop` close enough to merge into `staging` without surprises.

## Local Gate

Run this before pushing and before merging `develop` into `staging`:

```bash
make stage-ready
```

It runs the focused suite that currently protects:
- admin UI structure
- admin frontend-backend data contracts
- golden valuation cases
- deploy-critical config behavior

It intentionally skips tests marked `integration`, because those need a running app or live environment and belong in manual staging verification.

## What Still Needs Manual Staging Verification

Local green does not mean staging is done. Before calling a change staging-ready:

1. Verify Railway web-service vars:
   - `DATABASE_URL`
   - `ADMIN_SECRET_KEY`
   - `ALLOWED_ORIGINS`
   - `USE_MOCK_EMBEDDING`
   - `USE_MOCK_EASYOCR`
   - `CRAWLER_ENABLED`
2. Run migrations:
   - `railway run -e staging bash -c "cd backend && alembic upgrade head"`
3. Promote reference data:
   - `STAGING_DATABASE_URL="..." python scripts/promote_reference_data.py import --target staging`
4. Verify promoted data:
   - `STAGING_DATABASE_URL="..." python scripts/promote_reference_data.py verify --target staging`
5. Smoke test:
   - `/health`
   - `/admin`
   - `/admin/overview`
   - `/admin/metrics`
   - `/admin/market-data`
   - `/admin/valor-stats`
   - `/` returns `Cache-Control: no-cache`
   - `/admin` returns `Cache-Control: no-cache`
   - `/health` does not inherit the HTML cache header

Example header checks:

```bash
curl -sI https://your-staging-url.up.railway.app/ | grep -i cache-control
curl -sI https://your-staging-url.up.railway.app/admin | grep -i cache-control
curl -sI https://your-staging-url.up.railway.app/health | grep -i cache-control
```

## Keep This Updated

If your branch changes any of the following, update this file and the stage-ready gate in the same branch:

- Admin UI fetches a new backend endpoint
- Existing admin endpoint response shape changes
- A new staging env var becomes required
- A migration becomes required for the feature to work
- Trust-sensitive valuation behavior changes
- A staging smoke test should be added or removed

## Source Runbooks

- `docs/RAILWAY_STAGING_SETUP.md`
- `docs/ENVIRONMENT_AND_DATA_PROMOTION.md`
- `automation/product/GOLDEN_TEST_CASES.md`
