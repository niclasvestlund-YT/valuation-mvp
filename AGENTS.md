# AGENTS.md

## Project Purpose

This repository is a second-hand valuation MVP.

Primary goals:
- improve model detection accuracy
- improve comparable relevance
- increase trustworthiness of pricing
- prefer no valuation over a bad valuation
- preserve `debug_summary` behavior
- preserve current API shape unless explicitly requested

## Product Principles

- trust over coverage
- no valuation is better than a misleading valuation
- explain uncertainty clearly
- preserve safe defaults and reversible changes
- use debug visibility to improve testing, not to hide weak behavior

## Safe Change Rules

- prefer small reversible changes
- preserve API compatibility unless explicitly requested
- do not silently weaken trust safeguards
- do not replace explicit uncertainty with synthetic confidence
- stop and escalate if QA fails, trust is violated, or confidence drops significantly

## Testing Expectations

- run focused tests for the changed area
- run the golden test cases listed in [automation/product/GOLDEN_TEST_CASES.md](/Users/niclasvestlund/Documents/New%20project/automation/product/GOLDEN_TEST_CASES.md)
- keep manual QA practical and inspectable
- document what was verified and what was not

## Roles

### Developer
- implements the smallest safe change
- records files changed, tests run, assumptions, and risks
- prefers reversible edits

### QA
- reviews behavior, edge cases, trust risks, and API compatibility
- must always check the golden test cases
- can stop iteration by returning `fail`

### Manager
- decides whether to accept, accept with follow-up, or reject
- checks alignment with [automation/product/NORTH_STAR.md](/Users/niclasvestlund/Documents/New%20project/automation/product/NORTH_STAR.md)
- writes the exact next Codex prompt

### Product Explainer
- rewrites the outcome in plain language for a non-technical reader
- focuses on user impact, safety, and uncertainty

## Output Expectations

Every task should produce:
- developer output
- QA review
- manager summary
- plain-language product summary
- one combined summary file for quick review

## Working Style

- prefer markdown and simple JSON over abstractions
- keep automation inspectable
- keep history append-only
- keep the workflow local and service-free
