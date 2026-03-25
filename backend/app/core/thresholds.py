"""
Centralized threshold configuration for the valuation pipeline.

All numeric constants that control identification confidence, comparable scoring,
and pricing behavior live here. This makes tuning and calibration a single-file change.

Grouped by pipeline stage:
1. Vision — confidence caps and evidence requirements
2. Value Engine — ambiguity gates and preliminary estimate thresholds
3. Comparable Scoring — relevance score weights and caps
4. Pricing — confidence formula and gate thresholds
"""

# ─── 1. Vision: confidence caps ─────────────────────────────────────────────

STRONG_IDENTIFICATION_CONFIDENCE = 0.75
EXACT_MODEL_WITHOUT_TEXT_CAP = 0.89
GENERIC_SINGLE_IMAGE_CONFIDENCE_CAP = 0.69
MULTIPLE_ALTERNATIVES_CONFIDENCE_CAP = 0.74
MISSING_CONCRETE_EVIDENCE_CAP = 0.69

# ─── 2. Value Engine: ambiguity + preliminary estimate ──────────────────────

ABSOLUTE_IDENTIFICATION_CONFIDENCE_FLOOR = 0.55
AMBIGUOUS_IDENTIFICATION_CONFIDENCE_THRESHOLD = 0.80
AMBIGUOUS_NEW_PRICE_CONFIDENCE_FLOOR = 0.78
PRELIMINARY_ESTIMATE_CONFIDENCE_FLOOR = 0.86
PRELIMINARY_ESTIMATE_MIN_RELEVANT_SIGNALS = 1
PRELIMINARY_ESTIMATE_MIN_AVERAGE_RELEVANCE = 0.66
PRELIMINARY_ESTIMATE_MIN_DISCOVERY_RESULTS = 3

# ─── 3. Comparable Scoring: relevance weights ───────────────────────────────

# Exact model match in listing title
SCORE_EXACT_MODEL_MATCH = 0.72
SCORE_EXACT_MODEL_TOKENS_MATCH = 0.68
SCORE_CORE_TOKEN_MATCH = 0.65
SCORE_BRAND_MATCH = 0.12
SCORE_LINE_MATCH = 0.14
SCORE_VARIANT_MATCH = 0.05
# Bonus on top of exact match
SCORE_BRAND_BONUS = 0.1
SCORE_LINE_BONUS = 0.08
SCORE_VARIANT_BONUS = 0.06
# Osmo-specific caps
OSMO_GENERATION_MISSING_CAP = 0.58
OSMO_GENERATION_SPECIFIC_CAP = 0.52
OSMO_QUALIFIER_MISMATCH_CAP = 0.58
OSMO_VARIANT_SPECIFIC_CAP = 0.6
OSMO_BUNDLE_VARIANT_CAP = 0.68
# Camera bundle extras cap
CAMERA_BUNDLE_EXTRAS_CAP = 0.68

# ─── 4. Pricing: confidence formula + gates ─────────────────────────────────

MIN_RELEVANCE_SCORE = 0.55
MIN_AVERAGE_RELEVANCE = 0.55
MIN_SOLD_COMPARABLES = 0

BASE_PRICING_CONFIDENCE = 0.2
MAX_PRICING_CONFIDENCE = 0.95
LOW_IDENTIFICATION_CONFIDENCE_CAP = 0.68
AMBIGUOUS_IDENTIFICATION_CONFIDENCE_CAP = 0.78
MULTI_CANDIDATE_CONFIDENCE_CAP = 0.68
SINGLE_CANDIDATE_CONFIDENCE_CAP = 0.78

# Confidence formula weights
CONFIDENCE_COMPARABLE_WEIGHT = 0.08  # per comparable, max 5
CONFIDENCE_COMPARABLE_MAX = 5
CONFIDENCE_RELEVANCE_WEIGHT = 0.2
CONFIDENCE_SOLD_RATIO_WEIGHT = 0.12
CONFIDENCE_NEW_PRICE_BONUS = 0.04
CONFIDENCE_OUTLIER_PENALTY = 0.18

# Graduated penalty for sparse comparables
CONFIDENCE_PENALTY_1_COMPARABLE = 0.25
CONFIDENCE_PENALTY_2_COMPARABLES = 0.15
CONFIDENCE_PENALTY_3_COMPARABLES = 0.05

# Identification confidence thresholds for pricing caps
PRICING_LOW_IDENTIFICATION_THRESHOLD = 0.72
PRICING_AMBIGUOUS_IDENTIFICATION_THRESHOLD = 0.85
