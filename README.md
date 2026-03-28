# valuation-mvp

`valuation-mvp` is a local MVP for estimating the second-hand value of consumer tech products from photos.

The app is built around one main use case:
- help identify a tech product from one or more photos
- estimate its used-market value when the evidence is strong enough
- ask for better photos when identification is too uncertain
- refuse to show a price when market evidence is too weak

What this MVP is not:
- not a broad product-price scanner
- not a new-product price checker
- not a guarantee of resale value

New-price data can still appear in the app, but only as supporting context. The main goal is to estimate second-hand value from product identification plus used-market evidence.

## Current response states

- `ok`: the app found enough evidence to show an estimated used-value range
- `ambiguous_model`: the app needs clearer or more complete photos before it can trust the exact model identification
- `insufficient_evidence`: the product may be identified correctly, but there is not enough strong second-hand market evidence to support a trustworthy valuation
- `degraded`: a temporary system issue prevented a reliable valuation result
- `error`: the request failed

## Run locally

```bash
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

Open:

- API / app: `http://127.0.0.1:8000/`

## Stage-ready check

Before pushing or merging `develop` into `staging`, run:

```bash
make stage-ready
```

That focused gate keeps the admin contracts, golden valuation cases, and deploy-critical config behavior in view. The living staging checklist is in `docs/STAGE_READY.md`.
It skips tests marked `integration`, which are covered by actual staging smoke tests instead.

## MVP principles

- prefer honesty over always showing a number
- explain when more photos are needed
- explain when market evidence is too weak
- treat new price as secondary context, not the main promise

## Manual QA

Browser test steps:
- `ok`: upload clear photos of a common tech product with a known second-hand market, then confirm the app shows a used-value range, confidence label, evidence summary, and sources.
- `ambiguous_model`: upload one blurry, partial, or front-only product photo, then confirm the app asks for better photos and shows requested additional angles instead of a price.
- `insufficient_evidence`: test a niche or uncommon product that can still be identified, then confirm the app explains that market evidence is too weak and does not show a valuation.
- `degraded`: temporarily break one upstream integration or simulate a backend failure, then confirm the app shows a temporary system issue instead of a product result.
- `error`: submit an empty or malformed request, then confirm the app shows a request failure state instead of pretending a valuation exists.

Real-product checklist:
- Identification accuracy: does the detected brand/model match the real product, or does the app clearly ask for more photos?
- Valuation status correctness: does the app choose `ok`, `ambiguous_model`, `insufficient_evidence`, `degraded`, or `error` honestly?
- Evidence clarity: is it clear why a value was shown or withheld?
- UI trustworthiness: does the result feel cautious, understandable, and not overly confident?
