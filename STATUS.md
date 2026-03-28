# STATUS — 2026-03-28

## Last task
Admin v16 dark mode

## What changed
- frontend/admin.html: v15->v16, dark mode CSS tokens + @media prefers-color-scheme, html/body transitions, sidebar/card/kpi/hb/sf-row/login-overlay transitions, dm-toggle widget (HTML+CSS+JS), icon colors softened to #4a4845, third stack column renamed to "AI-verktyg"
- tests/test_admin_html.py: localStorage test updated to allow dark mode (dm key only)
- CONTEXT.md: file map + recent changes updated

## Verification
- prefers-color-scheme: dark = 3 matches
- DM_DARK = 2, dmApply = 6, vc-slide = 18
- HTML parses OK, all 6 tabs present
- health-banner class confirmed on ov-banner div

## Next up
- Run full pytest to confirm no regressions
- Commit changes
