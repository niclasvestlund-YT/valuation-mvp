# Deep Repository Investigation Report

---

## 1. Executive Summary

**The system's main problems are primarily data problems and math/threshold problems, not AI problems.** The single AI use (OpenAI Vision for product identification) is well-placed and well-engineered. The bigger risks to trust, consistency, and valuation quality come from:

1. **Search quality is the bottleneck, not AI.** The system can only value what it can find. Blocket returns only active listings (no sold data). Tradera's XML API is fragile and rate-limited. When both sources return thin results, the entire pipeline degrades — regardless of how good the vision model is.

2. **The threshold/scoring system is complex and brittle.** There are 25+ hand-tuned constants across 6 files controlling gates, caps, penalties, and floors. Small changes cascade unpredictably. The system already has a history of bugs caused by threshold interactions (visible in commit messages like "fix: scoring and search too aggressive").

3. **Confidence scores are synthetic, not calibrated.** Both vision confidence and pricing confidence are constructed from additive formulas with hand-tuned weights. They look precise (e.g., 0.68) but have no empirical calibration — a "0.68 confidence" doesn't mean "68% of the time this is correct."

4. **There are two separate valuation stacks.** The main backend (`backend/`) is the canonical system; `valuation-mvp/` is a parallel, older implementation with a simpler vision prompt, different model (`gpt-4o`), and less filtering. This creates confusion about which code is live.

5. **The product does the right thing by preferring no valuation over a bad one.** The tiered status system (`ok` → `insufficient_evidence` → `ambiguous_model` → `degraded`) and the preliminary estimate safety net are well-designed trust safeguards. These should be preserved and strengthened, not loosened.

---

## 2. System Map

### End-to-End Valuation Pipeline

```
User uploads image(s)
        │
        ▼
[1] IMAGE PREPROCESSING (image_preprocess.py)
    - Decode base64, resize to 1600px max, convert to JPEG
    - No AI involved — pure image processing
        │
        ▼
[2] PRODUCT IDENTIFICATION (vision_service.py)  ← ONLY AI STEP
    - OpenAI Responses API, gpt-4.1-mini
    - Structured JSON output with json_schema enforcement
    - Post-processing: confidence caps, evidence checks, candidate normalization
        │
        ▼
[3] AMBIGUITY CHECK (value_engine.py:556-628)
    - Hard block if brand OR model is missing
    - Soft warning if confidence < 0.80 or candidates exist
        │
        ▼
[4] MARKET COMPARABLE RETRIEVAL (market_data_service.py)
    - Blocket (scraping, active only, no API key)
    - Tradera (XML SOAP API, active + sold)
    - SerpAPI (fallback when both empty)
    - Progressive fallback queries with aliases
        │
        ▼
[5] NEW PRICE LOOKUP (new_price_service.py)
    - Serper.dev Google Shopping (primary)
    - Google Custom Search (parallel when configured)
    - SerpAPI Google Shopping (last resort)
    - Candidate filtering: used/refurbished/bundle/brand/model mismatch
        │
        ▼
[6] COMPARABLE SCORING (comparable_scoring.py)
    - String-matching on title tokens
    - Poison pattern rejection (broken, parts, locked, etc.)
    - Osmo family disambiguation
    - Bundle/accessory downgrade
        │
        ▼
[7] OUTLIER FILTERING (outlier_filter.py)
    - MAD first (≥5 items), IQR fallback (≥4 items)
        │
        ▼
[8] PRICING (pricing_service.py)
    - Weighted median of filtered comparables
    - Percentile ranges (15th/85th) when ≥4 items
    - New price anchor as constraint bounds only
    - Depreciation fallback when no comparables
        │
        ▼
[9] CONFIDENCE SCORING (pricing_service.py:317-365)
    - Additive formula: base + comparables + relevance + sold ratio + new price
    - Sparse data penalties, identification confidence caps
        │
        ▼
[10] PRELIMINARY ESTIMATE (value_engine.py:334-421)
    - Blended: 75% market signal + 25% depreciation midpoint
    - Only when identification ≥ 0.86 and ≥1 relevant comparable
    - Hard-capped at confidence 0.55
        │
        ▼
[11] RESPONSE ENRICHMENT (api/value.py)
    - Swedish user-facing messages
    - Debug summaries, market snapshots
    - Background DB persistence
```

### Major Modules

| Module | File | Purpose |
|--------|------|---------|
| Vision (AI) | backend/app/services/vision_service.py | Product ID from images |
| Value Engine | backend/app/core/value_engine.py | Pipeline orchestrator |
| Pricing | backend/app/services/pricing_service.py | Price estimation |
| Scoring | backend/app/services/comparable_scoring.py | Relevance scoring |
| Outlier Filter | backend/app/services/outlier_filter.py | Statistical outlier removal |
| Depreciation | backend/app/services/depreciation_rules.py | Category-based depreciation |
| Market Data | backend/app/services/market_data_service.py | Comparable retrieval |
| New Price | backend/app/services/new_price_service.py | New price lookup |
| API | backend/app/api/value.py | HTTP endpoint + enrichment |

### Duplicate/Conflicting Implementations

| Area | Main (canonical) | MVP (legacy) | Risk |
|------|-----------------|--------------|------|
| Vision | `gpt-4.1-mini`, structured output, chain-of-thought | `gpt-4o`, simple prompt, `json_object` | MVP uses different model, simpler prompt, no validation |
| Pricing | Weighted median + outlier filter + depreciation | Separate `pricing.py` in MVP | Logic divergence |
| Scoring | 350-line DJI Osmo-aware scorer | None in MVP | MVP has no relevance filtering |

**The MVP stack at `valuation-mvp/` should be explicitly deprecated or removed.** It is a source of confusion and has no feature parity with the main backend.

---

## 3. Current AI Usage Map

### AI Use #1: Product Identification from Images

| Aspect | Details |
|--------|---------|
| **File** | backend/app/services/vision_service.py |
| **Purpose** | Identify brand, model, category, variant from 1-N product photos |
| **Model** | `gpt-4.1-mini` via OpenAI Responses API |
| **Input** | 1-8 preprocessed JPEG images (max 1600px) |
| **Output** | Structured JSON: brand, line, model, category, variant, candidate_models, confidence, reasoning_summary, needs_more_images, requested_additional_angles |
| **Prompt** | ~95 lines, chain-of-thought with product knowledge, evidence hierarchy, confidence calibration rules |
| **Post-processing** | 5 confidence cap rules based on evidence keywords in reasoning_summary |
| **Cost** | ~$0.01-0.03 per call (gpt-4.1-mini with images) |
| **Latency** | 3-8 seconds typical (30s timeout) |
| **Current risks** | (1) Confidence is self-reported by the model, then capped by keyword heuristics — no ground-truth calibration. (2) Text evidence detection is keyword-matching on the model's own prose, creating a feedback loop. (3) No OCR — the model "reads" text via vision but can't be verified. (4) Non-deterministic: same image can produce different results across calls. |
| **Is AI appropriate?** | **Yes — this is the strongest use case for vision AI.** Identifying a product from photos is genuinely hard, multimodal, and benefits from world knowledge. No deterministic alternative exists. |

### Where AI is NOT used but could be considered

| Area | Current Approach | AI Alternative | Recommendation |
|------|-----------------|----------------|----------------|
| Comparable relevance scoring | String token matching | Cross-encoder or embedding similarity | **Not yet** — string matching is transparent, debuggable, and works for exact models. AI adds opacity for marginal gain. |
| Listing title understanding | Pattern matching + keyword lists | NLU for title parsing | **Not yet** — keyword lists are more predictable. Swedish+English bilingual NLU is hard. |
| New price candidate filtering | Rule-based rejection | LLM to judge "is this the same product?" | **Overkill** — rules work well here. |
| Price estimation | Weighted median | ML regression model | **No** — weighted median is the right tool. ML needs far more training data than available. |

---

## 4. AI Engineer / Developer Findings

### Where AI is helping

1. **Product identification is well-scoped.** Using vision AI for the single hardest step (what is this product?) and keeping everything else deterministic is the right architecture. The prompt is detailed, product-specific, and includes concrete examples — better than 90% of vision prompts I've reviewed.

2. **Structured output enforcement is correct.** Using `json_schema` with `strict: True` eliminates parse failures from the AI output, which is a common source of production bugs.

3. **Post-processing confidence caps are a good trust safeguard.** The system doesn't blindly trust the model's self-reported confidence — it applies evidence-based caps (vision_service.py:632-652). This is the right pattern.

### Where AI is hurting or adding risk

1. **OCR-by-proxy: The system relies on the vision model to "read" text, then checks whether its reasoning_summary mentions text keywords.** This is a fragile feedback loop (vision_service.py:626-628). The model might see "WH-1000XM4" printed on the headband but describe it as "the model identifier is visible" rather than using the exact keyword "text" or "label" — causing the confidence cap to fire incorrectly.

   **Recommendation (hybrid AI + rules):** Add a dedicated OCR step (Google Cloud Vision OCR or PaddleOCR) before the vision call. Pass extracted text strings as additional context to the vision prompt. This makes text evidence verifiable and deterministic.

2. **Non-deterministic outputs affect valuation consistency.** The same product photo can produce `confidence: 0.84` on one call and `confidence: 0.78` on the next, potentially toggling the preliminary estimate threshold (0.86). The system has no caching of vision results for repeat calls.

   **Recommendation (rules / infrastructure):** Cache vision results by image hash for 24 hours. Add a `temperature: 0` (or the lowest available) parameter to the API call (currently not set).

3. **The prompt encodes specific product knowledge that will go stale.** Lines 133-140 in vision_service.py hardcode generation-specific details for DJI Osmo Pocket, Sony WH-1000X, and iPhones. When new products launch, the prompt doesn't know about them.

   **Recommendation (product / workflow change):** This is acceptable for now but should be flagged as maintenance debt. Consider moving product knowledge to a separate data file that can be updated without code changes.

### Where AI should be removed or reduced

**Nowhere currently.** The single AI call is well-placed. The system correctly avoids using AI for scoring, pricing, or filtering where deterministic methods are superior.

### Where non-AI methods would be stronger

1. **OCR for text extraction.** Dedicated OCR (Google Cloud Vision, Tesseract, PaddleOCR) would provide deterministic, verifiable text extraction. The vision model can still do identification, but text evidence would be grounded in actual OCR output rather than the model's prose description.

2. **Search quality improvement.** The biggest valuation quality bottleneck is not AI but search. Blocket returns only active listings with no sold prices. Tradera's XML API is fragile. Adding Finn.no (Norway), Facebook Marketplace data, or a Swedish price aggregator would improve coverage more than any AI improvement.

3. **Comparable reranking.** The current string-matching scorer (comparable_scoring.py) works for exact model matches but fails for near-matches (e.g., "iPhone 13 128GB Midnight" vs. target "iPhone 13"). A lightweight cross-encoder (like `cross-encoder/ms-marco-MiniLM-L-6-v2`) could improve ranking quality without adding AI to the hot path — just as a sorting step after retrieval.

### Best experiments to run next

1. **A/B test vision model temperature.** Compare `temperature: 0` vs current default for identification consistency.
2. **OCR extraction pilot.** Run Google Cloud Vision OCR on 50 product images, compare text findings against the vision model's reasoning_summary.
3. **Search source expansion.** Test adding one new data source (e.g., marketplace scraper for Facebook Marketplace SE) and measure impact on comparable count and pricing gate pass rate.

---

## 5. QA Findings

### Trust Risks

1. **Depreciation estimates are presented alongside market-backed valuations without clear visual differentiation.** A `depreciation_estimate` (confidence 0.35) based purely on new_price × category_ratio uses the same response shape as an `ok` valuation backed by 5+ comparables. The frontend may not distinguish these clearly.
   - Files: pricing_service.py:162-189, value_engine.py:763

2. **Preliminary estimates blend market signals with depreciation but are capped at 0.55 confidence.** If the frontend shows these prominently, users may anchor on them despite the low confidence.
   - File: value_engine.py:405-406

3. **`single_source_insufficient` new prices (confidence 0.2) are used as preliminary estimate anchors.** Line 361 in value_engine.py sets `allow_source_fallback=True`, meaning a single unreliable new-price source can anchor a preliminary estimate. The comment says "risk is acceptable" but this should be validated.

### Consistency / Repeatability Risks

1. **Vision model non-determinism.** No temperature setting, no caching. The same image can produce different identifications on retry.

2. **Blocket scraping is inherently unstable.** The `blocket_api` package uses an internal API that can change without notice. No versioning or contract.
   - File: blocket_client.py:29

3. **Tradera rate limiting causes silent data loss.** When rate-limited, a flag is cached and ALL subsequent queries return empty results for the cache TTL period. This means valuations done during a rate-limit window silently lose Tradera data.
   - File: tradera_client.py:97-100

4. **Cache TTL is not visible in the code.** The `get_cached`/`set_cached` functions are used throughout but the TTL policy is opaque from this code.

### Edge Cases and Failure Modes

1. **Currency mixing.** If Tradera returns EUR listings and Blocket returns SEK, the pricing engine uses `select_currency` which picks the most common. With small sample sizes (2 SEK, 1 EUR), this could mix prices from different markets.
   - File: pricing_service.py:83-95

2. **The outlier filter returns the original list when MAD=0** (all prices identical). This is correct but means no outlier protection when listings have very similar prices with one extreme outlier in a small set (3-4 items).
   - File: outlier_filter.py:41-42

### Missing Test Coverage

1. **No integration tests.** All tests use stubs. There is no test that calls the actual Tradera API, Blocket API, or OpenAI API with real data.

2. **No golden test with real images.** The golden test cases in GOLDEN_TEST_CASES.md are documentation only — they're not automated. There's no test that sends a photo of a WH-1000XM4 and verifies the identification.

3. **No repeatability test.** No test runs the same input N times and checks that results are consistent.

4. **No confidence calibration test.** No test verifies that "confidence 0.80" means the identification is correct 80% of the time.

5. **No pricing accuracy test.** No test compares the system's estimated value against known sale prices.

6. **The comparable_scoring tests cover DJI Osmo well but lack coverage for:** phones with storage variants (iPhone 13 128GB vs 256GB), headphones with similar names (WH-1000XM4 vs WF-1000XM4), laptops with chip variants (MacBook Air M1 vs M2).

---

## 6. Manager Findings

### Top Priorities (Strict Order)

1. **Fix: Add `temperature: 0` to OpenAI vision call and cache results by image hash.** Directly improves consistency with zero risk. (1 hour)

2. **Fix: Deprecate or remove the `valuation-mvp/` stack.** It creates confusion and has no feature parity. If it's serving traffic, migrate. If not, delete it. (2 hours)

3. **Build: Automate golden test cases.** Convert the 4 cases in GOLDEN_TEST_CASES.md into actual test scripts that run against the vision service with real images. Store reference images in the repo. (4 hours)

4. **Build: Add OCR extraction as a pre-step before vision.** Use Google Cloud Vision OCR or similar. Pass extracted text to the vision prompt as grounding evidence. This directly improves model detection accuracy for any product with visible text. (8 hours)

5. **Investigate: Search source expansion.** Blocket's active-only listings are a major data gap. Research whether Tradera's sold data is reliable enough, or whether a new source (Facebook Marketplace, Swappie, Refurbed) would improve coverage. (Research: 4 hours, Implementation: depends)

6. **Build: Add confidence calibration logging.** For every valuation with `status: ok`, log the identification confidence, pricing confidence, and product name. After 100+ valuations, manually review a sample to check whether confidence scores correlate with actual accuracy. (2 hours)

### What to defer

- Cross-encoder reranking for comparables. The string matcher works well enough for exact models. Reranking adds complexity for marginal gain at this stage.
- ML pricing models. Not enough training data. Weighted median is the right approach for now.
- Embedding-based search. The search bottleneck is source availability, not query quality.

### What to reject

- "Use AI for everything" temptation. The system correctly uses AI for one step and rules for everything else. Don't add AI to scoring, pricing, or filtering.
- Removing or loosening confidence caps. These are trust safeguards. They should be calibrated, not removed.
- Displaying depreciation estimates with the same prominence as market-backed valuations. They're fundamentally different quality levels.

### Exact Next Implementation Prompt for Codex

```
Task: Add deterministic vision result caching and temperature control.

In backend/app/services/vision_service.py:
1. Add `"temperature": 0` to the payload dict in _build_request_payload() (line 400).
2. Before calling _post_with_retry(), compute a SHA-256 hash of the sorted processed image
   data_urls concatenated. Check the cache (using the existing get_cached/set_cached from
   backend/app/utils/cache.py) with key "vision:{hash}". If cached, parse and return the
   cached ProductIdentificationResult. After a successful API call, cache the raw JSON
   response with the same key.
3. Add a test in tests/test_vision_service.py that verifies the cache is hit on a second
   call with the same image data.

Do not change the prompt, model, or any confidence logic.
Do not change the API response shape.
Run existing tests to verify nothing breaks.
```

### Exact Next QA Prompt

```
Task: Verify the temperature and caching changes don't alter behavior.

1. Run all existing tests: pytest tests/ -v
2. Manually test with USE_MOCK_VISION=true to verify mock path still works.
3. Verify that the cache key includes ALL images (not just the first).
4. Verify that manual override (brand+model provided) bypasses the cache correctly.
5. Check that the cached response is the raw API JSON, not a Python object (to avoid
   serialization issues).
6. Confirm temperature:0 doesn't cause any OpenAI API errors with the Responses API.
```

---

## 7. Product Explainer Findings

### What the system does (plain language)

The product takes a photo of a used gadget, figures out what it is using AI, searches Swedish marketplaces (Blocket, Tradera) for similar items, and estimates what it's worth based on what similar items sell for.

### What users are likely experiencing today

1. **"I uploaded a clear photo but it said it needs more images."** This happens when the AI identifies the brand but isn't sure about the exact model (e.g., knows it's Sony headphones but not which generation). The system correctly asks for more evidence rather than guessing — but users may not understand why.

2. **"I got a price last time but not this time for the same product."** Because the AI isn't perfectly consistent between calls and marketplace listings change daily, the same product can get a valuation one day and "insufficient evidence" the next. This erodes trust.

3. **"The price seems too low/too high."** When only 1-2 comparable listings are found, the estimate is heavily influenced by those few data points. A single overpriced listing can skew the result.

4. **"It showed a price range that's really wide."** When comparables are sparse (fewer than 4), the system uses ±15% around the fair estimate rather than actual market percentiles, which can feel imprecise.

### Why it feels inconsistent

The core issue is that the system depends on marketplace search results that change hourly. The product isn't unstable — the underlying data is. The system handles this correctly by refusing to show a valuation when evidence is weak, but this feels like inconsistency to the user.

### How improvements would help

- **OCR** would mean the system can verify "I can read 'WH-1000XM4' on the headband" rather than relying on the AI's description. This makes identification more reliable and fewer "need more images" cases.
- **Caching** would mean the same photo always gets the same identification, removing one source of inconsistency.
- **Better search sources** would mean more comparables, which means fewer "insufficient evidence" results and tighter price ranges.

---

## 8. Prioritized Opportunity List

### Rank 1: Vision Result Caching + Temperature Control
- **Problem:** Same image can produce different identifications, toggling valuation eligibility
- **Recommendation:** Add `temperature: 0`, cache results by image hash
- **Why:** Directly fixes the most visible consistency issue
- **Classification:** Rules / infrastructure
- **Impact:** High consistency, medium trust
- **Effort:** 1 hour
- **Risk:** Very low

### Rank 2: Deprecate valuation-mvp/ Stack
- **Problem:** Two divergent implementations cause confusion
- **Recommendation:** Archive or delete `valuation-mvp/` entirely
- **Classification:** Product / workflow change
- **Impact:** Medium (removes confusion, reduces maintenance)
- **Effort:** 2 hours
- **Risk:** Low (verify nothing references it in production)

### Rank 3: Automate Golden Test Cases
- **Problem:** No automated regression testing for the most critical path (product identification)
- **Recommendation:** Create a test suite with real product images and expected outputs
- **Classification:** Rules / data only
- **Impact:** High trust, high consistency (prevents regressions)
- **Effort:** 4 hours
- **Risk:** Very low

### Rank 4: OCR Pre-Step for Text Evidence
- **Problem:** Text evidence detection relies on keyword matching against the AI's own prose
- **Recommendation:** Add dedicated OCR, pass extracted text to vision prompt
- **Classification:** Hybrid AI + rules
- **Impact:** High trust, high valuation quality (better model disambiguation)
- **Effort:** 8 hours
- **Risk:** Low-medium (new dependency, but additive — doesn't change existing flow)

### Rank 5: Confidence Calibration Logging
- **Problem:** Confidence scores are synthetic, not empirically calibrated
- **Recommendation:** Log all predictions, sample and verify monthly
- **Classification:** Product / workflow change
- **Impact:** High trust (over time), enables data-driven threshold tuning
- **Effort:** 2 hours
- **Risk:** Very low

### Rank 6: Search Source Expansion Research
- **Problem:** Blocket (active only) and Tradera (rate-limited) leave major data gaps
- **Recommendation:** Research Facebook Marketplace SE, Swappie, or direct scraping improvements
- **Classification:** Data only
- **Impact:** High valuation quality (more comparables = better estimates)
- **Effort:** 4 hours research + variable implementation
- **Risk:** Medium (new integrations are maintenance burden)

### Rank 7: Cross-Encoder Reranking for Comparables
- **Problem:** String token matching fails for near-matches and variant disambiguation
- **Recommendation:** Add a lightweight cross-encoder as a reranking step after retrieval
- **Classification:** AI-first
- **Impact:** Medium valuation quality
- **Effort:** 12 hours
- **Risk:** Medium (adds model dependency, needs evaluation)

### Rank 8: Threshold Consolidation
- **Problem:** 25+ hand-tuned thresholds across 6 files create unpredictable interactions
- **Recommendation:** Consolidate all thresholds into a single config file with documentation of what each controls and why
- **Classification:** Rules / workflow change
- **Impact:** Medium (developer velocity, debuggability)
- **Effort:** 4 hours
- **Risk:** Low

---

## 9. Evaluation Plan

### Offline Tests

| Test | What | How | Frequency |
|------|------|-----|-----------|
| Golden image identification | 20+ product images with known ground truth | Run vision_service.detect_product(), compare brand/model/confidence against expected values | Every PR that touches vision |
| Scoring regression | 50+ listing titles with expected scores | Run score_comparable_relevance(), assert score ranges | Every PR that touches scoring |
| Pricing accuracy | 10+ products with known recent sale prices | Run full pipeline, compare fair_estimate to actual sale price | Monthly |

### Golden Cases (minimum set)

| Product | Expected Brand | Expected Model | Key Challenge |
|---------|---------------|----------------|---------------|
| Sony WH-1000XM4 | Sony | WH-1000XM4 | Distinguish from XM5 |
| Sony WH-1000XM5 | Sony | WH-1000XM5 | Distinguish from XM4 |
| iPhone 13 | Apple | iPhone 13 | Distinguish from 12/14 |
| iPhone 13 Pro | Apple | iPhone 13 Pro | Distinguish from 13 |
| DJI Osmo Pocket 3 | DJI | DJI Osmo Pocket 3 | Distinguish from Pocket 2 |
| DJI Osmo Action 5 Pro | DJI | DJI Osmo Action 5 Pro | Distinguish from Action 4, handle "Osmo" prefix |
| MacBook Air M2 | Apple | MacBook Air M2 | Distinguish from M1 |

### Repeatability Checks

- Run each golden case 5 times. All 5 should return the same brand+model. Confidence should not vary by more than 0.05.
- Run the same product through the full pipeline twice in 5 minutes. Price estimates should match exactly (same comparables cached).

### Confidence Calibration Checks

- After 200+ valuations, bucket by confidence range (0.3-0.5, 0.5-0.7, 0.7-0.9, 0.9+).
- For each bucket, manually verify a sample of 20.
- Actual accuracy should correlate with stated confidence. If "0.80 confidence" products are correct only 50% of the time, the calibration is broken.

### Regression Checks

- Before any threshold change, run the full golden set and record results.
- After the change, re-run and diff. No golden case should degrade without explicit justification.

---

## 10. Final Combined Table

| Area | Current Approach | Problem | Recommendation | Role(s) | AI/Non-AI | Trust | Consistency | Effort | Risk | Priority |
|------|-----------------|---------|----------------|---------|-----------|-------|------------|--------|------|----------|
| Vision determinism | No temperature, no caching | Same image → different results | Add temp:0 + cache by hash | Dev, QA | Non-AI | Medium | **High** | 1h | Very Low | **1** |
| Dual codebase | Main + MVP both exist | Confusion, divergent logic | Delete/archive MVP | Manager, Dev | Non-AI | Medium | Medium | 2h | Low | **2** |
| Test coverage | Stubs only, no real images | No regression protection | Automate golden tests | QA, Dev | Non-AI | **High** | **High** | 4h | Very Low | **3** |
| Text evidence | AI prose keyword matching | Fragile feedback loop | Dedicated OCR pre-step | Dev | Hybrid | **High** | **High** | 8h | Low-Med | **4** |
| Confidence meaning | Synthetic additive formula | Scores look precise but aren't calibrated | Calibration logging | QA, Product | Non-AI | **High** | Medium | 2h | Very Low | **5** |
| Search sources | Blocket (active) + Tradera (rate-limited) | Thin data = bad valuations | Research new sources | Manager, Dev | Non-AI | Medium | **High** | 4h+ | Medium | **6** |
| Comparable ranking | String token matching | Misses near-matches | Cross-encoder reranking | Dev | AI | Medium | Medium | 12h | Medium | **7** |
| Threshold sprawl | 25+ constants across 6 files | Cascade bugs, hard to debug | Consolidate to config file | Dev | Non-AI | Medium | Medium | 4h | Low | **8** |
| Depreciation display | Same response shape as market-backed | Users can't tell quality level | Frontend differentiation | Product | Non-AI | **High** | Low | 4h | Low | **9** |
| New price anchoring | Single source used for preliminary estimate | Low confidence anchor drives estimate | Raise min sources to 2 for anchor | Dev, QA | Non-AI | Medium | Medium | 1h | Low | **10** |

---

**Bottom line:** This is a well-architected system that uses AI correctly — one focused call for the genuinely hard problem (product identification), with everything else built on deterministic rules and statistics. The main improvement opportunities are not AI problems — they're data availability, threshold management, test coverage, and consistency infrastructure. The trust-first design philosophy (prefer no valuation over bad valuation) is the system's greatest strength and should be protected, not diluted.
