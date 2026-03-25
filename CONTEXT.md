# CONTEXT.md
> Paste this into any new AI chat about this project for instant context.
> Auto-maintained by Claude Code via CLAUDE.md rules.
> Last updated: 2026-03-24

## What This Is
Local MVP for estimating the second-hand value of consumer tech products from photos. Identifies the product via OpenAI Vision, searches Swedish used markets (Tradera, Blocket), and returns a conservative value range. Prefers honest refusal over a misleading number.

## Stack
- Backend: FastAPI, Python 3.11, uvicorn
- Frontend: Single static HTML/CSS/JS file, served by FastAPI at GET /
- Deploy: Railway (railway.toml + Procfile); nixpacks builder; healthcheck /health; auto-deploys on push
- Key deps: fastapi, uvicorn, pydantic, requests, Pillow, pillow-heif, python-dotenv, blocket-api

## Request Flow
image upload → api/value.py → value_engine.py (orchestrates) → vision_service.py → market_data_service.py + new_price_service.py (parallel) → comparable_scoring.py → pricing_service.py → api/value.py (enrich_envelope) → response

## File Map
DEEP_INVESTIGATION_REPORT.md — full AI/valuation system investigation: AI usage map, pipeline analysis, QA/trust findings, prioritized opportunities
backend/app/main.py — FastAPI app, CORS, serves frontend/index.html + frontend/admin.html, /health endpoint, DB init on startup
backend/app/routers/admin.py — read-only admin API: DB overview, valuation metrics, table browser, index health, slow queries
backend/app/api/value.py — POST /value + POST /feedback endpoints; saves every valuation to DB via BackgroundTasks
backend/app/db/__init__.py — empty
backend/app/db/database.py — async SQLAlchemy engine, session factory, init_db()
backend/app/db/models.py — Valuation + PriceSnapshot ORM models
backend/app/db/crud.py — save_valuation, save_price_snapshot, save_feedback
backend/alembic/ — Alembic migrations directory
backend/alembic.ini — Alembic config (sync psycopg2 URL for migrations)
backend/app/core/config.py — all env var definitions and defaults
backend/app/core/version.py — single source of truth for VERSION string
backend/app/core/value_engine.py — main orchestration: vision → market → score → price → envelope
backend/app/services/vision_service.py — OpenAI Vision API, product identification, confidence rules
backend/app/services/market_service.py — market data wrapper, provider selection
backend/app/services/market_data_service.py — fetches and merges comparables from all sources
backend/app/services/new_price_service.py — new price lookup: Serper.dev primary, SerpAPI fallback, SEK filtering
backend/app/services/pricing_service.py — weighted median valuation, confidence calculation
backend/app/services/comparable_scoring.py — relevance scoring, hard rejection rules
backend/app/services/image_preprocess.py — image conversion, resizing, HEIC support
backend/app/services/outlier_filter.py — MAD/IQR outlier removal
backend/app/services/depreciation_rules.py — depreciation rate ranges by category
backend/app/integrations/tradera_client.py — Tradera SOAP API client, Swedish marketplace
backend/app/integrations/blocket_client.py — Blocket used-market search via blocket-api package; no API key needed; 1h in-memory cache
backend/app/integrations/serper_new_price_client.py — Serper.dev Google Shopping new price (primary); requires SERPER_DEV_API_KEY; 1h cache
backend/app/integrations/prisjakt_client.py — stub; Prisjakt blocks server-side requests (HTTP 403); documents investigation
backend/app/integrations/serpapi_used_market_client.py — SerpAPI used market supplement (optional fallback only)
backend/app/integrations/new_price_search_client.py — SerpAPI Google Shopping new price (fallback only)
backend/app/schemas/product_identification.py — vision output schema
backend/app/schemas/market_comparable.py — market comparable schema
backend/app/utils/cache.py — simple in-memory TTL cache (1h default); used by blocket_client + serper_new_price_client
backend/app/utils/error_reporting.py — structured JSON error logging to logs/errors.jsonl
backend/app/utils/logger.py — centralised JSON logger factory with request_id context var; two sinks (stdout + logs/app.jsonl)
backend/app/utils/normalization.py — text normalization utilities
backend/app/middleware/__init__.py — empty
backend/app/middleware/request_id.py — RequestIdMiddleware: injects UUID per request, sets request_id_var, adds X-Request-ID header
tests/test_logger.py — 10 tests: JSON fields, request_id propagation, log levels, exc_info
frontend/index.html — single-page UI in Swedish, image upload, result display; Admin nav button in header
frontend/admin.html — vanilla JS admin dashboard; tabs: DB overview, valuations metrics, table browser, index health
tests/test_vision_service.py — vision service tests
tests/test_market_discovery.py — market discovery tests
tests/test_new_price_service.py — new price service tests
tests/test_pricing_service.py — pricing service tests
tests/test_value_engine.py — end-to-end value engine tests
tests/test_depreciation_rules.py — condition adjustments and category depreciation range tests
automation/workflow.py — QA workflow automation
automation/close.py — session close helper
automation/product/GOLDEN_TEST_CASES.md — canonical test cases
automation/product/NORTH_STAR.md — product vision
automation/history/DECISIONS.md — architecture decision log
automation/history/IMPROVEMENTS.md — improvement history
TASKS.md — prioriterad uppgiftslista (3 nivåer)
KVALL_RAPPORT.md — kvällsrapport 2026-03-25 med alla fynd
.claude/settings.json — Claude Code permissions (block push main/staging, rm -rf)
CONTRIBUTING.md — branch workflow and commit conventions
ARCHITECTURE_REVIEW.md — full technical review: code quality, architecture, DB, security, risks, next steps
DB_GIT_REVIEW.md — database schema + git workflow review with prioritized fixes

## Endpoints
POST /value — JSON body: `{image?, images?, filename?, brand?, model?}`; returns ValueEnvelope JSON (includes valuation_id)
POST /feedback — JSON body: `{valuation_id, feedback, corrected_product?}`; saves user feedback
GET / — serves frontend/index.html
GET /admin — serves frontend/admin.html
GET /admin/overview — DB size, version, uptime, connections, table list
GET /admin/metrics — valuation counts, confidence, status/brand/category breakdowns
GET /admin/table/{name} — paginated rows for any public table (25/page)
GET /admin/index-health — seq scan ratios to spot missing indexes
GET /admin/slow-queries — currently running queries >500ms
GET /health — returns JSON {"status": "ok", "version": "...", "dependencies": {...}} with per-service config state

## Env Vars
- OPENAI_API_KEY — OpenAI Vision API (platform.openai.com)
- OPENAI_VISION_MODEL — model ID, default gpt-4.1-mini
- OPENAI_TIMEOUT_SECONDS — default 30
- OPENAI_MAX_RETRIES — default 3
- USE_MOCK_VISION — set true to skip real vision calls in tests
- TRADERA_APP_ID — Tradera marketplace API (developer.tradera.com)
- TRADERA_APP_KEY — Tradera marketplace API key
- TRADERA_TIMEOUT_SECONDS — default 20
- SERPER_DEV_API_KEY — Serper.dev (serper.dev); primary new-price source; replaces SerpAPI for this use
- SERPAPI_API_KEY — SerpAPI (serpapi.com); optional fallback for new price + used market supplement
- SERPAPI_TIMEOUT_SECONDS — default 20
- SERPAPI_ENGINE — default google_shopping
- SERPAPI_LOCATION — default Sweden
- SERPAPI_GL — default se
- SERPAPI_HL — default sv
- DATABASE_URL — PostgreSQL connection string; default postgresql+asyncpg://postgres:dev@localhost:5432/valuation; Railway sets this automatically
- ADMIN_SECRET_KEY — required for /admin/* API access; admin.html prompts for it on load
- ALLOWED_ORIGINS — comma-separated CORS origins; default localhost only

## Response States
- ok — enough evidence, shows used-value range
- depreciation_estimate — 0 comparables found but new price known; uses category depreciation midpoint; confidence=0.35
- ambiguous_model — confidence < 0.55 or hard ambiguity signal, returns requested angles
- insufficient_evidence — product identified but no comparables and no new price, or average relevance too low
- degraded — upstream API failure (vision, Tradera); SerpAPI failure is silent (not a degraded trigger)
- error — request failed (bad upload, decode failure, unexpected exception)

## Known Issues
- Prisjakt is blocked (HTTP 403 / Cloudflare): prisjakt_client.py is a documented stub; no price history source is wired
- DB save is fire-and-forget via FastAPI BackgroundTasks — valuation_id is pre-generated UUID included in every response
- Local PostgreSQL not installed — DB save silently fails (all writes return None)
- SQL injection risk: admin.py table browser uses f-string SQL (mitigated by whitelist, but fragile)
- database.py:17 create_all bypasses Alembic — dual-path table creation will cause conflicts

## Recent Changes
2026-03-25 — feat: rate limiting (slowapi 10/min), hide /docs in prod, temperature=0 on vision, vision cache SHA-256, Tradera rate-limit logging, .env.example updated
2026-03-25 — docs: deep investigation report; AI usage map, pipeline analysis, 10 prioritized opportunities, evaluation plan, QA/trust findings
2026-03-25 — fix: vision prompt rewrite for better product identification; chain-of-thought procedure (brand→line→generation→variant→cross-check); specificity examples; product knowledge hints (DJI Osmo Pocket 1/2/3, Sony WH-1000XM4/5); adjusted confidence bands (0.80–0.89 for design-based generation ID); camera-specific requested angles; 66 tests pass
2026-03-25 — feat: improved pricing model; FIX 1 depreciation fallback (0 comps + new price → depreciation_estimate, conf=0.35); FIX 2 graduated confidence penalty replaces hard MIN_RELEVANT_COMPARABLES=3 gate; FIX 3 percentile range (p15/p85 for ≥4 comps, ±15% otherwise); FIX 4 CANONICAL comment + legacy deprecation; FIX 5 calibration table; FIX 6 response_time_ms on all return paths; 66 tests pass
2026-03-25 — fix: Osmo Action scoring — DJI brand inference, relaxed core-token match (score 0.65), qualifier penalty (score_cap 0.52), candidate model substring guard; Tradera fallback skips broad "DJI Osmo" query; new price rejects bundle/combo variants; 66 tests pass
2026-03-25 — fix: vision brand inference for DJI Action cameras; prompt now maps "Action 5 Pro" → DJI; expanded text evidence keywords (branding, reads, says, visible on, printed on, stamped, embossed); AMBIGUOUS_IDENTIFICATION_CONFIDENCE_THRESHOLD lowered 0.90→0.80
2026-03-25 — fix: 5 DB issues; confidence_score→confidence, _persist_valuation try/except, indexes on status/brand/category, admin.py→SQLAlchemy pool, condition+response_time_ms fields
2026-03-25 — docs: DB + Git review; found confidence_score bug, missing indexes, pool bypass, dual-path create_all
2026-03-25 — security: XSS fix, admin auth via X-Admin-Key, CORS restricted to ALLOWED_ORIGINS, bypassPermissions
2026-03-25 — docs: full architecture review
2026-03-25 — infra: GitHub workflow; remote added, develop/staging/main branches, CONTRIBUTING.md
2026-03-25 — chore: kvällsgranskning; säkerhetsskanning OK, DB-save-risk dokumenterad, TASKS.md + KVALL_RAPPORT.md + .claude/settings.json skapade
2026-03-25 — docs: OVERNIGHT_SUMMARY.md written; v0.2.0 tagged; 66 tests passing, 8 commits this session
2026-03-25 — feat: Railway deployment; railway.toml (nixpacks, healthcheck /health), Procfile, DEPLOY.md with env vars and migration steps
2026-03-25 — feat: production hardening; input validation (condition enum, images count ≤8, text fields ≤128 chars), 20MB request body limit, /health returns dependency states
2026-03-25 — test: 17 new tests; depreciation rules, condition propagation, enrich_envelope states, scoring edge cases; total 66 tests passing
2026-03-25 — refactor: remove dead code; market_service.get_prices() unused method removed
2026-03-25 — feat: wire condition field end-to-end; ValueRequest.condition → value_item → calculate_valuation + build_preliminary_estimate → get_depreciation_range; affects pricing range and preliminary estimate
2026-03-25 — feat: changelog system; CHANGELOG.md, version.py (VERSION=0.1.0), /health returns JSON with version, git tag v0.1.0
2026-03-25 — feat: structured logging foundation; centralised get_logger() with JSON formatter and request_id propagation; RequestIdMiddleware; two sinks (stdout + logs/app.jsonl); logged vision/valuation/db events; 10 logger tests pass
2026-03-25 — fix: image-based valuations always returned ambiguous_model; root cause: MULTIPLE_ALTERNATIVES_CONFIDENCE_CAP (0.74) is structurally always below AMBIGUOUS_IDENTIFICATION_CONFIDENCE_THRESHOLD (0.90), so candidate_models always triggered hard-block; fix: demoted multiple_plausible_models from hard_block_reasons to soft warning; only missing_brand_or_model now hard-blocks
2026-03-25 — admin dashboard: GET /admin serves vanilla JS admin.html; admin router with DB overview, valuation metrics, table browser, index health, slow queries; Admin nav button added to main header
2026-03-24 — frontend fixes: double product name dedup (WH-1000XM + WH-1000XM4 → WH-1000XM4); comparable status field (status=completed → Såld); quick comparables list now visible in main view (no need to expand "Se detaljer"); ended_at time-ago shown per comparable
2026-03-24 — pipeline fixes: AVIF image support; color word stripping before Blocket query; MIN_SOLD_COMPARABLES=0; confidence floor 0.55; needs_more_images demoted to warning; Blocket/Tradera comparables no longer classified as "related" in frontend; category passed through manual override
2026-03-24 — frontend rewrite: premium Klarna-style design system; warm off-white tokens; Inter font; Lucide icons throughout; upload, scanning, and result screens redesigned; quick view with text-hero estimate, combined info line, retention bar; advanced view with dot plot, comparable listings, reasoning, feedback, next steps; ambiguous/insufficient/error states redesigned; no blue, no emoji; all JS logic preserved unchanged
2026-03-24 — zero-SerpAPI pipeline: blocket-api package integrated as primary used-market source; Serper.dev as primary new-price source; SerpAPI demoted to optional fallback for both; prisjakt_client.py stub documents 403 block; in-memory TTL cache added

## Next Up
[Empty — add manually]

---
How to use: copy this file and attach it when starting a new AI conversation about this project.
