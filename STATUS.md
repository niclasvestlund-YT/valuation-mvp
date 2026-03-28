# STATUS — 2026-03-28

## Last task
HTML cache headers v2 — Cache-Control: no-cache on HTML entrypoints

## What changed
- backend/app/main.py: added `headers={"Cache-Control": "no-cache"}` to FileResponse for / and /admin
- tests/test_admin_ui_data.py: +4 tests (TestHtmlCacheHeaders: index no-cache, admin no-cache, ETag preserved, health unaffected)
- CONTEXT.md: updated

## Verification
- make stage-ready: 75 passed, 22 skipped
- test_admin_ui_data: 26 passed, 19 skipped, 0 failures

## Decision rationale
- no-cache forces revalidation on every request but allows 304 via existing ETag/Last-Modified
- no-store rejected: loses 304 support, wastes bandwidth
- Scoped to HTML only — API endpoints unaffected
