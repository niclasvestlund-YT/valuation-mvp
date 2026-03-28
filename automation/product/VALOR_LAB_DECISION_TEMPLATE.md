# VALOR Lab Decision Template

Use this template when reviewing a new VALOR candidate trained in an isolated local lab or shadow setup.

This template is designed for this repo's roles:

- Developer
- QA
- Manager
- Product Explainer

It follows the project's trust-first rules:

- no valuation is better than a misleading valuation
- preserve API compatibility unless explicitly requested
- preserve `debug_summary` behavior
- prefer small reversible changes

## Required Inputs

Before using this template, collect:

- candidate model version
- champion model version
- train/test date windows
- training source breakdown
- gold/silver/bronze sample counts
- holdout metrics
- golden case results
- trust-sensitive test results
- shadow comparison summary if shadow mode was used
- files changed

## Promotion Gates

A candidate must not be promoted if any of these are true:

- golden cases regress
- trust behavior weakens
- API shape changes unexpectedly
- `debug_summary` behavior changes unexpectedly
- candidate is worse than champion on holdout without a narrow, justified exception
- training data contains unverified self-labels as default truth
- rollback path is unclear or untested

## Decision Labels

Use exactly one:

- `accept`
- `accept_with_follow_up`
- `reject`

For QA verdict, use exactly one:

- `pass`
- `fail`

## Developer Output

```md
# Developer Output

Candidate version: TBD
Champion version: TBD
Run type: lab | shadow | promotion_candidate
Date: YYYY-MM-DD

Goal:
- TBD

Files changed:
- TBD

Training data:
- Gold samples: TBD
- Silver samples: TBD
- Bronze samples: TBD
- Sources used: TBD
- Sources excluded: TBD
- Were unverified valuations excluded by default? yes/no

Implementation summary:
- TBD

Evaluation summary:
- Holdout MAE: TBD
- Holdout MAPE: TBD
- vs champion: better/same/worse
- vs naive baseline: better/same/worse
- Worst regressions: TBD

Tests run:
- TBD

Shadow results:
- Not run / TBD

Rollback plan:
- TBD

Assumptions:
- TBD

Risks:
- TBD

Result status:
- pending | ready_for_qa | blocked
```

## QA Review

```md
# QA Review

Candidate version: TBD
Champion version: TBD
Date: YYYY-MM-DD

What was reviewed:
- training data quality
- holdout metrics
- golden cases
- trust-sensitive behavior
- API compatibility
- rollback readiness

Training data concerns:
- TBD

Behavioral findings:
- TBD

Trust concerns:
- TBD

API compatibility issues:
- TBD

debug_summary concerns:
- TBD

Golden case results:
- Sony WH-1000XM4: pass/fail + note
- Sony WH-1000XM5: pass/fail + note
- iPhone 13: pass/fail + note
- DJI Osmo Action / Pocket family: pass/fail + note

Shadow comparison:
- Not run / TBD

Regressions:
- TBD

Test gaps:
- TBD

Trust principle violated: yes/no
Confidence decreased significantly: yes/no

Verdict: pass/fail

Reason:
- TBD
```

## Manager Summary

```md
# Manager Summary

Candidate version: TBD
Champion version: TBD
Date: YYYY-MM-DD

Technical summary:
- TBD

QA verdict:
- pass/fail

Decision:
- accept | accept_with_follow_up | reject

Reason:
- TBD

Open risks:
- TBD

Promotion decision:
- promote now / keep in shadow / reject candidate

Exact next Codex prompt:
```text
TBD
```
```

## Plain-Language Product Summary

```md
# Plain-Language Product Summary

What changed:
- TBD

Why it matters:
- TBD

Did prices become more trustworthy?
- yes/no/unclear

What users would notice:
- TBD

What is still uncertain:
- TBD

What happens next:
- TBD
```

## Combined One-File Summary

```md
# VALOR Candidate Review Summary

Candidate version: TBD
Champion version: TBD
Date: YYYY-MM-DD

Decision:
- accept | accept_with_follow_up | reject

Top reasons:
- TBD

Developer summary:
- TBD

QA summary:
- TBD

Manager summary:
- TBD

Product summary:
- TBD

Promotion status:
- promoted / shadow_only / rejected

Rollback readiness:
- ready / not_ready
```

## Recommended Minimum Checks

Run at least:

- `tests/test_valor_pipeline.py`
- `tests/test_valor_service.py`
- `tests/test_golden_cases.py`
- trust-sensitive pricing/value tests relevant to the changed area

If training logic changed, also inspect:

- training source mix
- excluded sample reasons
- feature importance or equivalent model inspection
- disagreement cases versus current champion

## Suggested Review Rules

Use these review defaults unless there is a strong documented reason not to:

- `gold` data can drive promotion decisions
- `silver` data can help training but should be weighted lower than `gold`
- `bronze` data should not silently become production truth
- external analysis may assist labeling, but should not outrank verified market outcomes
- self-generated model outputs should never become default ground truth

## Minimal Go/No-Go Checklist

Mark each item before promotion:

- [ ] Candidate beats or matches champion on holdout
- [ ] Golden cases pass
- [ ] No trust regression found
- [ ] No unexpected API changes
- [ ] No unexpected `debug_summary` changes
- [ ] Rollback path exists
- [ ] Training data provenance is documented
- [ ] Any external teacher or pseudo-label source is documented
- [ ] QA verdict is `pass`
- [ ] Manager decision is explicit
