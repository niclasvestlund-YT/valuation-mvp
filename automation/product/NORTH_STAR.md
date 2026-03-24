# NORTH_STAR

## Product Vision

Help a person upload photos of used tech, identify the product reliably, and only show a second-hand value when the evidence is strong enough to trust.

## Core Principles

- trust > coverage
- exact model identification matters
- better to ask for more input than guess
- better to return no valuation than a bad one
- debug visibility should improve confidence, not replace it
- preserve API compatibility unless explicitly requested

## Key Goals In The Current Phase

- improve model detection accuracy
- improve comparable relevance
- make pricing stricter and more trustworthy
- keep status handling clear: `ok`, `ambiguous_model`, `insufficient_evidence`, `degraded`, `error`
- preserve `debug_summary` behavior

## Anti-Goals

- do not inflate confidence
- do not hide uncertainty behind polished UI
- do not broaden the product into a generic price scanner
- do not break API shape without explicit approval
- do not overengineer the automation workflow

## Current Focus

- trustworthy second-hand valuation
- better family and generation distinction
- faster local testing and clearer handoff between roles
