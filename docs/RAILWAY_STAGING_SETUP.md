# Railway Staging Setup

Complete runbook for setting up a staging environment on Railway Hobby plan.

---

## Recommended Topology

```
Railway Project: valuation-mvp
  ├── Environment: staging
  │     ├── Service: web (FastAPI app, auto-deploy from develop branch)
  │     └── Service: Postgres (pgvector-capable, shared reference variable)
  └── Environment: production (later — same pattern)
```

Hobby plan: one project, two environments, one Postgres per environment.
No replicas. No always-on workers. Modest and sufficient.

---

## Prerequisites

1. Railway CLI installed: `npm install -g @railway/cli`
2. Logged in: `railway login`
3. Project linked: `railway link` (select your existing project)
4. Local PostgreSQL running with seed-worthy data
5. `psql` available locally

---

## Step 1: Create Staging Environment

```bash
railway environment create staging
```

This creates a new isolated environment. Each environment has its own services, variables, and deployments.

---

## Step 2: Add PostgreSQL Service

**This must be done in the Railway Dashboard** — the CLI cannot provision database services.

1. Open [Railway Dashboard](https://railway.com/dashboard)
2. Select your project
3. Switch to the **staging** environment (top-left dropdown)
4. Click **+ New** → **Database** → **PostgreSQL**

### pgvector support

Railway's default PostgreSQL template uses a standard Postgres image. pgvector availability depends on the image version Railway ships. It may or may not be pre-installed.

**After the Postgres service is created, verify pgvector:**

```bash
railway run --environment staging psql -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname = 'vector';"
```

**If it works:** You're set. The Alembic migration (`ebfc16bbbee6`) also runs `CREATE EXTENSION IF NOT EXISTS vector` as its first step, so `alembic upgrade head` will handle this automatically.

**If it fails with "could not open extension control file":** The Railway Postgres image does not include pgvector. Options:
1. Use Railway's Docker-based service with an explicit pgvector image: **+ New** → **Docker Image** → `pgvector/pgvector:pg16`
2. Or check Railway's template marketplace for a pgvector-ready Postgres template

In either case, re-run the verification command after switching images.

---

## Step 3: Configure Reference Variables

Railway auto-generates a `DATABASE_URL` for the Postgres service. You need to make it available to your web service using a **reference variable**.

**In Railway Dashboard:**

1. Select your **web service** in the staging environment
2. Go to **Variables** tab
3. Add a new variable:
   - Name: `DATABASE_URL`
   - Value: `${{Postgres.DATABASE_URL}}`
   (This creates a live reference to the Postgres service URL)

Railway injects this as a standard `postgres://` URL. The app's `alembic/env.py` and `config.py` handle the driver prefix conversion automatically.

### Required environment variables

Set these on the **web service** in staging:

| Variable | Value | Notes |
|---|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Reference variable |
| `RAILWAY_ENVIRONMENT` | `staging` | Auto-set by Railway |
| `ADMIN_SECRET_KEY` | (generate a strong random string) | **Required** — admin is locked without it |
| `OPENAI_API_KEY` | (your key) | For vision API |
| `ALLOWED_ORIGINS` | `https://your-staging-url.up.railway.app` | CORS |
| `USE_MOCK_VISION` | `true` | Optional: save API credits during initial testing |
| `USE_MOCK_EMBEDDING` | `true` | No SigLIP model on Railway |
| `USE_MOCK_EASYOCR` | `true` | EasyOCR needs torch, heavy for staging |
| `CRAWLER_ENABLED` | `false` | Don't crawl in staging |

---

## Step 4: Deploy and Run Migrations

### Deploy

Railway auto-deploys from the connected branch. To deploy manually:

```bash
railway up --environment staging
```

### Run Alembic Migrations

**Important:** `alembic.ini` is inside `backend/`, so you must `cd` into it:

```bash
railway run --environment staging bash -c "cd backend && alembic upgrade head"
```

This will:
1. Create all tables (valuations, product, market_comparable, etc.)
2. Create the pgvector extension (`CREATE EXTENSION IF NOT EXISTS vector` in database.py init)
3. Create HNSW indexes for embedding similarity search

### Verify migration

```bash
railway run --environment staging bash -c "cd backend && alembic current"
```

Expected output: the latest migration revision (currently `b5f1e2c3d4a5`).

---

## Step 5: Promote Reference Data

Use the idempotent promotion script (see [ENVIRONMENT_AND_DATA_PROMOTION.md](ENVIRONMENT_AND_DATA_PROMOTION.md) for full details).

### Export from local

```bash
python scripts/promote_reference_data.py export
cat data/snapshots/latest/manifest.json   # review counts
```

### Import into staging

Get the staging DB URL from Railway Dashboard → Postgres service → Connect tab → **Connection URL**.

```bash
STAGING_DATABASE_URL="postgresql://user:pass@host:port/railway" \
  python scripts/promote_reference_data.py import --target staging
```

### Verify import

```bash
STAGING_DATABASE_URL="postgresql://user:pass@host:port/railway" \
  python scripts/promote_reference_data.py verify --target staging
```

---

## Step 6: Verify Staging

### Health check

```bash
curl https://your-staging-url.up.railway.app/health
```

Expected:
```json
{
  "status": "ok",
  "environment": "staging",
  "dependencies": {
    "database": "configured",
    "valor": "no_model"
  }
}
```

Key checks:
- `environment` is `"staging"` (not `"production"` or `"local"`)
- `database` is `"configured"` (not `"unconfigured"`)
- `/docs` is accessible (staging keeps docs visible, production hides them)

### Verify admin auth

```bash
# Should return 403 without key
curl -s -o /dev/null -w "%{http_code}" https://your-staging-url.up.railway.app/admin/overview

# Should return 200 with key
curl -s -o /dev/null -w "%{http_code}" -H "X-Admin-Key: your-staging-key" https://your-staging-url.up.railway.app/admin/overview
```

### Verify valuation pipeline

```bash
curl -X POST https://your-staging-url.up.railway.app/value \
  -H "Content-Type: application/json" \
  -d '{"brand": "Sony", "model": "WH-1000XM4"}'
```

Expected: a ValueEnvelope with `status: "ok"` or `"insufficient_evidence"` (depending on seed data coverage).

---

## Step 7: Create Backup

After successful seeding and verification:

Railway Dashboard → Postgres service → **Backups** tab → **Create Backup**

This is your known-good baseline. Free on Hobby plan (point-in-time recovery).

---

## Rollback Plan

### If migrations fail

```bash
# Check current state
railway run --environment staging bash -c "cd backend && alembic current"

# Downgrade one step
railway run --environment staging bash -c "cd backend && alembic downgrade -1"
```

### If seed data is bad

```bash
# Truncate seed tables (preserves schema)
psql "$STAGING_DATABASE_URL" -c "
  TRUNCATE market_comparable CASCADE;
  TRUNCATE new_price_snapshot CASCADE;
  TRUNCATE product CASCADE;
"
# Re-import
STAGING_DATABASE_URL="..." python scripts/promote_reference_data.py import --target staging
```

### If everything is broken

Railway Dashboard → Postgres service → Backups → Restore from last good backup.

---

## Production Follow-Up (NOT part of this setup)

When staging is stable and tested:

1. Create `production` environment in Railway (same pattern as staging)
2. Add Postgres service to production environment
3. Set `RAILWAY_ENVIRONMENT=production` (auto-set by Railway)
4. Set stricter `ALLOWED_ORIGINS`
5. Consider: separate OpenAI key with higher rate limits
6. Consider: separate Tradera/Serper keys for production quotas
7. Deploy from `main` branch (staging deploys from `develop`)
8. Run migrations: same `cd backend && alembic upgrade head` pattern
9. Seed production with same script or start empty
10. `/docs` and `/redoc` are hidden in production (controlled by `_is_production` flag)

---

## Troubleshooting

### pgvector not available

If `CREATE EXTENSION vector` fails during migration or verification:
1. Railway's default Postgres image may not include pgvector
2. Use a Docker-based service instead: **+ New** → **Docker Image** → `pgvector/pgvector:pg16`
3. Re-set the `DATABASE_URL` reference variable to point to the new service
4. Re-run migrations: `cd backend && alembic upgrade head`

### Alembic "relation already exists"

This means migrations and schema are out of sync. Fix:
```bash
railway run --environment staging bash -c "cd backend && alembic stamp head"
```
Then verify tables manually.

### DATABASE_URL format

Railway injects `postgres://user:pass@host:port/db`. The app handles conversion:
- `config.py`: uses it as-is for asyncpg (adds `+asyncpg` prefix if needed)
- `alembic/env.py`: converts to `+psycopg2` for sync migrations

If you get connection errors, check the URL format in Railway Variables tab.

### Admin returns 403 even with correct key

Verify `ADMIN_SECRET_KEY` is set in the **web service** variables (not the Postgres service).
The key must match the `X-Admin-Key` header exactly (case-sensitive, no trailing whitespace).
