# Overnight Engineering Session — 2026-03-25

## What was shipped

Eight production-readiness tasks completed end-to-end. All 66 tests pass. Four git commits. Tagged v0.1.0.

---

## Task 1 — Structured logging foundation

**Problem:** The codebase used ad-hoc `print` and stdlib `logging` with no consistent format. There was no way to correlate log lines from the same request in production.

**What was built:**
- `backend/app/utils/logger.py`: centralised `get_logger()` factory with `_JsonFormatter` that emits structured JSON on every line
- Two sinks: stdout (JSON) and `logs/app.jsonl` (10 MB rotating, 5 files)
- `request_id_var: ContextVar[str | None]` for async-safe propagation across the full pipeline
- `backend/app/middleware/request_id.py`: `RequestIdMiddleware` generates a UUID per request, sets the context var, and adds `X-Request-ID` to every response
- Structured log events wired throughout: `pipeline.vision_complete`, `pipeline.valuation_complete`, `pipeline.missing_brand_or_model`, `pipeline.degraded`, `request.value.start/complete`, `db.*`
- 10 logger tests covering: required fields, extra context, request_id propagation, all log levels, ISO 8601 timestamps, exc_info capture

**Tests before:** 49 passing. **Tests after:** 49 passing.

---

## Task 2 — Changelog system and semantic versioning

**What was built:**
- `CHANGELOG.md` covering the full history through v0.1.0 in Keep a Changelog format
- `backend/app/core/version.py`: single source of truth for `VERSION = "0.1.0"`
- `GET /health` upgraded from plain text "API running" to JSON `{"status": "ok", "version": "0.1.0"}`
- Git tag `v0.1.0` created

---

## Task 3 — Wire `condition` field end-to-end

**Problem:** `condition` was accepted by `get_depreciation_range()` and `PricingService.calculate_valuation()` but always passed as `None`. The API had no `condition` field at all.

**What was wired:**
- `ValueRequest.condition: str | None` added to the API schema
- Flows: `POST /value` → `value_item(condition=)` → `calculate_valuation(condition=)` + `build_preliminary_estimate(condition=)`
- `get_depreciation_range()` now receives the actual user-supplied condition, shifting the depreciation bounds:
  - `excellent`: +0.05 (higher residual value)
  - `good`: baseline
  - `fair`: -0.07
  - `poor`: -0.16
- Condition is logged in `pipeline.vision_complete` and `request.value.start` events

---

## Task 4 — Dead code audit

**What was removed:**
- `MarketService.get_prices()` — confirmed unused across the entire codebase (only defined, never called)

**What was kept:**
- `prisjakt_client.py` — documents the 403/Cloudflare investigation; useful reference

---

## Task 5 — Comprehensive test suite expansion

**17 new tests added (49 → 66):**

| File | New tests |
|---|---|
| `test_depreciation_rules.py` | 8 — known category, unknown fallback, None category, all 4 conditions, range validity invariants |
| `test_pricing_service.py` | 4 — poor vs excellent condition shifts estimate, exact model substring accepted, wrong brand scores zero, sold/active both accepted |
| `test_value_engine.py` | 5 — condition forwarded to pricing service, enrich_envelope for ok/ambiguous/reason_details/dedup |

---

## Task 6 — Production hardening

**Input validation added to `ValueRequest`:**
- `condition`: must be one of `excellent|good|fair|poor`; case-normalised to lowercase
- `images`: must not exceed 8 items
- `brand`, `model`, `category`, `filename`: must not exceed 128 characters

**Request size limit:**
- `RequestSizeLimitMiddleware`: returns HTTP 413 if `Content-Length` exceeds 20 MB

**Health endpoint enriched:**
- `/health` now includes `"dependencies"` with per-service config state (`configured|unconfigured|missing_key|mock`)

---

## Task 7 — Railway deployment setup

**Files added:**
- `railway.toml`: nixpacks builder, `uvicorn --host 0.0.0.0 --port $PORT` start command, `/health` probe with 30s timeout, restart on failure (max 3)
- `Procfile`: fallback start command for Heroku-compatible runtimes
- `DEPLOY.md`: full environment variable table, Railway setup steps, migration command (`railway run alembic upgrade head`), local dev commands

---

## State of the codebase at tag v0.2.0

| Metric | Value |
|---|---|
| Tests passing | **66 / 66** |
| Test files | 7 |
| Git commits (this session) | 8 |
| Git tags | v0.1.0, v0.2.0 |
| Known open issues | Prisjakt blocked (HTTP 403, documented stub) |
| DB persistence | Fire-and-forget via BackgroundTasks — silently fails without Postgres |

---

## What's still missing for a public launch

1. **Database**: Railway auto-sets `DATABASE_URL` when a Postgres service is attached, but no Postgres is running locally or in CI. Valuations save silently fail until this is connected.
2. **Rate limiting**: No per-IP throttling on `POST /value`. The OpenAI call is expensive and unbounded.
3. **Auth**: The admin panel (`/admin/*`) is public. Fine for MVP, but should be behind basic auth before sharing the URL.
4. **Frontend condition selector**: The `condition` field is now wired in the API but the frontend (`frontend/index.html`) has no UI to let users select it.
5. **CI**: No GitHub Actions workflow exists. Tests run locally only.
