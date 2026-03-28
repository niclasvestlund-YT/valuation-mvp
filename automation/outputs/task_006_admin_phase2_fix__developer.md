# Developer Output — Task 006: Admin Phase 2 Security Hardening

## Scope
XSS prevention, loader state standardization, exception leakage removal, and endpoint hardening — the remaining high-risk items from the Task 004 audit.

## Changes Made

### 1. XSS: esc() helper applied to all API data in innerHTML
- Added `function esc(str)` at the top of the script block, before all other JS.
- Escapes &, <, >, ", ' — the five HTML-dangerous characters.
- Applied `esc()` to every user-controlled interpolation in template literals across all render functions:
  - renderList(): product names
  - openDetail(): brand, category, condition, model_version, valuation_id, JSON dump
  - loadMarketData(): crawl titles, source names, product brand/model/category
  - loadValuationsData(): recent brand/model, feedback original_guess/corrected_to
  - loadOcrStats(): brand+model names
  - loadAgentStats(): source names, product_keys, error_messages
  - loadValorStats(): model_version, data_quality_warnings, source_type
  - Dev Diary: commit messages, fun_facts, social card text, day dates
  - showAgentEmpty/showValorEmpty/showMetricsError/showValuationsError: message params
  - API usage: source labels, quota_unit_label
- NOT applied to: numbers (formatKr, toFixed, toLocaleString), hardcoded strings, SVG icons, getStatusPill() output, CSS variables.

### 2. renderSectionState() for consistent loader states
- Added a shared `renderSectionState(containerId, state, message)` function.
- Supports 5 states: loading (skeleton), ok, empty, error, unauthorized.
- Uses `esc()` on the message parameter.
- Available for all section containers.

### 3. Exception leakage removed from admin.py
- 11 occurrences of `str(exc)` in HTTP responses replaced:
  - 6x `raise HTTPException(detail=str(exc))` → `detail="Internt serverfel"` + `logger.error()`
  - 5x `JSONResponse(content={"error":"DB-fel","detail":str(exc)})` → `content={"error":"Internt serverfel"}`
- Real error details now go to logs only. Client gets a generic Swedish message.

### 4. Table browser hardened via ALLOWED_TABLES
- Added static `ALLOWED_TABLES` set with 11 known application tables.
- Validation happens before any SQL construction.
- Unknown tables (e.g., `pg_shadow`) get HTTP 400 with the allowlist.
- SQL injection attempts (e.g., `valuations;DROP TABLE`) fail regex validation.
- Old dynamic information_schema whitelist removed.

### 5. Stray loadValorStats() pre-auth call removed
- Found and removed a bare `loadValorStats()` call that fired before auth.

## Files Changed
- `frontend/admin.html` — esc() helper, renderSectionState(), esc() applied everywhere, stray init call removed
- `backend/app/routers/admin.py` — exception leakage removed, ALLOWED_TABLES added
- `tests/test_admin_ui_data.py` — 10 new tests (esc coverage, renderSectionState, exception safety, table browser)
- `CONTEXT.md` — updated

## Tests Run
- `pytest tests/test_admin_ui_data.py -v` → 17 passed, 18 skipped
- `pytest tests/ -q` (excluding pre-existing embedding failures) → 427 passed, 23 skipped

## Residual Risks
- Admin HTML shell is still publicly served without server-side auth
- Admin key is still a shared secret, not a session token
- Some Chart.js label data passes through without esc() (Chart.js handles its own rendering safely)
