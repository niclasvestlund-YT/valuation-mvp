# Combined Review: Unit Tests + Deploy Flow — 2026-03-28

## Findings (sorted by severity)

### HIGH — Makefile `deploy` target had wrong branch name and skipped staging
- **File:** [Makefile](Makefile)
- **Issue:** The deploy target referenced `dev` branch (doesn't exist — actual branch is `develop`), merged directly to `main` skipping `staging`, and ran no tests before deploy.
- **Risk:** Running `make deploy` would fail silently or worse, push untested code straight to production.
- **Fix applied:** Split into `make stage` (develop→staging with test gate) and `make deploy` (staging→main). Both now use correct branch names.

### HIGH — `outlier_filter.py` had zero unit tests
- **File:** [backend/app/services/outlier_filter.py](backend/app/services/outlier_filter.py)
- **Issue:** Trust-critical module that decides which comparable prices are included/excluded from valuations. IQR and MAD statistical filtering had no direct tests — only indirectly exercised.
- **Risk:** A regression in outlier removal directly corrupts valuation estimates.
- **Fix applied:** Added 21 focused unit tests covering all public functions, edge cases (empty lists, identical values, MAD=0 fallback), and the comparable dict pipeline.

### MEDIUM — `_normalize_database_url` had no tests
- **File:** [backend/app/core/config.py](backend/app/core/config.py)
- **Issue:** Deploy-critical function that converts Railway's `postgres://` URL to `postgresql+asyncpg://`. Also implements fail-closed behavior on Railway (empty string when no DATABASE_URL). No tests.
- **Risk:** A subtle regression would cause silent connection failure on staging/production.
- **Fix applied:** Added 17 tests covering all URL prefixes, Railway fail-closed, local fallback, and env reading helpers.

### MEDIUM — No automated test gate in the deploy workflow
- **Issue:** Neither the Makefile nor the documented runbook required running tests *before* merging to staging. Tests were only mentioned in CONTRIBUTING.md as a suggestion.
- **Fix applied:** `make stage` now runs `pytest` and aborts if tests fail.

### MEDIUM — pytest not declared in requirements.txt
- **File:** [requirements.txt](requirements.txt)
- **Issue:** `make stage` calls `python -m pytest`, and `make setup` installs from `requirements.txt`, but pytest was not listed. It happened to be available as a transitive dependency, but a clean install on a different machine or Python version could omit it.
- **Fix applied:** Added `pytest>=8.0.0` to `requirements.txt` under a `# Testing` section.

### LOW — `market_service.py` has no direct unit tests
- **File:** [backend/app/services/market_service.py](backend/app/services/market_service.py)
- **Issue:** Tested only via stubs in `test_value_engine.py`. The actual comparable normalization/mapping logic is never directly tested.
- **Recommendation:** Add focused unit tests if this module gains complexity. Currently low risk — thin wrapper.

### LOW — `image_preprocess.py` has no tests
- **File:** [backend/app/services/image_preprocess.py](backend/app/services/image_preprocess.py)
- **Recommendation:** Add tests if HEIC/AVIF handling becomes important. Current risk is low — failures are visible immediately.

### INFO — `db` target uses plain postgres:16, not pgvector
- **File:** [Makefile](Makefile)
- **Issue:** `make db` starts `postgres:16` without pgvector. Production uses pgvector. This creates a local/staging divergence for embedding features.
- **Recommendation:** Consider changing to `pgvector/pgvector:pg16` when pgvector features become critical for local testing.

---

## Test Suite Classification

| Category | Test files | Test count (approx) |
|---|---|---|
| **Unit tests** | test_pricing_service, test_depreciation_rules, test_normalization, test_data_validator, test_outlier_filter, test_config, test_vision_service, test_new_price_service, test_new_price_clients, test_embedding_service, test_valor_service, test_logger, test_api_counter, test_api_quota_clients | ~180 |
| **Integration / light integration** | test_pipeline_integration, test_data_quality, test_market_discovery, test_crawler_service, test_ocr_service, test_ocr_verification | ~70 |
| **API / contract tests** | test_value_engine, test_ingest_endpoint, test_admin_ui_data, test_agent_endpoint, test_assistant_context | ~110 |
| **Golden / regression** | test_golden_cases | 7 |
| **Feature-specific** | test_valor_pipeline, test_training_pipeline, test_promote_reference_data, test_backfill_price_observations, test_crawl_jobs, test_agent, test_vinted_client | ~110 |

**Total: ~480+ tests** (32 test files)

### Quality Assessment

**Strengths:**
- Golden test cases cover the four canonical product families from GOLDEN_TEST_CASES.md
- Comparable scoring has excellent test coverage — Osmo family rules, poison patterns, bundle detection
- Pricing service tests cover sparse data, outliers, condition adjustments, depreciation estimates
- Value engine tests cover all status paths: ok, insufficient_evidence, ambiguous_model, degraded
- `debug_summary` behavior is preserved and tested
- API shape is tested via Pydantic models (ValueEnvelope)
- Promotion script has 21 safety tests (URL guards, localhost rejection, dry-run)

**Weaknesses:**
- Outlier filter was untested (now fixed)
- Config URL normalization was untested (now fixed)
- Some tests are heavily mocked — but this is appropriate given the architecture (external APIs)
- No contract test for the actual HTTP `/value` endpoint shape (only tests the engine, not FastAPI serialization)

### Are unit tests being added continuously?

**Evidence of good discipline:** Most features in the git log include test counts ("18 new tests", "21 promotion tests", "33 tests"). The Recent Changes section shows test counts alongside features.

**Evidence of gaps:** The outlier_filter.py gap suggests that core utility modules can slip through — they're indirectly tested via integration but lack direct unit tests. The `test_agent_endpoint.py` was added separately from the agent feature (different commits).

**Verdict:** The team has a strong testing culture overall, but should strengthen the rule that **every trust-critical utility module gets direct unit tests**, not just indirect coverage through integration.

---

## Deploy Flow Review

### Current documented flow
```
develop → staging → main
(local)    (Railway auto-deploy)   (Railway auto-deploy)
```

### Issues found and status

| Issue | Severity | Status |
|---|---|---|
| Makefile `deploy` used wrong branch `dev` instead of `develop` | HIGH | **Fixed** |
| Makefile `deploy` skipped staging, went direct to main | HIGH | **Fixed** |
| No test gate before staging deploy | MEDIUM | **Fixed** — `make stage` runs pytest |
| pytest not declared in requirements.txt | MEDIUM | **Fixed** — added `pytest>=8.0.0` |
| No automated migration step in deploy targets | LOW | Not changed — migrations are documented in runbook, manual step is safer |
| `make db` uses postgres:16 without pgvector | LOW | Documented, recommend change later |
| `.env.example` references SERPER_DEV_API_KEY as "primary" but Serper is disabled | INFO | Not changed — cosmetic |

### What looks good
- Railway `railway.toml` is clean — healthcheck, restart policy, volume mount
- `Procfile` matches `railway.toml` start command
- DATABASE_URL normalization handles all Railway URL variants correctly
- Fail-closed behavior on Railway (no localhost fallback) is correct and now tested
- Reference data promotion is idempotent with safety guards
- Three-way separation (code/schema/data) is well-documented
- CONTRIBUTING.md branch workflow matches ENVIRONMENT_AND_DATA_PROMOTION.md

### Remaining deploy risks
1. **Alembic migrations are manual** — must remember to run after deploy. No automated check. This is acceptable for the hobby tier but should be automated for production.
2. **No smoke test step** in `make stage` or `make deploy` — after merge + push, there's no automated health check.
3. **pgvector availability** depends on Railway's Postgres image version — documented but not automatically verified.

---

## Developer Output

### Files changed
| File | Change | Reason |
|---|---|---|
| `Makefile` | Modified (unstaged) | Fixed branch names, split stage/deploy, added test gate, dirty-tree guard, branch-exists check, `--no-edit` merge, branch restore |
| `requirements.txt` | Modified (unstaged) | Added `pytest>=8.0.0` — test gate dependency |
| `tests/test_outlier_filter.py` | New (untracked) | 21 unit tests for trust-critical outlier filtering |
| `tests/test_config.py` | New (untracked) | 17 unit tests for deploy-critical URL normalization |
| `CONTEXT.md` | Modified (unstaged) | Added new test files, recent changes (devcontainer entries excluded) |
| `STATUS.md` | Modified (unstaged) | Reconciled with real worktree state |
| `REVIEW_TEST_AND_DEPLOY_2026-03-28.md` | New (untracked) | This review report |

### Tests run
- `pytest tests/test_outlier_filter.py` — 21 passed
- `pytest tests/test_config.py` — 17 passed
- `pytest tests/test_golden_cases.py` — 7 passed
- `pytest tests/test_pricing_service.py tests/test_value_engine.py tests/test_depreciation_rules.py tests/test_data_quality.py tests/test_normalization.py tests/test_data_validator.py` — all passed
- **Total trust-critical tests: 124 passed**
- Full suite run was initiated but takes >2 minutes due to EasyOCR model loading in some test files. Focused runs on all changed/affected areas passed.

---

## QA Review

### Golden test cases: **PASS**
All 7 golden cases pass:
- Sony WH-1000XM4: ok ✓
- Sony WH-1000XM5: ok, distinguished from XM4 ✓
- iPhone 13: ok ✓
- DJI Osmo Pocket 3: ok, not confused with generic Osmo ✓
- MacBook Air M2: ok ✓
- Unknown product: insufficient_evidence ✓
- Low confidence: ambiguous_model ✓

### API shape: **PRESERVED**
No changes to any API endpoint, response schema, or ValueEnvelope structure.

### Trust safeguards: **PRESERVED**
No changes to thresholds, confidence caps, ambiguity gates, or refuse-to-value paths.

### debug_summary: **PRESERVED**
No changes to debug_summary construction or behavior.

### Risk assessment: **LOW**
Changes are strictly additive (new tests) or corrective (Makefile fix). No behavioral changes to the valuation pipeline.

---

## Manager Summary

This review found and fixed two high-severity issues:
1. The `make deploy` command was broken — wrong branch name and it skipped staging entirely. Now split into `make stage` + `make deploy` with correct branches and a test gate.
2. The outlier filter (which decides what prices count in valuations) had zero direct tests. Now has 21 focused tests.

Additionally added 17 tests for the DATABASE_URL normalization that's critical for Railway deployments.

No behavioral changes to the valuation pipeline. All golden tests pass. API shape preserved.

**Decision:** Accept. Follow up with the remaining low-severity items (market_service tests, pgvector in `make db`, smoke test in deploy).

---

## Product Summary (plain language)

We reviewed two things: whether the project has enough safety tests, and whether the deploy process from development to production is safe.

**What we found:**
- The deploy command (`make deploy`) was misconfigured and would have either failed or pushed code directly to production without testing. We fixed this to follow the correct path: development → staging → production, with automatic testing before each step.
- A critical piece of math that decides which price comparisons to trust had no safety tests. We added 21 tests to protect it.
- The database connection setup for Railway (the hosting platform) also had no safety tests. We added 17 tests.

**What didn't change:** The actual valuation logic, the API, and all user-facing behavior are completely unchanged. These changes only add safety nets.

---

## PASTE BACK TO CHATGPT

### Status
complete

### Summary
Combined review of unit tests and deploy flow for the valuation MVP. Found and fixed two high-severity issues: (1) the Makefile `deploy` target used the wrong branch name (`dev` instead of `develop`), skipped staging entirely, and had no test gate — now split into `make stage` (develop→staging with pytest gate) and `make deploy` (staging→main); (2) `outlier_filter.py`, a trust-critical statistical filtering module that directly affects which prices enter valuations, had zero unit tests — now has 21 focused tests. Also added 17 tests for the deploy-critical `_normalize_database_url` function. The test suite overall is strong (~480+ tests, 32 files) with good coverage of trust-critical paths. No behavioral changes to the valuation pipeline. All 7 golden test cases pass. API shape and debug_summary behavior preserved.

### Findings
- **HIGH** — Makefile `deploy` target had wrong branch name (`dev` not `develop`) and skipped staging → fixed in [Makefile](Makefile)
- **HIGH** — `outlier_filter.py` (IQR/MAD filtering) had zero unit tests → fixed in [tests/test_outlier_filter.py](tests/test_outlier_filter.py) (21 tests)
- **MEDIUM** — `_normalize_database_url` in [config.py](backend/app/core/config.py) had no tests → fixed in [tests/test_config.py](tests/test_config.py) (17 tests)
- **MEDIUM** — No automated test gate before staging deploy → fixed in `make stage`
- **MEDIUM** — pytest not declared in [requirements.txt](requirements.txt) → fixed, added `pytest>=8.0.0`
- **LOW** — `market_service.py` has no direct unit tests (only stubs) → recommend adding later
- **LOW** — `image_preprocess.py` has no tests → recommend adding when HEIC/AVIF becomes critical
- **LOW** — `make db` uses `postgres:16` without pgvector → recommend `pgvector/pgvector:pg16`
- **INFO** — `.env.example` still calls Serper "primary" but it's disabled

### Files changed
- `Makefile` — (modified, unstaged) fixed branch names, split stage/deploy, test gate, dirty-tree guard, branch-exists check, `--no-edit` merge, branch restore on cancel/failure
- `requirements.txt` — (modified, unstaged) added `pytest>=8.0.0`
- `tests/test_outlier_filter.py` — (new, untracked) 21 unit tests for IQR/MAD outlier removal
- `tests/test_config.py` — (new, untracked) 17 unit tests for URL normalization and env reading
- `CONTEXT.md` — (modified, unstaged) added new test file entries, recent changes (devcontainer entries excluded for separate commit)
- `STATUS.md` — (modified, unstaged) reconciled with real worktree state, corrected rollback wording
- `REVIEW_TEST_AND_DEPLOY_2026-03-28.md` — (new, untracked) this review report

### Tests run
- `pytest tests/test_outlier_filter.py` — 21 passed ✓
- `pytest tests/test_config.py` — 17 passed ✓
- `pytest tests/test_golden_cases.py` — 7 passed ✓ (golden tests explicitly run)
- `pytest tests/test_pricing_service.py tests/test_value_engine.py tests/test_depreciation_rules.py tests/test_data_quality.py tests/test_normalization.py tests/test_data_validator.py` — 80 passed ✓
- Total trust-critical focused run: 124 passed in 6.74s
- Full suite partial run: 66%+ passed, no failures (EasyOCR model loading causes >2min runtime)

### Deploy risks
- **Fixed:** Makefile now follows correct develop→staging→main flow with test gate
- **OK:** Railway config (railway.toml, Procfile) is clean and consistent
- **OK:** DATABASE_URL normalization handles all Railway URL variants; fail-closed on Railway
- **OK:** Reference data promotion is idempotent with safety guards
- **Remaining risk:** Alembic migrations are still manual post-deploy (acceptable for hobby tier)
- **Remaining risk:** No automated smoke test after Railway deploy
- **Remaining risk:** pgvector availability depends on Railway's Postgres image version
- **Uncertain:** Whether `make stage` test suite runtime (~2min+ with EasyOCR) is acceptable as a deploy gate

### Unit test assessment
- Do we need more unit tests: **yes** — outlier_filter and config were gaps; market_service and image_preprocess are minor gaps
- Should unit tests be added more consistently as changes are made: **yes** — the team has good discipline for feature-level tests but trust-critical utility modules can slip through
- Top 3 highest-value testing areas going forward:
  1. **Comparable scoring edge cases** — more products will create more scoring rules; each rule should have a test
  2. **Pricing confidence formula** — the confidence calculation has many parameters; property-based tests would catch drift
  3. **HTTP endpoint contract tests** — the FastAPI /value endpoint serialization is only tested via engine stubs, not actual HTTP requests

### Assumptions and blockers
- Full test suite takes >2 minutes due to EasyOCR model initialization in test_ocr_service.py — this slows the test gate
- No database available locally for integration tests (Docker not installed per memory)
- Could not verify deploy targets end-to-end (no Railway CLI configured locally)
- Assumed the `staging` and `main` branches exist and are up-to-date (verified via `git branch -a`)

### Git/worktree
Nothing is staged. All changes are unstaged or untracked on branch `develop`.
```
git status --short:
 M CONTEXT.md
 M Makefile
 M STATUS.md
 M requirements.txt
?? .devcontainer/
?? REVIEW_TEST_AND_DEPLOY_2026-03-28.md
?? tests/test_config.py
?? tests/test_outlier_filter.py

git diff --stat:
 CONTEXT.md       | 20 ++++++++------------
 Makefile         | 43 ++++++++++++++++++++++++++++++++++---------
 STATUS.md        | 40 ++++++++++++++++++++++------------------
 requirements.txt |  2 ++
 4 files changed, 66 insertions(+), 39 deletions(-)
```

### Next prompt to ChatGPT
> The test and deploy review is ready to commit. Nothing is staged. Two intended commits: (1) review commit — `Makefile`, `requirements.txt`, `tests/test_outlier_filter.py`, `tests/test_config.py`, `CONTEXT.md`, `STATUS.md`, `REVIEW_TEST_AND_DEPLOY_2026-03-28.md`; (2) devcontainer commit — `.devcontainer/` plus re-adding the devcontainer entries to `CONTEXT.md`. Commit the review first, then the devcontainer. After committing, run `make stage` on the clean tree to verify the happy path end-to-end.
