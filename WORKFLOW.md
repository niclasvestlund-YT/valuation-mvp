# Development Workflow Rulebook

## The Golden Rule
**Keep `develop` mergeable into `staging` at all times. `main` stays downstream of a tested `staging`.**

---

## Your Daily Workflow

```
Write/fix code → make stage-ready → Push to develop → Merge to staging → Verify on Railway staging → Merge to main
```

---

## Rule 1 — Always run the stage-ready gate before pushing
```bash
make stage-ready
```

This focused gate checks:
- admin UI/frontend-backend contract tests
- golden valuation cases
- deploy-critical config behavior

If it fails locally, fix that first.

---

## Rule 2 — Push to `develop` only
```bash
git add <files>
git commit -m "fix: what you fixed"
git push origin develop
```
`develop` is your working branch, but it should stay close enough to merge into `staging` without surprises.

---

## Rule 3 — Merge `develop` to `staging` before thinking about `main`
```bash
make stage
```

This is the handoff point for real environment testing. A staging merge is not complete until you also:
- run Alembic migrations in staging
- promote reference data into staging
- smoke test `/health`, `/admin`, and the key admin endpoints

---

## Rule 4 — Only merge to `main` from a healthy `staging`
```bash
make deploy
```
Do this only after:
- ✅ `make stage-ready` passed
- ✅ staging deploy is healthy
- ✅ migrations and reference-data promotion were done if needed
- ✅ the specific changed flow was tested on staging

---

## Rule 5 — One change at a time
Don't fix 5 things and push everything at once. Small focused commits make it easy to find what broke something.

---

## Rule 6 — Commit messages tell a story
```
feat: add DJI brand detection        ← new feature
fix: brand returns null for Action 5 ← bug fix
refactor: simplify confidence logic  ← code cleanup
docs: update README                  ← docs only
```

---

## Rule 7 — Never commit secrets
`.env` stays local. It's already in `.gitignore`.
API keys go in Railway's Variables dashboard, not in code.

---

## Quick Reference Card

| Situation | Action |
|---|---|
| Making a change | Work on `develop` branch |
| Before pushing | Run `make stage-ready` |
| Something broke locally | Fix it, don't push |
| Ready for staging | `make stage` |
| Ready to go live | Merge `staging` → `main` |
| Urgent production fix | Fix on `develop`, run `make stage-ready`, merge to `staging`, verify, then promote to `main` |
| Unsure if it works | **Don't push to main yet** |

---

## 30-second checklist before merging to staging
- [ ] Did `make stage-ready` pass?
- [ ] Did I test the specific thing I changed locally?
- [ ] If I changed schema/data contracts, did I update migrations or staging notes?
- [ ] Is the `.env` file NOT in my commit?

If all four are yes → safe to merge.

---

## Keep It Stage Ready
When a change affects any of these, update the stage-ready flow in the same branch:
- admin endpoints or admin response shapes
- required staging environment variables
- Alembic migrations
- golden trust cases
- staging smoke-test expectations

See `docs/STAGE_READY.md` for the living checklist.
