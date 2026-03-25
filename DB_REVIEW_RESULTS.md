# Database Code Review Results

**Date:** 2026-03-25
**Reviewer scope:** All database-related Python code in backend/
**Files reviewed:** database.py, models.py, crud.py, admin.py, value.py, main.py, config.py, alembic/env.py, alembic.ini, both migrations

---

## Critical — Causes data loss, crashes, or security holes

### 1. `create_all` bypasses Alembic on every startup
**File:** `backend/app/db/database.py:17`
**Was:** `Base.metadata.create_all()` ran on every startup, creating tables directly from ORM models.
**Problem:** Dual-path schema management. If a model adds a column without a migration, `create_all` silently creates it. On a fresh DB with Alembic, the migration doesn't know about it. Results in "column already exists" or "column does not exist" depending on startup order.
**Fix:** Replaced `create_all()` with a `SELECT 1` connectivity check. Tables are now managed exclusively by Alembic.

### 2. SQL injection risk in admin table browser
**File:** `backend/app/routers/admin.py` (browse_table endpoint)
**Was:** `table_name` and `order_by` from URL params were f-string-interpolated into SQL. Whitelist existed but was the only defense.
**Problem:** If the whitelist logic has any bug (race condition, caching issue, etc.), attacker-controlled strings go straight into SQL. Defense in depth was missing.
**Fix:** Added strict regex validation (`^[a-z_][a-z0-9_]{0,62}$`) via `_validate_identifier()` that runs BEFORE any SQL. The whitelist check remains as a second layer. Also switched `limit`/`offset` from f-string interpolation to bound parameters.

### 3. `save_feedback` silently drops feedback when valuation not in DB
**File:** `backend/app/db/crud.py:40-51`
**Was:** `session.get(Valuation, valuation_id)` returned `None` when valuation wasn't found; function exited silently with no log and no return value.
**Problem:** When DB was down during the original valuation (common per CONTEXT.md), the valuation_id doesn't exist. User submits feedback thinking it was saved — it's silently dropped. No log, no trace.
**Fix:** Added `logger.warning("db.save_feedback.not_found", ...)` when valuation missing. Changed return type to `bool` so callers can inform users. Updated the `/feedback` endpoint to return `{"ok": false}` when feedback can't be saved.

### 4. No connection pool health checks
**File:** `backend/app/db/database.py:9`
**Was:** `create_async_engine(...)` with no `pool_pre_ping`.
**Problem:** After a PostgreSQL restart or network blip, the pool holds dead connections. Next query gets a `ConnectionResetError` or similar. User sees a 500 error for the first request after any DB interruption.
**Fix:** Added `pool_pre_ping=True` (validates connections before use) and `pool_recycle=1800` (recycles connections every 30 min to prevent stale TCP state).

### 5. Hardcoded credentials in alembic.ini
**File:** `backend/alembic.ini:89`
**Was:** `sqlalchemy.url = postgresql+psycopg2://postgres:dev@localhost:5432/valuation`
**Problem:** Default username `postgres` and password `dev` in version-controlled config. While `env.py` overrides this from `DATABASE_URL`, if that env var is ever unset, Alembic silently uses the hardcoded URL. In production (Railway), this could connect to the wrong database or leak credential patterns.
**Fix:** Replaced with `postgresql+psycopg2://localhost/valuation` (no credentials). Added a warning in `env.py` when `DATABASE_URL` is not set.

---

## Important — Causes bugs or will cause bugs at scale

### 6. `datetime.utcnow()` deprecated — produces naive datetimes
**Files:** `backend/app/db/models.py:14,54`, `backend/app/api/value.py:395`
**Was:** `default=datetime.utcnow` (Python-side default) and `datetime.utcnow().strftime(...)`.
**Problem:** `datetime.utcnow()` is deprecated since Python 3.12. More importantly, it returns timezone-naive datetimes. PostgreSQL stores them as `timestamp without time zone`, making timezone-aware comparisons unreliable. The admin router uses `datetime.now(timezone.utc)` for query params, creating a naive-vs-aware comparison.
**Fix:** Replaced all instances with `datetime.now(timezone.utc)`. Changed `created_at` columns to `DateTime(timezone=True)`.

### 7. No `server_default` on critical columns
**File:** `backend/app/db/models.py`
**Was:** `created_at` used `default=datetime.utcnow` (Python-only). `is_correction` used `default=False` (Python-only). `source` used `default="user_scan"` (Python-only).
**Problem:** These defaults only apply when inserting via the ORM. Raw SQL inserts (migrations, manual fixes, data imports) get NULL. `created_at=NULL` breaks every time-based query in admin.py.
**Fix:** Added `server_default=func.now()` on `created_at`, `server_default="false"` on `is_correction`, `server_default="user_scan"` on `source`. Note: a new Alembic migration is needed to apply these server defaults to the existing DB schema.

### 8. No engine disposal on shutdown — connection leak
**File:** `backend/app/main.py`
**Was:** `@app.on_event("startup")` called `init_db()`. No shutdown handler.
**Problem:** When the app stops (deploy, restart), the connection pool is abandoned. PostgreSQL keeps the connections alive until `tcp_keepalives_idle` timeout (typically 2 hours). On Railway with frequent deploys, this exhausts `max_connections`.
**Fix:** Replaced deprecated `on_event("startup")` with `lifespan` context manager. Added `dispose_engine()` on shutdown.

### 9. `_persist_valuation` leaks internal fields into API response
**File:** `backend/app/api/value.py:496-505`
**Was:** `result["_condition"]` and `result["_response_time_ms"]` were set directly on the response dict before passing to `background_tasks`.
**Problem:** While FastAPI's `response_model` strips unknown fields, the internal `_`-prefixed keys still exist in the response dict. If `response_model` validation is ever disabled or the dict is logged/forwarded, these internal fields leak.
**Fix:** Created a separate `persist_payload` dict for the background task. The API response dict no longer contains `_condition` or `_response_time_ms`.

### 10. Admin helper functions used fragile positional-to-named param conversion
**File:** `backend/app/routers/admin.py:38-56`
**Was:** `_fetch(sql, *args)` with a `_positional_to_named` helper that mapped positional args to `:p1`, `:p2`.
**Problem:** Fragile coupling — the SQL must use `:p1`, `:p2` markers matching the positional arg order. Easy to mismatch. No IDE support or type checking.
**Fix:** Changed to explicit `dict` params: `_fetch(sql, params={"since": day_ago})`. Callers now use named params matching the SQL markers. Clearer, harder to mismatch.

### 11. CRUD accepts arbitrary dict keys — risk of TypeError
**File:** `backend/app/db/crud.py:12-13`
**Was:** `Valuation(**data)` passed the raw dict directly to the ORM constructor.
**Problem:** If the `data` dict contains a key that isn't a Valuation column (typo, renamed field, extra data), SQLAlchemy raises `TypeError: __init__() got an unexpected keyword argument`. In the background task, this kills the persist silently.
**Fix:** Added field whitelists (`_VALUATION_FIELDS`, `_SNAPSHOT_FIELDS`) computed from `__table__.columns`. The `save_*` functions now filter the dict before passing to the ORM constructor.

---

## Minor — Code quality, future-proofing

### 12. Alembic migration has fabricated revision ID
**File:** `backend/alembic/versions/a2b3c4d5e6f7_add_indexes_condition_response_time.py`
**Observation:** Revision ID `a2b3c4d5e6f7` is clearly hand-crafted (sequential hex characters), not auto-generated by `alembic revision`. While it technically works, it signals the migration may not have been created through the standard Alembic workflow.
**Risk:** If someone runs `alembic revision --autogenerate`, the chain works but operational trust is reduced.
**Recommendation:** Re-generate this migration using `alembic revision --autogenerate -m "add indexes, condition, response_time_ms"` to get a proper random revision ID.

### 13. UUID columns use String instead of native PostgreSQL UUID
**File:** `backend/app/db/models.py:13,53`
**Observation:** `id = Column(String, ...)` with `default=lambda: str(uuid.uuid4())` stores UUIDs as 36-character strings.
**Why it matters:** PostgreSQL's native `UUID` type uses 16 bytes vs 36 bytes for String. Indexes are smaller and faster. Comparison operations are more efficient. JOIN performance improves on large tables.
**Recommendation:** Migrate to `Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)` in a future migration when you have enough data to warrant the storage improvement.

### 14. `snapshot_date` stored as String instead of Date
**File:** `backend/app/db/models.py:63`
**Observation:** Dates are stored as `"2026-03-24"` strings instead of `sa.Date`.
**Why it matters:** Can't use `BETWEEN`, date arithmetic, or `date_trunc()` in SQL without casting. Indexes on string dates don't support range scans as efficiently as `Date` indexes.
**Recommendation:** Add a migration to change the column type to `Date` and convert existing data.

### 15. `value_image` endpoint is synchronous
**File:** `backend/app/api/value.py:405`
**Observation:** `def value_image(...)` is not `async`. FastAPI runs it in a thread pool.
**Why it matters:** The endpoint calls `value_engine.value_item()` which does HTTP calls to external APIs. Running sync HTTP in a thread is functional but ties up a thread pool slot. Under load, the thread pool (default 40 threads) becomes the bottleneck.
**Recommendation:** Consider making the value engine async. Low priority for MVP traffic levels.

### 16. Missing Alembic migration for server_default changes
**Observation:** The `server_default` additions to `created_at`, `is_correction`, and `source` exist in the model but have no corresponding migration.
**Impact:** Existing databases won't get these defaults until a migration is run.
**Recommendation:** Create a new Alembic migration: `alembic revision --autogenerate -m "add server defaults"` and verify it picks up the `server_default` changes.

---

## Summary

| Severity | Count | Fixed in code |
|----------|-------|---------------|
| Critical | 5 | 5 |
| Important | 6 | 6 |
| Minor | 5 | 0 (recommendations only) |
| **Total** | **16** | **11** |

### Files modified
- `backend/app/db/database.py` — removed `create_all`, added `pool_pre_ping`, `pool_recycle`, `dispose_engine()`
- `backend/app/db/models.py` — fixed `datetime.utcnow`, added `server_default`, timezone-aware `DateTime`
- `backend/app/db/crud.py` — fixed silent feedback drop, added field whitelisting, proper session transactions
- `backend/app/routers/admin.py` — hardened SQL injection defense, explicit named params, removed fragile positional conversion
- `backend/app/api/value.py` — fixed `datetime.utcnow`, stopped leaking internal fields, improved feedback response
- `backend/app/main.py` — replaced deprecated `on_event` with `lifespan`, added engine disposal on shutdown
- `backend/alembic.ini` — removed hardcoded credentials
- `backend/alembic/env.py` — added warning when `DATABASE_URL` not set

### Still needed (not fixed here)
1. New Alembic migration for `server_default` changes and `DateTime(timezone=True)`
2. Re-generate fabricated migration revision ID
3. Migrate UUID String columns to native PostgreSQL UUID type
4. Migrate `snapshot_date` from String to Date
5. Make value engine async

DONE
