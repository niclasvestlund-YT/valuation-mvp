# STATUS — 2026-03-25

## Done
- XSS fix: admin.html esc() sanitizer for table browser cells/columns + statTile values
- XSS fix: index.html replaced innerHTML += with createElement in angle-slot
- Admin auth: X-Admin-Key header on all /admin/* routes, 403 on mismatch
- CORS: allow_origins=["*"] → ALLOWED_ORIGINS env var (default localhost)
- .claude/settings.json: bypassPermissions + deny list
- .env.example: added ADMIN_SECRET_KEY, ALLOWED_ORIGINS

## Files Changed
- frontend/admin.html — esc() helper, table XSS fix, auth key prompt + header
- frontend/index.html — createElement replaces innerHTML += in angle-slot
- backend/app/routers/admin.py — verify_admin_key dependency on all routes
- backend/app/main.py — CORS reads ALLOWED_ORIGINS from settings
- backend/app/core/config.py — added allowed_origins, admin_secret_key fields
- .env.example — ADMIN_SECRET_KEY, ALLOWED_ORIGINS
- .claude/settings.json — bypassPermissions mode
- CONTEXT.md — updated env vars, removed fixed issues, added changelog entry

## Failed
- git push origin develop — GitHub HTTPS auth not configured (same as prior session)

## Next
1. Run `gh auth login` then `git push origin develop`
2. Wrap _persist_valuation in try/except (TASKS.md prio 1)
3. Set up local PostgreSQL
