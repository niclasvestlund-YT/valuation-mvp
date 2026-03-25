# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-03-25

### Added
- Structured JSON logging foundation: centralised `get_logger()` factory with `_JsonFormatter`
- Two log sinks: stdout (JSON) and `logs/app.jsonl` (10 MB rotating, 5 files)
- `RequestIdMiddleware`: injects UUID per request, sets `request_id_var` ContextVar, adds `X-Request-ID` header
- Structured log events throughout the pipeline: `pipeline.vision_complete`, `pipeline.valuation_complete`, `pipeline.missing_brand_or_model`, `pipeline.degraded`, `request.value.start/complete`, `db.*` events
- `GET /health` now returns JSON `{"status": "ok", "version": "0.1.0"}`
- `backend/app/core/version.py` as single source of truth for version string

### Fixed
- Image-based valuations always returned `ambiguous_model`; root cause: `MULTIPLE_ALTERNATIVES_CONFIDENCE_CAP` structurally below `AMBIGUOUS_IDENTIFICATION_CONFIDENCE_THRESHOLD`; fix: demoted `multiple_plausible_models` from hard-block to soft warning
- Active-only comparables (no sold listings) now accepted as valid evidence (`MIN_SOLD_COMPARABLES=0`)
- Serper.dev test isolation: tests no longer contaminated by real Serper cache via stub injection
- `build_preliminary_estimate` now accepts `single_source_insufficient` as anchor when no better source exists

### Changed
- Blocket promoted to primary used-market source (no API key required); SerpAPI demoted to zero-result fallback only
- Serper.dev promoted to primary new-price source; SerpAPI Google Shopping demoted to fallback
- `market_service.py` `get_prices()` — identified as potential dead code (not called from main request flow)

### Infrastructure
- Admin dashboard: `GET /admin` serves vanilla JS `admin.html`; admin router with DB overview, valuation metrics, table browser, index health, slow queries
- Data flywheel: PostgreSQL + asyncpg + SQLAlchemy async; `Valuation` + `PriceSnapshot` models; `POST /feedback` endpoint; Alembic initial migration

[Unreleased]: https://github.com/niclasvestlund/valuation-app/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/niclasvestlund/valuation-app/releases/tag/v0.1.0
