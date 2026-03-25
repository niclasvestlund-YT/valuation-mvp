# Development Workflow Rulebook

## The Golden Rule
**Never push to `main` without testing first. Main = live = real users.**

---

## Your Daily Workflow

```
Write/fix code → Test locally → Push to develop → Verify on Railway dev → Merge to main
```

---

## Rule 1 — Always test locally before pushing anywhere
```bash
source .venv/bin/activate
uvicorn backend.app.main:app --reload
```
Open http://localhost:8000 and test manually.
**If it breaks locally, fix it before pushing.**

---

## Rule 2 — Push to `develop` only
```bash
git add <files>
git commit -m "fix: what you fixed"
git push origin develop
```
`develop` is your sandbox. Breaking it is fine. No real users are affected.

---

## Rule 3 — Only merge to `main` when you're confident
```bash
git checkout main
git merge develop
git push origin main
```
Do this only after:
- ✅ It works locally
- ✅ You've tested the specific thing that changed
- ✅ No obvious errors in the terminal

---

## Rule 4 — One change at a time
Don't fix 5 things and push everything at once. Small focused commits make it easy to find what broke something.

---

## Rule 5 — Commit messages tell a story
```
feat: add DJI brand detection        ← new feature
fix: brand returns null for Action 5 ← bug fix
refactor: simplify confidence logic  ← code cleanup
docs: update README                  ← docs only
```

---

## Rule 6 — Never commit secrets
`.env` stays local. It's already in `.gitignore`.
API keys go in Railway's Variables dashboard, not in code.

---

## Quick Reference Card

| Situation | Action |
|---|---|
| Making a change | Work on `develop` branch |
| Before pushing | Test on http://localhost:8000 |
| Something broke locally | Fix it, don't push |
| Ready to go live | `git merge develop` → push `main` |
| Urgent production fix | Fix on `develop`, test, fast-merge to `main` |
| Unsure if it works | **Don't push to main yet** |

---

## 30-second checklist before merging to main
- [ ] Does it work on localhost?
- [ ] Did I test the specific thing I changed?
- [ ] Any obvious errors in the terminal?
- [ ] Is the `.env` file NOT in my commit?

If all four are yes → safe to merge.

---

## I'll tell you when it's time for main
Claude Code will say **"Ready for main"** when:
- The fix is verified working locally
- No regressions on other features
- The change is small enough to be confident about
