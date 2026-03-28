# STATUS — 2026-03-28

## Last task
Combined test + deploy review (initial pass + follow-up hardening)

## What changed
- Makefile: fixed broken deploy (wrong branch `dev`, skipped staging) → split into `make stage` + `make deploy`; follow-up: dirty-tree guard, branch-exists check, `--no-edit` merge, returns to original branch on cancel/failure (does not undo a merge that already landed on the target branch)
- Added pytest to requirements.txt (was implicit transitive dep; `make stage` test gate requires it)
- Added 21 unit tests for outlier_filter.py (trust-critical, was untested)
- Added 17 unit tests for config.py URL normalization (deploy-critical, was untested)
- Updated CONTEXT.md (review-only; devcontainer entries excluded for separate commit)

## Test results
- 124 trust-critical tests passed (including all 7 golden cases)
- No behavioral changes to pipeline

## Not yet committed
Nothing is staged. All changes are unstaged or untracked on branch `develop`.
- Modified (unstaged): Makefile, CONTEXT.md, STATUS.md, requirements.txt
- Untracked: tests/test_outlier_filter.py, tests/test_config.py, REVIEW_TEST_AND_DEPLOY_2026-03-28.md
- Excluded from review commit: .devcontainer/ (separate commit)

## Next up
- Commit the review changes
- Add HTTP contract test for POST /value
- Consider pytest-timeout for EasyOCR slowness
