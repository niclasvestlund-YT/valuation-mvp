# Database & Git Review — valuation-mvp

**Date:** 2026-03-25
**Scope:** Database schema, Alembic migrations, CRUD layer, git workflow

---

## Database Review

### Schema future-proofing

The current schema has **two tables** (Valuation, PriceSnapshot). This is adequate for an MVP but will not support a multi-tenant data platform without significant additions.

**What works now:**
- Valuation captures the full lifecycle: identification, pricing, confidence, feedback
- PriceSnapshot enables basic time-series tracking per product
- JSONB `sources_json` provides flexible metadata storage
- Self-referential `original_valuation_id` FK supports correction chains

**What doesn't scale:**

The product identity is a free-text string (`product_identifier = "WH-1000XM4"`). Two different users scanning the same product may get `"WH-1000XM4"`, `"WH1000XM4"`, or `"Sony WH-1000XM4"` — there is no canonical product table to normalize against. Every analytics query (trends, popular products, price history) requires fuzzy string matching.

### Missing tables

| Table | Purpose | Why it matters |
|-------|---------|----------------|
| `products` | Canonical product catalog with normalized brand/model/category | Deduplicates product identity; enables clean aggregation, trend analysis, and product pages |
| `market_listings` | Raw listing data (title, price, URL, source, scraped_at) | Currently discarded after each request; storing them enables trend analysis and avoids re-fetching |
| `api_keys` / `tenants` | Multi-tenancy for B2B | No concept of "who asked" — critical for billing, rate limiting, and data isolation |

### Missing fields on existing tables

| Table | Field | Why |
|-------|-------|-----|
| `valuations` | `condition` | Request accepts condition (excellent/good/fair/poor) but it's never persisted — can't analyze how condition affects price |
| `valuations` | `response_time_ms` | Critical for monitoring; no way to detect slow requests without this |
| `valuations` | `request_image_count` | Analytics: does more images = higher confidence? |
| `valuations` | `currency` | Always assumed SEK but stored values have no currency context |
| `price_snapshots` | `condition` | Snapshots don't capture which condition the price was for |
| `price_snapshots` | `currency` | Same as above — no currency stored |

### Missing indexes

| Table | Column(s) | Why needed |
|-------|-----------|------------|
| `valuations` | `status` | `admin.py:163` does `GROUP BY status` on every metrics page load — sequential scan |
| `valuations` | `brand` | `admin.py:184` does `GROUP BY brand ORDER BY count DESC` — sequential scan |
| `valuations` | `category` | `admin.py:173` does `GROUP BY category` — sequential scan |
| `price_snapshots` | `(product_identifier, snapshot_date)` | The primary query pattern for trend data; separate indexes on each column don't help with compound lookups |

At 10,000 valuations these missing indexes will make admin dashboard queries noticeably slow. At 100,000 they'll time out.

### Critical bug: admin.py queries wrong column name

**`admin.py:160`** queries `confidence_score` but the actual column is `confidence` (`models.py:29`):
```sql
SELECT ROUND(AVG(confidence_score)::numeric, 3) FROM valuations WHERE confidence_score IS NOT NULL
```

This will throw a PostgreSQL error on every `/admin/metrics` call. Same bug on **line 212**. The admin dashboard metrics tab is broken.

### Alembic setup

**Mostly correct**, with issues:

- `env.py` properly swaps `asyncpg://` → `psycopg2://` for sync migrations
- `env.py` imports models so autogenerate works
- Only 1 migration file (initial schema) — clean

**Issues:**
- `alembic.ini:89` has a hardcoded `sqlalchemy.url` with default credentials — this should use an env var only. The `env.py` overrides it, but if `DATABASE_URL` is unset, it falls back to this hardcoded value. Works for local dev but leaks the pattern.
- `database.py:17` uses `Base.metadata.create_all` on startup — this **bypasses Alembic entirely**. If you add a column via Alembic migration but the app starts first, `create_all` creates the table with ALL columns from the model, making the migration a no-op. But if you run the migration first, then change the model without a migration, `create_all` silently adds the column. This dual-path table creation will cause confusion.
- No migration for the schema changes made since initial (e.g., `market_data_json` column exists in models.py but may or may not be in the migration — it is in the initial, so OK for now, but future changes will need discipline).

### Data loss scenarios

1. **`_persist_valuation` crash** (`value.py:339-392`) — no try/except around dict-parsing. A `TypeError` or `KeyError` kills the BackgroundTask silently. The valuation result is returned to the user but never saved.

2. **DB connection failure on startup** (`database.py:19-20`) — `init_db` catches the exception and logs a warning, then the app runs without a database. Every `save_valuation` call returns `None`. Zero data persists, zero alerts.

3. **No backup strategy** — Railway PostgreSQL has point-in-time recovery, but no automated backup export exists. If the Railway project is deleted, all data is gone.

4. **`save_feedback` silent failure** (`crud.py:44-45`) — if the `valuation_id` doesn't exist in DB (common when DB was down during valuation), `session.get` returns `None` and feedback is silently dropped. No log entry for "valuation not found."

### What breaks first at 10,000 valuations

1. **Admin metrics page** — `GROUP BY status/brand/category` without indexes = sequential scans on every page load (auto-refreshes every 30 seconds)
2. **Admin table browser** — `SELECT *` with `LIMIT/OFFSET` pagination degrades linearly; at 10K rows, page 400 scans 10K rows to skip 9,975
3. **Connection pool exhaustion** — `admin.py` opens a **new connection per query** (`asyncpg.connect()`) instead of using the SQLAlchemy pool. 5 concurrent admin refreshes = 20+ connections.
4. **The `confidence_score` bug** crashes the metrics endpoint, so you won't even know the dashboard is broken until you look at it.

---

## Git Review

### Branch structure

```
* main      — 8a7453a (production)
  staging   — 8a7453a (same as main)
  develop   — 2c8ec36 (4 commits ahead)
```

**Structure is correct.** Three-branch flow (develop → staging → main) is standard. Currently on `main` locally; should be on `develop` for daily work.

Remote is configured and pushed:
```
origin → github.com/niclasvestlund-YT/valuation-mvp (main, staging, develop)
```

### Commit quality

Commits are **good** — conventional prefixes used consistently, messages are descriptive:
```
security: XSS fix, admin auth, CORS, bypass permissions
docs: full architecture review
infra: professional git workflow established
feat: Railway deployment setup
feat: production hardening — input validation, size limits
test: comprehensive test suite expansion (49 → 66 tests)
fix: image valuations always returned ambiguous_model
```

One issue: the `checkpoint 2026-03-25` commit (`fa628ac`) is a catch-all with 9 files. In the future, avoid checkpoint commits — stage and commit related changes together.

### Missing for professional workflow

1. **No CI/CD pipeline** — no GitHub Actions for tests, linting, or deployment. Every push is untested.
2. **No PR template** — `CONTRIBUTING.md` exists but no `.github/pull_request_template.md`
3. **No branch protection enforced** — documented in CONTRIBUTING.md but not set on GitHub
4. **Currently on `main`** — should be on `develop` for daily work

### .gitignore gaps

Current `.gitignore` is minimal (6 lines). Missing entries:

| Pattern | Why |
|---------|-----|
| `*.pyc` | Python bytecode (though `__pycache__/` covers most) |
| `logs/` | `app.jsonl` and `errors.jsonl` are generated at runtime |
| `*.egg-info/` | Python package metadata |
| `.pytest_cache/` | pytest cache |
| `dist/` | Build artifacts |
| `.mypy_cache/` | Type checker cache |
| `*.db` | SQLite files if used for local testing |
| `node_modules/` | In case frontend gets a build step |
| `.env.*` with `!.env.example` | Protect all env variants |

---

## Top 5 Risks

### 1. Admin metrics crash — wrong column name
**`admin.py:160` and `admin.py:212`** query `confidence_score` but the column is `confidence` (`models.py:29`). Every call to `/admin/metrics` will throw a PostgreSQL `UndefinedColumn` error. The admin dashboard metrics tab is completely broken.

### 2. Silent data loss in `_persist_valuation`
**`value.py:339-392`** — no try/except around 50 lines of dict-parsing. A single unexpected `None`, missing key, or type mismatch kills the BackgroundTask. The user gets their valuation result, but it's never persisted. No error log, no alert. The docstring says "Never raises" but it can and will.

### 3. Admin router opens raw connections outside the pool
**`admin.py:26-27`** — `asyncpg.connect(DATABASE_URL)` creates a new TCP connection per query, bypassing SQLAlchemy's connection pool (`database.py:9` sets `pool_size=5`). The admin dashboard fires 3 queries on load, then auto-refreshes every 30 seconds. Multiple admin users = connection exhaustion.

### 4. `database.py:17` `create_all` bypasses Alembic
**`database.py:14-20`** — `Base.metadata.create_all` runs on every startup. This means Alembic migrations are redundant for creating tables — but NOT for altering them. If you add a column in the model without a migration, `create_all` creates it on the next restart. But on a fresh database with Alembic, the migration doesn't know about it. This dual-path will cause "column already exists" or "column does not exist" errors depending on startup order.

### 5. No indexes on query-heavy columns
**`models.py:19-20,24`** — `brand`, `category`, and `status` have no indexes. The admin router does `GROUP BY` on all three (`admin.py:163,173,184`). At 10K+ rows, every admin page load triggers 3 full table scans, plus 2 more for the `confidence_score` aggregation (which crashes anyway — see Risk #1).

---

## Recommended Fixes in Priority Order

### 1. Fix `confidence_score` → `confidence` in admin.py
- **File:** `backend/app/routers/admin.py` lines 160, 212
- **Change:** Replace `confidence_score` with `confidence` in both SQL queries
- **Why:** The admin metrics tab is completely broken — every call throws UndefinedColumn. This is a live bug, not a hypothetical risk.

### 2. Wrap `_persist_valuation` in try/except
- **File:** `backend/app/api/value.py:339-392`
- **Change:** Wrap the entire function body in `try: ... except Exception as exc: logger.error("db.persist_valuation.error", extra={"valuation_id": valuation_id, "error": str(exc)})`
- **Why:** Silent data loss. Every valuation where the response shape is slightly unexpected loses its DB record with zero trace.

### 3. Add missing indexes via Alembic migration
- **File:** New migration in `backend/alembic/versions/`
- **Change:** Add indexes on `valuations.status`, `valuations.brand`, `valuations.category`, and a composite index on `price_snapshots(product_identifier, snapshot_date)`
- **Why:** Admin dashboard will time out at scale. These are the most-queried columns with no indexes.

### 4. Switch admin.py to use SQLAlchemy session pool
- **File:** `backend/app/routers/admin.py:26-44`
- **Change:** Replace `asyncpg.connect(DATABASE_URL)` with the existing `async_session` from `database.py`. Rewrite queries using `session.execute(text(...))`.
- **Why:** Each admin query opens a raw TCP connection and closes it. Connection churn + no pooling = exhaustion under load.

### 5. Add `condition` and `response_time_ms` to Valuation model
- **Files:** `backend/app/db/models.py`, `backend/app/api/value.py`, new Alembic migration
- **Change:** Add `condition = Column(String, nullable=True)` and `response_time_ms = Column(Integer, nullable=True)` to Valuation. Persist condition from the request and measure elapsed time in the endpoint.
- **Why:** Condition affects pricing but isn't stored — you can't analyze its impact. Response time is the most basic observability metric and you have zero visibility.
