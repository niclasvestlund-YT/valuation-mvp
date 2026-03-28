# Review Swarm V1

This repository now has a local, inspectable `review swarm v1` scaffold for recurring code review runs.

The goal is not to let agents edit code autonomously.
The goal is to:

- run the same local trust checks on a schedule
- capture the repo state in append-only run folders
- generate role-specific review prompts
- keep developer, QA, manager, and product outputs easy to inspect
- optionally execute those reviewer prompts through local `codex exec`

## Why This Shape

This repo already has a good local workflow:

- `automation/workflow.py`
- `automation/diagnose.py`
- `automation/close.py`

`review_swarm.py` adds a second layer on top:

- recurring review runs
- timestamped artifacts
- prompts for reviewer roles
- a stable place to plug in future LLM execution
- filtered review context so swarm output and local-only editor settings do not pollute findings

## Files Added

- `automation/review_swarm.py`
- `automation/review_swarm_config.json`
- `automation/review_swarm.cron.example`
- `automation/review_runs/.gitkeep`

Generated runs live in:

- `automation/review_runs/<timestamp>__<label>/`

Each run contains:

- `repo/`
- `checks/`
- `prompts/`
- `artifacts/`
- `agent_runs/`
- `manifest.json`
- `one_file_summary.md`

## Reviewer Roles

V1 creates prompt files for these roles:

- `developer_reviewer`
- `qa_reviewer`
- `trust_reviewer`
- `manager`
- `product_explainer`

Artifacts created for each run:

- `artifacts/developer_output.md`
- `artifacts/qa_review.md`
- `artifacts/trust_review.md`
- `artifacts/manager_summary.md`
- `artifacts/product_summary.md`

This matches the repo's preferred working style:

- developer output
- QA review
- manager summary
- plain-language product summary
- one-file summary

## Local Checks In V1

Configured in `automation/review_swarm_config.json`:

- golden cases
- trust-sensitive core valuation tests
- full test collection to detect broken imports and missing optional deps

These are intentionally conservative and inspectable.

If a check fails, the run still gets created.
That is useful for nightly review because failures themselves are part of what the reviewers should see.

## Local Reviewer Runner

V1 can now execute the reviewer prompts through local `codex exec`.

Design choices:

- explicit opt-in per run via `--execute-reviewers`
- `read-only` sandbox
- append-only execution logs under `agent_runs/`
- artifact files are only replaced when the CLI returns success and non-empty output
- failed runs keep their logs without silently overwriting the artifact

Configured in `automation/review_swarm_config.json`:

- provider: `codex_exec`
- binary: `codex`
- per-role model selection
- per-role reasoning effort
- per-role timeout

## How To Run

Manual run:

```bash
.venv/bin/python automation/review_swarm.py run --label nightly
```

Manual run plus local reviewer execution:

```bash
.venv/bin/python automation/review_swarm.py run --label nightly --execute-reviewers
```

Prompt-only run:

```bash
.venv/bin/python automation/review_swarm.py run --label manual_review --skip-checks
```

Rebuild summary after reviewers fill artifacts:

```bash
.venv/bin/python automation/review_swarm.py summarize --run-dir automation/review_runs/<run_id>
```

Execute reviewers for an existing run:

```bash
.venv/bin/python automation/review_swarm.py execute --run-dir automation/review_runs/<run_id>
```

Execute only a subset of roles:

```bash
.venv/bin/python automation/review_swarm.py execute --run-dir automation/review_runs/<run_id> --roles qa_reviewer,trust_reviewer
```

The latest run pointer is written to:

```text
automation/review_runs/LATEST
```

## Scheduling

There is a cron example in:

```text
automation/review_swarm.cron.example
```

Recommended cadence:

- every night: `nightly --execute-reviewers`
- before merge: `pre_merge`
- weekly deeper scan: `weekly_trust`

## Current Safety Boundary

V1 is read-only in spirit:

- it gathers repo state
- it runs tests/checks
- it writes review prompts and artifacts
- it may execute local reviewer agents in `read-only` mode
- it does not modify product code

That is the right default for this project because the product is trust-sensitive and should prefer review over silent automated fixing.

## How To Make It More Autonomous Later

The next upgrade path is:

1. keep `review_swarm.py` as the orchestrator
2. keep using the built-in `codex exec` runner for reviewer artifacts
3. write the resulting review back into the matching artifact file
4. let the manager role produce the exact next prompt

Only after that works reliably should you consider a write-capable worker agent.

Recommended order:

1. autonomous review
2. autonomous test-gap generation
3. autonomous patch suggestions
4. write-capable agents only for bounded, low-risk maintenance tasks

## Best-Practice Notes

- Use FastAPI route tests with `TestClient` for contract checks.
- Use pytest fixtures and env monkeypatching for repeatable isolated runs.
- Use property-style tests for invariants like value range ordering and refusal logic.
- Use a frozen evaluation dataset for image/model-identification and trust decisions.

References:

- FastAPI testing: https://fastapi.tiangolo.com/tutorial/testing/
- FastAPI dependency overrides: https://fastapi.tiangolo.com/advanced/testing-dependencies/
- pytest fixtures: https://docs.pytest.org/en/stable/how-to/fixtures.html
- pytest monkeypatch env vars: https://docs.pytest.org/en/stable/how-to/monkeypatch.html
- Hypothesis: https://hypothesis.readthedocs.io/en/latest/
- OpenAI image evals cookbook: https://developers.openai.com/cookbook/examples/evaluation/use-cases/evalsapi_image_inputs
