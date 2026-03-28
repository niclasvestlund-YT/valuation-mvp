# Tradera/Blocket Image Dataset Analysis

Date: 2026-03-28
Type: trust-first analysis round

Grounding:
- Read: `AGENTS.md`
- Read: `automation/product/NORTH_STAR.md`
- Read: `automation/product/GOLDEN_TEST_CASES.md`
- Read: `automation/product/VALOR_LAB_DECISION_TEMPLATE.md`
- Read: `automation/REVIEW_SWARM_V1.md`
- Read: `automation/review_swarm_config.json`
- Read: `tests/test_golden_cases.py`
- Read: `tests/test_vision_service.py`
- Read: `scripts/train_valor.py`
- Read: `backend/app/core/value_engine.py`
- Ran: `.venv/bin/python -m pytest tests/test_golden_cases.py -q` -> `7 passed`
- Ran: `.venv/bin/python -m pytest tests/test_vision_service.py -q` -> `4 passed`

External source check for rights/privacy:
- Blocket user terms, effective 2023-08-24: https://www.blocket.se/villkor/villkor-privat/anvandarvillkor
- Tradera user agreement, version 2025-01-07: https://www.tradera.com/support/nl/terms/terms-and-conditions/anvaendaravtal-2025-01-07/
- IMY on GDPR and AI, updated 2025-08-21: https://www.imy.se/verksamhet/dataskydd/innovationsportalen/vagledning-om-gdpr-och-ai/gdpr-och-ai/ai-och-tillampning-av-gdpr/
- IMY on GDPR principles: https://www.imy.se/verksamhet/dataskydd/det-har-galler-enligt-gdpr/grundlaggande-principer/

# Developer Output

Candidate version: N/A
Champion version: N/A
Run type: analysis_review
Date: 2026-03-28

Goal:
- Assess whether a local image folder or dataset based on Tradera/Blocket listings is a good idea for internal testing, model identification, and possible future learning.

Files changed:
- `automation/product/TRADERA_BLOCKET_IMAGE_DATASET_ANALYSIS_2026-03-28.md`

Training data:
- Gold samples: not created
- Silver samples: not created
- Bronze samples: not created
- Sources used: repo documents, tests, pipeline code, official terms/privacy sources
- Sources excluded: no marketplace images collected
- Were unverified valuations excluded by default? yes

Implementation summary:
- No product code changed.
- This repo already has a strong refusal-oriented valuation pipeline in `backend/app/core/value_engine.py`.
- This repo still lacks a frozen real-image evaluation set. Current golden tests in `tests/test_golden_cases.py` use mocked vision outputs, not real listing images.
- `automation/REVIEW_SWARM_V1.md` already points toward a frozen evaluation dataset for image/model-identification and trust decisions.
- `scripts/train_valor.py` already shows the repo's preferred trust posture for learning loops: lab mode excludes valuation-derived samples by default to avoid self-reinforcement. The same caution should apply even more strongly to image labels derived from listings.

Evaluation summary:
- Holdout MAE: N/A
- Holdout MAPE: N/A
- vs champion: N/A
- vs naive baseline: N/A
- Worst regressions: N/A

Tests run:
- `.venv/bin/python -m pytest tests/test_golden_cases.py -q`
- `.venv/bin/python -m pytest tests/test_vision_service.py -q`

Shadow results:
- Not run

Rollback plan:
- No runtime or API changes were made.
- If the pilot is later scaffolded, keep it doc-only and local-only first so it can be removed by deleting one local folder and one spec file.

Assumptions:
- The goal is internal evaluation first, not immediate product retraining.
- The user wants a practical recommendation that preserves current API shape and `debug_summary`.
- The repo should remain trust-first and refusal-friendly.

Risks:
- Rights and terms-of-use risk if marketplace images are copied locally without clear permission.
- Privacy risk if images contain identifiable people, names, addresses, phone numbers, receipts, or IMEI/serial details.
- Leakage risk if the same listing, resized duplicate, or cross-posted ad appears in both future eval and training pools.
- False ground truth risk if seller title, filename, or model output is treated as verified truth.

Result status:
- ready_for_qa

Recommendation:
- Yes to the need.
- No to the broad sourcing plan as stated.
- Recommended now: a tiny, local, rights-reviewed, `eval_only` pilot for frozen regression testing.
- Not recommended now: a general Tradera/Blocket image corpus for future training.

Direct answers to the required questions:

1. Is this a good idea right now for this repo?
- Partly.
- A frozen real-image eval set is a good idea now because the repo currently relies on mocked golden cases and therefore cannot measure real photo behavior.
- A Tradera/Blocket-derived image corpus for broad storage or future training is not a good idea right now because rights, privacy, and leakage controls are not yet mature enough.

2. If yes, should phase 1 be a small `eval_only` pilot or something else?
- Yes: phase 1 should be a small local `eval_only` pilot.
- It should not be a training dataset, and it should not default to `training_candidate`.

3. What is the concrete benefit for internal end-to-end testing?
- It closes the current gap between mocked golden tests and real image behavior.
- It lets us test whether real photos trigger the correct refusal path: `ok`, `ambiguous_model`, or `insufficient_evidence`.
- It gives a stable local benchmark even when live marketplace results change.
- It can test the join between vision evidence, ambiguity handling, and `debug_summary` without changing the API.

4. Does it help model identification, or mainly risk false confidence?
- It helps model identification only if labels are explicitly verified and refusal cases are included from the start.
- It mainly creates false confidence if filenames, seller titles, model outputs, or over-trusted ad context become de facto ground truth.
- The strongest use right now is regression evaluation, not learning.

5. How should the dataset be structured: per image or per listing/case?
- Primarily per listing/case.
- Reason: the product accepts multiple images, the truth usually belongs to the listing as a whole, and leakage must be controlled at case level.
- Images should be child records under the case.

6. How should folder structure, filenames, and metadata look?
- Folder structure should be case-first, not loose images.
- Filenames should be for human organization only, never for labels.
- Labels must come from metadata, not from folder names or image names.

Recommended folder structure:

```text
<LOCAL_LISTING_DATASET_DIR>/
  README.md
  manifests/
    pilot_manifest.json
    removals.jsonl
  cases/
    case_se_0001/
      case.json
      images/
        image_01.jpg
        image_02.jpg
    case_se_0002/
      case.json
      images/
        image_01.jpg
```

Recommended storage location:
- Best: outside repo, for example `~/valor-local-data/listing_cases_v1/`
- Acceptable fallback: repo-local but git-ignored, for example `data/local/listing_cases_v1/`

Recommended filename style:
- `image_01.jpg`, `image_02.jpg`
- Optional human suffixes like `image_01_front.jpg` are fine for us, but must never be read as labels by eval or training code.

7. Which labels should be required immediately, and which should be optional or uncertain?
- Required immediately for every case:
  - `case_id`
  - `source`
  - `listing_id`
  - `collected_at` or `captured_at`
  - `expected_category`
  - `label_confidence`
  - `use`
  - `split`
  - `notes`
  - `rights_status`
  - `removal_supported`
- Required for positive exact-model cases:
  - `expected_brand`
  - `expected_model`
- Optional or nullable:
  - `expected_line`
  - `expected_model` for ambiguous or negative cases
  - `captured_at` if only `collected_at` is known
- Strongly recommended extra fields:
  - `expected_status`
  - `uncertainty_reason`
  - `dedupe_group_id`
  - `visible_text_evidence`
  - `manual_reviewed_by`
  - `reviewed_at`

8. Which negative cases must exist from the start?
- Accessory-only
- Empty box
- Replacement parts
- Body/base-unit only
- Low-quality or blurry images
- Duplicate or cross-posted listing
- Wrong category
- Mixed objects in one listing
- Unclear model despite correct brand
- Suspected fake or replica
- Near-family confusers:
  - `WH-1000XM4` vs `WH-1000XM5`
  - `WH-1000XM4` vs `WF-1000XM4`
  - `iPhone 13` vs `iPhone 13 Pro`
  - `iPhone 13` vs `iPhone 14`
  - `DJI Osmo Action` vs `DJI Osmo Pocket`
  - `Osmo Pocket 2` vs `Osmo Pocket 3`

9. How should golden cases be extended with real image cases around Sony WH-1000XM4/XM5, iPhone 13, and the DJI Osmo family?
- Extend in two layers:
  - image-identification evals with real images
  - full-pipeline evals with stubbed comparables/new-price fixtures
- Minimum recommended additions:
  - Sony WH-1000XM4:
    - 2 clear exact-model cases
    - 1 ambiguous-angle case
    - 1 negative accessory or case-only case
  - Sony WH-1000XM5:
    - 2 clear exact-model cases
    - 1 ambiguous-angle case
    - 1 wrong-family negative, preferably `WF-1000XM5` or similar nearby confusion
  - iPhone 13:
    - 2 clear cases
    - 1 near-confuser negative (`iPhone 13 Pro` or `iPhone 14`)
    - 1 low-evidence or covered-phone case
  - DJI Osmo family:
    - 1 clear `Osmo Action`
    - 1 clear `Osmo Pocket 3`
    - 1 `Action` vs `Pocket` family confusion case
    - 1 generation confusion case
    - 1 combo/bundle-heavy case
    - 1 accessory-only case

10. What legal or privacy-related risks exist if ad images are stored locally?
- Rights risk:
  - Blocket's current terms say material on the site may not be copied or distributed without prior written permission, and automated use such as robots, spiders, indexing, or systematic use is also prohibited.
  - Tradera's current user agreement prohibits scrapers and copying or reproducing content from Tradera or third parties without prior written consent.
- Privacy risk:
  - IMY states that images where a person is visible can be personal data.
  - IMY also states that selecting, storing, and using personal data in an AI dataset is personal-data processing and requires a legal basis, clear purpose, minimization, security, and deletion routines.
- Inference from those official sources:
  - A local marketplace-image dataset is not legally clean by default, especially not for broad collection or future training.
  - This is a risk assessment, not legal advice.

11. Should raw images live in the repo, outside the repo, or git-ignored?
- Raw images should live outside the repo by default.
- If local convenience wins, the fallback should be a git-ignored folder.
- Repo-tracked content should be limited to:
  - the spec
  - metadata template
  - schema
  - local eval harness
- Raw third-party images should not be committed.

12. Which exit criteria decide whether the pilot is worth continuing?
- The pilot is worth continuing only if all of the following are true:
  - at least 24 cases were collected
  - at least 10 cases are hard negatives or refusal-sensitive
  - 100% of cases have complete metadata
  - 100% of cases are removable via `listing_id` and source trace
  - 0 split leakage by `listing_id`, `dedupe_group_id`, or perceptual duplicate check
  - the eval finds at least one actionable regression or one trustworthy improvement opportunity that mocked tests could not see
  - no proposal based on the pilot weakens refusal behavior
- Stop instead of scaling if:
  - rights status remains unclear
  - labels are mostly silver or bronze
  - duplicate leakage is hard to control
  - the pilot mostly measures seller text or easy backgrounds rather than actual product evidence

13. What exact next Codex step is recommended after this analysis?
- Scaffold a local `eval_only` pilot spec and metadata validation, without collecting or training on marketplace images yet.

Minimum sensible pilot scope:
- 24 cases total
- 14 positive or near-positive cases
- 10 negative or refusal-sensitive cases
- 2 to 6 images per case
- All cases marked `use: eval_only`
- All pilot cases marked `split: frozen_eval`

Labeling policy:
- `gold`
  - Exact model is manually verified from image-visible evidence or strong corroborating evidence.
  - Safe for frozen eval.
  - Not automatically safe for training unless rights are separately cleared.
- `silver`
  - Likely correct, but exact-model proof is incomplete.
  - Use for ambiguity/refusal eval or family-level checks.
  - Do not treat as exact-model training truth.
- `bronze`
  - Weak, contradictory, or context-derived only.
  - Use only for hard negatives, exploratory review, or uncertainty cases.
  - Never use as exact-model ground truth.

How uncertainty should be marked:
- `label_confidence: silver` or `bronze`
- `expected_model: null` when exact model is not verified
- `expected_status: ambiguous_model` or `insufficient_evidence`
- `uncertainty_reason`: short explicit string such as `model_text_not_visible`, `nearby_family_confusion`, or `suspected_fake`

Split policy for future eval and training:
- Split at case level, never at image level.
- All images from the same listing stay together.
- Cross-posts and near-duplicates share one `dedupe_group_id` and must stay in one split.
- Recommended now:
  - pilot cases: `split: frozen_eval`
- Recommended later:
  - future training candidates: start as `split: unassigned`
  - assign `train`, `dev`, or `holdout` only after dedupe and rights review
- Never move a frozen eval case into training later.

How to collect difficult negatives:
- Deliberately search for:
  - seller photos of accessories only
  - screenshots of packaging only
  - blurry distance shots
  - mixed bundles
  - nearby model families
  - damaged or parts-only listings
  - suspicious fakes or replicas
- The difficult negatives are more valuable than adding more easy positives.

How to avoid increasing confidence without better evidence:
- Do not lower thresholds based on this pilot alone.
- Do not promote `silver` or `bronze` labels into exact-model truth.
- Do not let filenames or listing titles enter the label path.
- Treat improvement as:
  - more correct refusals
  - more correct exact-model calls on gold cases
  - fewer false exact-model calls on negatives
- Treat "more outputs" without stronger evidence as a failure mode, not an improvement.

Recommended per-case metadata file:

```json
{
  "case_id": "case_se_0001",
  "source": "tradera",
  "listing_id": "1234567890",
  "captured_at": null,
  "collected_at": "2026-03-28T10:15:00Z",
  "expected_brand": "Sony",
  "expected_line": "WH-1000X",
  "expected_model": "WH-1000XM4",
  "expected_category": "headphones",
  "label_confidence": "gold",
  "use": "eval_only",
  "split": "frozen_eval",
  "notes": "Model text visible on inside headband. One image shows carrying case.",
  "rights_status": "not_cleared_for_training",
  "removal_supported": true,
  "expected_status": "ok",
  "uncertainty_reason": null,
  "dedupe_group_id": "sony_xm4_group_01",
  "images": [
    {
      "image_id": "image_01",
      "filename": "image_01.jpg",
      "sha256": "TBD",
      "phash": "TBD",
      "view": "front_angle",
      "quality": "clear"
    },
    {
      "image_id": "image_02",
      "filename": "image_02.jpg",
      "sha256": "TBD",
      "phash": "TBD",
      "view": "inside_headband",
      "quality": "clear"
    }
  ]
}
```

# QA Review

Candidate version: N/A
Champion version: N/A
Date: 2026-03-28

What was reviewed:
- fit with trust-first product rules
- fit with current golden cases and tests
- real-image regression value
- labeling error risk
- leakage controls
- API compatibility and `debug_summary` preservation

Training data concerns:
- The proposed idea becomes unsafe as soon as `eval_only` and `training_candidate` are mixed informally.
- Listing-derived labels are noisy by default.
- Model outputs or old valuations must not backfill missing truth.
- Rights-clearing is not good enough for marketplace-derived training data right now.

Behavioral findings:
- The repo's current gap is real-image evaluation, not lack of more synthetic labels.
- `tests/test_golden_cases.py` validates full valuation flow, but only from mocked identification outputs.
- `tests/test_vision_service.py` already encodes trust-sensitive behavior like confidence reduction and `needs_more_images`; a real-image pilot would strengthen that coverage.
- The value engine already treats ambiguity and insufficient evidence as first-class outputs. A pilot should test those behaviors, not try to suppress them.

Trust concerns:
- Easy positives alone would produce a misleading picture.
- The pilot must contain refusal-sensitive negatives from day one or it will bias the team toward broader confident output.

API compatibility issues:
- None if the next step stays doc-only and local-eval-only.

debug_summary concerns:
- None if the pilot is used only for local evaluation.
- A future harness should assert current `debug_summary` fields, not bypass them.

Golden case results:
- Sony WH-1000XM4: pass + current mocked golden test passes; missing real-image coverage
- Sony WH-1000XM5: pass + current mocked golden test passes; missing real-image coverage
- iPhone 13: pass + current mocked golden test passes; missing real-image coverage
- DJI Osmo Action / Pocket family: pass + current mocked golden test passes; missing real-image coverage

Shadow comparison:
- Not run

Regressions:
- No code regressions detected in this analysis round.
- Main gap remains lack of real-image regression cases.

Test gaps:
- No local harness yet for case-level image fixtures
- No repeatability check on the same real case
- No explicit leakage audit tool
- No metadata validator for future case folders

Trust principle violated: no
Confidence decreased significantly: no

Verdict: pass

Reason:
- A tiny `eval_only` pilot is testable, reversible, aligned with current goals, and directly improves regression visibility.
- A broader marketplace-derived dataset or training plan would fail QA at this stage.

# Trust Review

Date: 2026-03-28

Trust-first judgment:
- Proceed only with a very small, local, frozen, `eval_only` pilot.
- Do not approve a general Tradera/Blocket image dataset for future training now.

Why:
- `backend/app/core/value_engine.py` is designed to preserve refusal behavior. The main trust risk is not lack of images; it is accidentally training or evaluating on weak labels that encourage false exact-model confidence.
- `scripts/train_valor.py` already avoids self-reinforcement in lab mode by excluding valuation-derived samples by default. The same principle should apply to image labels from ads.

Critical trust risks:
- False ground truth:
  - Seller title is not proof.
  - Filename is not proof.
  - The model's own output is not proof.
  - A successful valuation is not proof.
- Leakage:
  - same listing in multiple folders
  - same listing mirrored across sources
  - same photo re-uploaded with a new listing id
  - cropped or screenshot versions of the same image
- Confidence inflation:
  - If the pilot mostly contains clear hero shots, it will encourage threshold loosening.
  - Improvement must be measured on near-confusers and refusal cases, not just easy wins.
- Rights and privacy:
  - Official Blocket and Tradera terms make broad copying and automated collection risky.
  - IMY guidance means visible people and other identifying details move the dataset into GDPR territory.

Required trust boundaries:
- `use` must default to `eval_only`
- `training_candidate` must require a separate review gate
- `split` must be case-level
- `frozen_eval` cases must never move into future training
- `rights_status` must default to a non-training state
- `removal_supported` must be true for every kept case
- `expected_model` must be null when exact model is uncertain

Trust review on the original idea statement:
- "local image folder/dataset with images from listings for internal testing" -> conditionally acceptable
- "better model identification" -> acceptable only as evaluation feedback
- "possible future training/learning" -> not acceptable as a default extension of this same dataset

Recommended trust-safe interpretation:
- Build a frozen evaluation set first.
- Use it to measure exact-model accuracy and refusal quality.
- Only after that, and only with rights-cleared sources and explicit split control, consider separate `training_candidate` intake.

# Manager Summary

Candidate version: N/A
Champion version: N/A
Date: 2026-03-28

Technical summary:
- The repo needs a frozen real-image eval layer more than it needs more training data.
- The current product and tests are already trust-oriented; the dataset should strengthen that posture, not widen coverage at the expense of certainty.
- A tiny local `eval_only` pilot is aligned with `AGENTS.md`, `NORTH_STAR.md`, the current golden cases, and the repo's existing anti-self-reinforcement posture.
- The proposed source choice, Tradera/Blocket ad images, introduces real rights and privacy concerns, so the accepted scope must be narrower than the original idea.

QA verdict:
- pass

Decision:
- accept_with_follow_up

Reason:
- Accept the need for a frozen real-image eval pilot.
- Do not accept a broad marketplace-image dataset or future training path yet.
- Follow-up is required to formalize rights status, removal support, split policy, and metadata validation before any image collection starts.

Open risks:
- unclear rights to copy and retain marketplace images
- privacy exposure in images with people or identifying information
- duplicate leakage across future eval/training
- pressure to treat weak labels as exact-model truth

Promotion decision:
- keep in shadow

Exact next Codex prompt:
```text
Task: Scaffold a trust-first local eval-only listing-case pilot without changing product behavior.

Create a spec and local validation scaffold for a frozen image-eval pilot.

Requirements:
1. Add a new markdown spec under automation/product that defines:
   - case-first folder structure
   - required metadata fields
   - gold/silver/bronze labeling policy
   - split policy with frozen_eval
   - rights_status and removal_supported rules
   - negative-case collection rules
2. Add a repo-tracked metadata template JSON file for one case.
3. Add a JSON schema or equivalent validator input for the metadata file.
4. Add a git-ignore rule for a local raw-image folder, but do not add any real marketplace images.
5. Add a local-only pytest that validates metadata files when a dataset path exists, and skips cleanly otherwise.

Guardrails:
- Do not change API shape.
- Do not change debug_summary behavior.
- Do not change vision thresholds or pricing thresholds.
- Do not create any training integration.
- Do not ingest or scrape Tradera/Blocket images automatically.

Verification:
- Run tests/test_golden_cases.py
- Run tests/test_vision_service.py
```

# Plain-Language Product Summary

What changed:
- No product code changed.
- We analyzed whether it is smart to save ad images locally for better testing and future learning.

Why it matters:
- Right now the project has good trust rules and mocked golden tests, but it still lacks a small frozen set of real images that can reveal real-world identification mistakes.

Did prices become more trustworthy?
- unclear

What users would notice:
- Nothing yet.
- If a small eval pilot is built later, users should not notice any immediate behavior change. The benefit is safer internal testing before future model or prompt changes.

What is still uncertain:
- Whether marketplace images may be stored locally without permission problems
- How much of the image content contains personal data
- Whether labels can be verified strongly enough for anything beyond eval

What happens next:
- If we do anything now, it should be a tiny local `eval_only` pilot with strict metadata, deletion support, and negative cases.
- We should not jump straight to a training dataset.

# Combined One-File Summary

# Local Listing Image Dataset Review Summary

Date: 2026-03-28

Decision:
- accept_with_follow_up

Top reasons:
- The repo has a real gap in frozen real-image evaluation.
- The repo does not have a good enough rights/privacy foundation for a broad Tradera/Blocket image corpus.
- Trust improves only if the pilot is small, case-first, eval-only, and negative-heavy.

Developer summary:
- Recommend a 24-case local `eval_only` pilot organized per listing/case.
- Keep raw images outside git.
- Use explicit metadata, case-level split control, and gold/silver/bronze labels.
- Never use filenames, model outputs, or old valuations as ground truth.

QA summary:
- Current mocked golden tests pass, but real-image coverage is missing.
- A tiny pilot would improve regression testing.
- A larger marketplace-derived dataset would create labeling and leakage risk.
- Verdict: pass

Trust summary:
- Proceed only if all pilot cases are `eval_only` and `frozen_eval`.
- Do not let this pilot become training data by drift.
- Rights status must default to non-training.
- Removal support and duplicate control are mandatory.

Manager summary:
- Accept the need for a frozen real-image pilot.
- Narrow scope hard.
- Next step is spec plus local validation scaffold, not collection at scale and not training.

Product summary:
- A tiny pilot can help the team catch mistakes earlier without making the product more reckless.
- A big dataset too early would risk false certainty, privacy issues, and weak labels.

Promotion status:
- shadow_only

Rollback readiness:
- ready

Rekommenderat nu:
- Bygg en liten lokal `eval_only`-pilot med cirka 24 case, case-first metadata, `split: frozen_eval`, negativa fall från start och råbilder utanför repo eller git-ignorerat.

Rekommenderat senare:
- Överväg separat `training_candidate`-intag först efter att pilotens metadata, rights review, removal workflow och leakage-kontroller fungerar i praktiken.

Gör inte detta:
- Bygg inte ett brett Tradera/Blocket-bilddataset nu.
- Lägg inte råbilder i git.
- Använd inte filnamn, modellens egna outputs eller gamla valuations som ground truth.
