# STATUS — 2026-03-29

## Last task
Admin UI v17 — Crawler redesign + Översikt redesign + DnD + Svep

## What changed
- frontend/admin.html: new CSS (source cards, listing feed, coverage bars, milestones, DnD, swipe-reveal, hidden pills), replaced tab-ov HTML (hero KPI trio, projektkostnad, milstolpar, drag-hints, hidden-bar), replaced tab-cr HTML (DnD sections, source cards layout), replaced loadOv() (3-column hero, cost breakdown, milestones), replaced loadCr() (source cards, listing feed, coverage bars, schedule badges), added DnD + swipe + hide/show JS
- tests/test_admin_html.py: updated localStorage test (allowlist for DnD/hint/hidden keys), replaced health banner test with ov-hero-kpis test
- CONTEXT.md: updated

## Verification
- 6 JS functions verified (initDnD, initSwipe, ovHide, secAction, dismissHint, showToast)
- 52 HTML structure matches (dnd-section, swipe-content, etc.)
- 51 passed, 24 skipped, 0 failures
