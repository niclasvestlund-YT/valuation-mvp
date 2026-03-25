# STATUS.md — valuation-mvp

**Generated:** 2026-03-25
**Based on:** TASKS.md, CONTEXT.md, DB_GIT_REVIEW.md, CLAUDE.md

> Note: Five DB fixes from DB_GIT_REVIEW.md are already done per Recent Changes
> (confidence_score→confidence, _persist_valuation try/except, indexes, admin.py pool, condition+response_time_ms).
> TASKS.md has not been updated to reflect these. Items below are truly remaining.

---

## Critical — Breaks something now

- [ ] **Set up local PostgreSQL** — DB save silently fails; every write returns None; zero data persists (TASKS Prio 1; CONTEXT Known Issues)
- [ ] **Complete GitHub auth and push** — remote added but auth pending; code only exists locally (TASKS Prio 1)
- [ ] **Fix dual-path table creation** — `database.py:17` `create_all` bypasses Alembic on every startup; will cause "column already exists" or "column does not exist" errors when schema evolves (CONTEXT Known Issues; DB_GIT_REVIEW Risk #4)
- [ ] **Fix SQL injection risk in admin table browser** — `admin.py` uses f-string SQL for table name; whitelist mitigates but is fragile (CONTEXT Known Issues)
- [ ] **Fix `save_feedback` silent failure** — if valuation_id is missing from DB (common when DB was down), feedback is silently dropped with no log entry (DB_GIT_REVIEW)

---

## Important — Needed for the data platform vision

- [ ] **Replace Prisjakt stub with working price history source** — Prisjakt blocks server-side (HTTP 403); no price history is wired (TASKS Prio 2; CONTEXT Known Issues)
- [ ] **Add `.env.example`** with all env vars (no values) for onboarding (TASKS Prio 2)
- [ ] **Integration tests against real DB** — verify the full request flow end-to-end (TASKS Prio 2)
- [ ] **Verify Railway deployment end-to-end** (TASKS Prio 2)
- [ ] **Set up CI/CD pipeline** — no GitHub Actions; every push is untested (DB_GIT_REVIEW Git Review)
- [ ] **Add backup strategy** — Railway has point-in-time recovery but no automated export; project deletion = total data loss (DB_GIT_REVIEW)
- [ ] **Normalize product identity** — add a `products` table so "WH-1000XM4" / "WH1000XM4" / "Sony WH-1000XM4" resolve to one entity; needed for trends and analytics (DB_GIT_REVIEW)
- [ ] **Store market listings** — add `market_listings` table; raw listings are discarded after each request, blocking trend analysis (DB_GIT_REVIEW)
- [ ] **Multi-tenancy support** — add `api_keys`/`tenants` table for B2B billing, rate limiting, data isolation (DB_GIT_REVIEW)
- [ ] **Add missing fields** — `currency` and `request_image_count` on valuations; `condition` and `currency` on price_snapshots (DB_GIT_REVIEW)
- [ ] **Clean up `alembic.ini` hardcoded URL** — default credentials in config file; should rely solely on env var (DB_GIT_REVIEW)
- [ ] **Enable branch protection on GitHub** — documented in CONTRIBUTING.md but not enforced (DB_GIT_REVIEW)

---

## Nice to have — Can wait

- [ ] **Feedback loop** — show historical valuations per product (TASKS Prio 3)
- [ ] **Cron worker for automatic price updates** via PriceSnapshot (TASKS Prio 3)
- [ ] **Rate limiting on POST /value** (TASKS Prio 3)
- [ ] **Image validation** — check filetype and size before vision call (TASKS Prio 3)
- [ ] **Admin dashboard authentication** (TASKS Prio 3)
- [ ] **Add PR template** — `.github/pull_request_template.md` (DB_GIT_REVIEW)
- [ ] **Expand .gitignore** — missing `logs/`, `*.egg-info/`, `.pytest_cache/`, `dist/`, `.mypy_cache/`, `*.db`, `.env.*` (DB_GIT_REVIEW)
- [ ] **Switch to `develop` branch** for daily work; currently on `main` (DB_GIT_REVIEW)

---

**Summary:** 5 critical, 12 important, 8 nice-to-have. The top priority is getting PostgreSQL running locally so data actually persists, followed by completing the GitHub push so the code is backed up.

DONE
