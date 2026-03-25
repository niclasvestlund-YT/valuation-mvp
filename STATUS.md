# Vision Prompt Rewrite — STATUS.md
Date: 2026-03-25

## Problem
ChatGPT identified "DJI Osmo Pocket 3" from image. Our app returned "DJI Osmo" (ambiguous_model).
Both use OpenAI Vision API. Difference is in our prompt.

## Root Cause
Old prompt was too conservative and lacked generation-detection guidance.
Model saw "OSMO" text on body and returned that as the full model name.

## Old Prompt (key issues)
- "Identify one consumer tech product" — no specificity target
- No chain-of-thought for generation identification
- No examples of desired specificity level
- No product knowledge hints for differentiating generations
- Confidence 0.90+ required visible model text — design-based ID was penalized

## New Prompt (key improvements)
1. Chain-of-thought: Brand → Product Line → Generation/Version → Variant → Cross-check
2. Specificity examples: BAD "DJI Osmo" vs GOOD "DJI Osmo Pocket 3"
3. Product knowledge hints: Pocket 1/2/3 differences, Sony XM4/5, iPhone generations
4. Key rule: "OSMO on body + 2-inch rotatable OLED = Osmo Pocket 3, not just DJI Osmo"
5. Confidence 0.80–0.89 now valid for design-based generation ID
6. Camera-specific requested angles added

## Test Results
- 66/66 tests passing, 0 regressions
- Live API test: needs production verification (no API key in dev env)

## Files Changed
- backend/app/services/vision_service.py — prompt rewrite
- CONTEXT.md — updated
