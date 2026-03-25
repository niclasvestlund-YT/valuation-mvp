# Pricing Model Improvements — STATUS.md
Date: 2026-03-25

## Summary
Six targeted improvements to the pricing engine. All 66 tests pass. Committed to `develop`.

---

## FIX 1 — Depreciation fallback when no comparables

**Before:** 0 comparables + new price → `insufficient_evidence`, no valuation shown.

**After:** 0 comparables + new price → `status=depreciation_estimate` with a fair estimate
calculated from `new_price × category_depreciation_midpoint`.
Confidence is fixed at 0.35. Swedish warning shown to user.
If 0 comparables AND no new price → still `insufficient_evidence`.

---

## FIX 2 — Graduated confidence penalty (replaces hard gate)

**Before:** `< 3 relevant comparables` → hard gate to `insufficient_evidence`.

**After:** 1 comp: −0.25 confidence, 2 comps: −0.15, 3 comps: −0.05, 4+: no penalty.
Pricing proceeds with reduced confidence instead of refusing entirely.

---

## FIX 3 — Percentile price range (replaces raw min/max)

**Before:** `low = min(prices)`, `high = max(prices)` — easily skewed by outliers.

**After:** For ≥4 comparables: p15/p85. For <4: fair ± 15%.

---

## FIX 4 — Canonical engine / deprecated legacy

`pricing_service.py` has CANONICAL PRICING ENGINE header.
`valuation-mvp/.../pricing.py` has DEPRECATED comment.

---

## FIX 5 — Confidence calibration table

Added as comment at top of `pricing_service.py`.
0.80-1.00 Very high / 0.60-0.79 High / 0.40-0.59 Medium / 0.20-0.39 Low / 0.00-0.19 Very low

---

## FIX 6 — response_time_ms on all return paths

Every response envelope now includes `response_time_ms` (integer milliseconds).
Covers all 5 paths in `value_engine.py`.

---

## Test results
- 66 tests, 0 failures
- Updated 2 tests to match new behaviour (FIX 1 + FIX 2)
