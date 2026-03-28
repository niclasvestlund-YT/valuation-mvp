# CONTEXT.md
> Paste this into any new AI chat about this project for instant context.
> Auto-maintained by Claude Code via CLAUDE.md rules.
> Last updated: 2026-03-28

## What This Is
Local MVP for estimating the second-hand value of consumer tech products from photos. Identifies the product via OpenAI Vision, searches Swedish used markets (Tradera, Blocket), and returns a conservative value range. Prefers honest refusal over a misleading number.

## Stack
- Backend: FastAPI, Python 3.11, uvicorn
- Frontend: Single static HTML/CSS/JS file, served by FastAPI at GET /
- Deploy: Railway (railway.toml + Procfile); nixpacks builder; healthcheck /health; auto-deploys on push
- Key deps: fastapi, uvicorn, pydantic, requests, Pillow, pillow-heif, python-dotenv, blocket-api, pgvector

## Request Flow
image upload → api/value.py → value_engine.py (orchestrates) → vision_service.py → market_data_service.py + new_price_service.py (parallel) → comparable_scoring.py → pricing_service.py → api/value.py (enrich_envelope) → response

## File Map
DEEP_INVESTIGATION_REPORT.md — full AI/valuation system investigation: AI usage map, pipeline analysis, QA/trust findings, prioritized opportunities
docs/RAILWAY_STAGING_SETUP.md — complete Railway staging runbook: topology, env setup, migrations, seed data, verification
docs/ENVIRONMENT_AND_DATA_PROMOTION.md — operating model: code vs schema vs data promotion, git workflow, idempotent reference data workflow
scripts/promote_reference_data.py — idempotent reference data promotion: export → import → verify; UPSERT-based, transactional, auditable with manifest
scripts/export_stage_seed.sql — (legacy) one-time CSV seed export; superseded by promote_reference_data.py
scripts/import_stage_seed.sh — (legacy) one-time CSV import; superseded by promote_reference_data.py
scripts/verify_stage_seed.sql — (legacy) post-import SQL verification; superseded by promote_reference_data.py verify
backend/app/main.py — FastAPI app, CORS, serves frontend/index.html + frontend/admin.html, /health endpoint, DB init on startup
backend/app/routers/admin.py — read-only admin API: DB overview, valuation metrics, table browser, index health, slow queries, agent-stats, valor-stats
backend/app/routers/ingest.py — POST /api/ingest + /agent/job/start + /agent/job/complete + /valor/train + /valor/rollback
backend/app/api/value.py — POST /value + POST /feedback endpoints; saves every valuation to DB via BackgroundTasks
backend/app/db/__init__.py — empty
backend/app/db/database.py — async SQLAlchemy engine, session factory, init_db()
backend/app/db/models.py — Valuation, PriceSnapshot, Product, MarketComparable, NewPriceSnapshot, AgentJob, PriceObservation, TrainingSample, ValorModel, ValorEstimate, PriceStatistic, ProductEmbedding ORM models
backend/app/db/crud.py — save_valuation, save_price_snapshot, save_feedback, upsert_product, upsert_comparables, get_cached_comparables, upsert_new_price, get_latest_new_price
backend/app/services/data_validator.py — ingestion validator for market comparables (hard rejects + soft warnings)
backend/app/services/crawler_service.py — background crawler for pre-populating comparable cache from seed products
backend/app/data/seed_products.json — 80 seed products across 3 priority tiers for crawler
scripts/crawl_prices.py — CLI to run crawler: --priority, --max, --with-new-prices, --dry-run
scripts/train_valor.py — VALOR ML training: ETL → quality scoring → XGBoost → model registry; --dry-run, --force, --min-samples, --product
backend/app/services/valor_service.py — VALOR XGBoost wrapper: predict(), reload_model(), mock mode; never crashes
backend/app/services/embedding_service.py — SigLIP/CLIP embedding service for product image similarity (768-dim, pgvector)
backend/app/services/ocr_service.py — OCR orchestrator: Google Vision → EasyOCR → empty fallback
backend/app/services/ocr_verification.py — cross-verify OCR text/logos against Vision identification
backend/app/integrations/google_vision_client.py — Google Cloud Vision API client (TEXT + LOGO + LABEL detection, cached)
backend/app/integrations/easyocr_client.py — EasyOCR local fallback (no API key needed)
backend/app/schemas/ocr_result.py — OCR result dataclass with detected text, logos, labels
backend/alembic/ — Alembic migrations directory
backend/alembic.ini — Alembic config (sync psycopg2 URL for migrations)
backend/app/core/config.py — all env var definitions and defaults
backend/app/core/version.py — single source of truth for VERSION string
backend/app/core/thresholds.py — all 40+ pipeline thresholds in one file (confidence caps, scoring weights, gates)
backend/app/data/product_knowledge.json — 7 product families + 8 category angle sets for vision prompt
backend/app/core/value_engine.py — main orchestration: vision → market → score → price → envelope
backend/app/services/vision_service.py — OpenAI Vision API, product identification, confidence rules
backend/app/services/market_service.py — market data wrapper, provider selection
backend/app/services/market_data_service.py — fetches and merges comparables from all sources
backend/app/services/new_price_service.py — new price lookup: Webhallen → Inet → SerpAPI fallback; SEK filtering
backend/app/services/pricing_service.py — weighted median valuation, confidence calculation
backend/app/services/comparable_scoring.py — relevance scoring, hard rejection rules
backend/app/services/image_preprocess.py — image conversion, resizing, HEIC support
backend/app/services/outlier_filter.py — MAD/IQR outlier removal
backend/app/services/depreciation_rules.py — depreciation rate ranges by category
backend/app/integrations/tradera_client.py — Tradera SOAP API client, Swedish marketplace
backend/app/integrations/facebook_marketplace_client.py — FB Marketplace via DuckDuckGo index (no API key, no FB account)
backend/app/integrations/blocket_client.py — Blocket used-market search via blocket-api package; no API key needed; 1h in-memory cache
backend/app/integrations/webhallen_client.py — Webhallen autocomplete API new price (primary); free, Swedish, JSON; 1h cache, 5s rate limit
backend/app/integrations/inet_client.py — Inet.se autocomplete API new price (secondary); free, Swedish, JSON; 1h cache, 8s rate limit
backend/app/integrations/serper_new_price_client.py — Serper.dev Google Shopping new price (disabled — quota exhausted); preserved for future use
backend/app/integrations/prisjakt_client.py — stub; Prisjakt blocks server-side requests (HTTP 403); documents investigation
backend/app/integrations/serpapi_used_market_client.py — SerpAPI used market supplement (optional fallback only)
backend/app/integrations/new_price_search_client.py — SerpAPI Google Shopping new price (last-resort fallback only)
backend/app/schemas/product_identification.py — vision output schema
backend/app/schemas/assistant.py — QuickReply + AssistantContext for Prisassistent conversation layer
backend/app/schemas/market_comparable.py — market comparable schema
backend/app/utils/cache.py — simple in-memory TTL cache (1h default); used by blocket_client + serper_new_price_client
backend/app/utils/error_reporting.py — structured JSON error logging to logs/errors.jsonl
backend/app/utils/logger.py — centralised JSON logger factory with request_id context var; two sinks (stdout + logs/app.jsonl)
backend/app/utils/normalization.py — text normalization utilities
backend/app/utils/admin_errors.py — structured admin errors with copy-paste-for-Claude-Code context
backend/app/middleware/__init__.py — empty
backend/app/middleware/request_id.py — RequestIdMiddleware: injects UUID per request, sets request_id_var, adds X-Request-ID header
tests/test_logger.py — 10 tests: JSON fields, request_id propagation, log levels, exc_info
frontend/index.html — single-page UI in Swedish, image upload, result display; Admin nav button in header
frontend/admin.html — admin UI v16: 6 tabs, dark mode toggle (CSS + JS), Scandinavian design, responsive, skeleton loaders, structured errors
tests/test_vision_service.py — vision service tests
tests/test_market_discovery.py — market discovery tests
tests/test_new_price_service.py — new price service tests
tests/test_new_price_clients.py — 18 tests for Webhallen, Inet, Serper clients + service source chain
tests/test_pricing_service.py — pricing service tests
tests/test_value_engine.py — end-to-end value engine tests
tests/test_depreciation_rules.py — condition adjustments and category depreciation range tests
tests/test_golden_cases.py — 7 canonical product pipeline tests (Sony XM4/5, iPhone 13, DJI Osmo, MacBook Air)
tests/test_data_validator.py — 15 tests for ingestion validator (rejects, valid, warnings)
tests/test_normalization.py — 10 tests for normalize_product_key
tests/test_crawler_service.py — 10 tests for seed products and crawler
tests/test_embedding_service.py — 11 tests for embedding service (mock mode, hash, base64, dimensions)
tests/test_pipeline_integration.py — 13 integration tests (normalization→validation→embedding flow)
tests/test_data_quality.py — 12 data quality invariant tests (thresholds, seed products, validator)
tests/test_ocr_service.py — 11 tests for OCR clients and service (mock mode, fallback chain)
tests/test_ocr_verification.py — 14 tests for OCR cross-verification (brand/model match, contradictions)
tests/test_valor_service.py — 7 tests for VALOR ML service (mock mode, sanity checks, no-crash)
tests/test_outlier_filter.py — 21 tests for IQR/MAD outlier removal (trust-critical statistical filtering)
tests/test_config.py — 17 tests for config URL normalization, env reading, Railway fail-closed behavior
tests/test_ingest_endpoint.py — 8 tests for /api/ingest validation (price limits, accessory flags, truncation)
tests/test_training_pipeline.py — 10 tests for VALOR training ETL (quality scores, encoding, inclusion criteria)
tests/test_promote_reference_data.py — 21 tests for promotion safety (URL guards, localhost rejection, manifest, dry-run, env var mapping)
tests/test_assistant_context.py — 33 tests for Prisassistent (confirmation normalization, phase derivation, quick replies, guardrails)
tests/test_valor_pipeline.py — 29 tests for VALOR pipeline (quality scores, ETL null guard, feature consistency, dry-run, response fields)
tests/test_admin_ui_data.py — 26 tests for admin endpoint shapes, auth behavior, metrics normalization, no-local-history
tests/test_admin_html.py — 26 structure tests + 2 integration tests for admin.html (tabs, responsive, security, XSS)
automation/workflow.py — QA workflow automation
automation/close.py — session close helper
automation/product/GOLDEN_TEST_CASES.md — canonical test cases
automation/product/NORTH_STAR.md — product vision
automation/history/DECISIONS.md — architecture decision log
automation/history/IMPROVEMENTS.md — improvement history
TASKS.md — prioriterad uppgiftslista (3 nivåer)
KVALL_RAPPORT.md — kvällsrapport 2026-03-25 med alla fynd
.claude/settings.json — Claude Code permissions (block push main/staging, rm -rf)
scripts/collect_vibe_stats.py — collects git + test stats to vibe_stats.json
scripts/pre-push — pre-push git hook (runs pytest before push)
scripts/install_hook.sh — installs pre-push hook to .git/hooks
CONTRIBUTING.md — branch workflow and commit conventions
ARCHITECTURE_REVIEW.md — full technical review: code quality, architecture, DB, security, risks, next steps
DB_GIT_REVIEW.md — database schema + git workflow review with prioritized fixes

## Endpoints
POST /value — JSON body: `{image?, images?, filename?, brand?, model?}`; returns ValueEnvelope JSON (includes valuation_id, valor_estimate_sek, valor_available)
POST /feedback — JSON body: `{valuation_id, feedback, corrected_product?}`; saves user feedback
GET / — serves frontend/index.html
GET /admin — serves frontend/admin.html
GET /admin/overview — DB size, version, uptime, connections, table list
GET /admin/metrics — valuation counts, confidence, status/brand/category breakdowns + recent_valuations, valor_stats, source_stats
GET /admin/assistant-stats — Prisassistent conversation stats (phases, corrections, confirmed rate, 7-day window)
GET /admin/table/{name} — paginated rows for any public table (25/page)
GET /admin/index-health — seq scan ratios to spot missing indexes
GET /admin/slow-queries — currently running queries >500ms
GET /admin/agent-stats — agent observations, jobs, coverage, stale products, suspicious rate
POST /api/ingest — accepts list of price observations from agents (X-Admin-Key auth); validates, flags suspicious, returns accept/reject counts
POST /api/agent/job/start — create agent job record, returns job_id (X-Admin-Key auth)
POST /api/agent/job/complete — finalize agent job with results (X-Admin-Key auth)
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
- DATABASE_URL — PostgreSQL connection string; auto-normalized from postgres:// to postgresql+asyncpg://; defaults to localhost locally, empty on Railway (fail-closed)
- ADMIN_SECRET_KEY — required for /admin/* API access; MUST be set on Railway (admin locked without it); optional locally
- RAILWAY_ENVIRONMENT — auto-set by Railway; "staging" or "production"; controls env detection, docs visibility, admin auth behavior
- ALLOWED_ORIGINS — comma-separated CORS origins; default localhost only
- VALOR_MODEL_DIR — optional; path to model directory; default "models" (relative); set to "/app/models" on Railway with persistent volume
- VALOR_MIN_SAMPLES_FOR_PRODUCTION — minimum training samples before VALOR estimates shown to users; default 50; set to 1 to force-enable

## Response States
- ok — enough evidence, shows used-value range
- depreciation_estimate — 0 comparables found but new price known; uses category depreciation midpoint; confidence=0.35
- ambiguous_model — confidence < 0.55 or hard ambiguity signal, returns requested angles
- insufficient_evidence — product identified but no comparables and no new price, or average relevance too low
- degraded — upstream API failure (vision, Tradera); SerpAPI failure is silent (not a degraded trigger)
- error — request failed (bad upload, decode failure, unexpected exception)

## Known Issues
- Serper.dev quota exhausted — disabled in serper_new_price_client.py; get_new_price_sek() returns None; class preserved for quota refill
- Prisjakt is blocked (HTTP 403 / Cloudflare): prisjakt_client.py is a documented stub; no price history source is wired
- DB save is fire-and-forget via FastAPI BackgroundTasks — valuation_id is pre-generated UUID included in every response
- Admin table browser uses f-string SQL after ALLOWED_TABLES allowlist + regex validation (hardened in phase 2)
- VALOR model persistence: Railway volume mounted at /app/models (deployed 2026-03-28); model survives restarts
- Admin panel: HTML shell still publicly served; XSS now mitigated via esc() helper; exception leakage removed

## Recent Changes
2026-03-28 — feat: admin v16 dark mode — CSS custom properties for light/dark, prefers-color-scheme media query, JS toggle with localStorage persistence (dm key only), smooth transitions on all surfaces, updated icon colors for contrast
2026-03-28 — feat: admin.html full rewrite — 6 tabs (Oversikt/Crawler/Vibe/Ekonomi/Valor/Halsokoll), Scandinavian design system, XSS-safe esc(), memory-only auth, skeleton loaders, Chart.js, responsive mobile tab bar, assistant-stats fallback
2026-03-28 — review: test + deploy audit — outlier_filter tests (21), config tests (17), Makefile fixed (develop→staging→main, test gate), pytest in requirements.txt, golden cases verified
2026-03-28 — feat: replace Serper.dev with Webhallen+Inet for new prices — webhallen_client.py (JSON API), inet_client.py (JSON API), serper disabled, priority chain Webhallen→Inet→SerpAPI, 18 new tests, 461 pass
2026-03-28 — test: TDZ regression guard for VALOR admin UI — 2 tests in test_admin_ui_data.py assert declaration order + explanatory copy
2026-03-28 — fix: admin VALOR UI temporal-dead-zone bug — moved `const t` before first use, updated no-model copy to explain market_comparable vs training_sample distinction
2026-03-28 — deploy: Railway pre-prod live — valor-models volume, first VALOR training (3 samples, MAE 1189 kr, MAPE 28.7%), model persists across restarts, threshold set to 50
2026-03-28 — security: admin phase 2 — esc() XSS helper on all API data in innerHTML, renderSectionState() for consistent loader states, str(exc) removed from all HTTP error responses, table browser hardened via ALLOWED_TABLES allowlist, 10 new tests
2026-03-28 — fix: admin phase 1 security — admin key memory-only (no localStorage), auth gate before fetches, 401/403 re-auth, demo fallback removed, status_breakdown metrics bug fixed, local valuation_history removed from admin, 7 new tests
2026-03-28 — feat: VALOR production activation — Railway volume config, VALOR_MODEL_DIR env var, production threshold gate (50 samples), admin UI threshold display + training state, 405 tests pass
2026-03-28 — feat: VALOR production readiness — ETL null brand/model guard, ETL summary logging, feature consistency tests, admin VALOR health cell + detail panel estimate + training CTA, 400 tests pass
2026-03-27 — fix: promotion safety v2 — strict env vars, localhost rejection, 21 promotion tests, weekly runbook
2026-03-27 — feat: idempotent reference data promotion — promote_reference_data.py, UPSERT-based, ENVIRONMENT_AND_DATA_PROMOTION.md

## Next Up
- Backfill price observations from existing comparables to bootstrap VALOR training data toward 50-sample threshold
- Replace f-string SQL in admin table browser with parameterized queries
- Wire up scheduled agent jobs to continuously feed price observations into ingest pipeline
