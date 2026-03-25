"""
Diagnose pipeline quality for a product without uploading an image.

Usage:
    python automation/diagnose.py "DJI Osmo Action 5 Pro" camera
    python automation/diagnose.py "Sony WH-1000XM5" headphones
    python automation/diagnose.py "iPhone 15 Pro" smartphone

Prints a table showing what each source returned, which comparables passed
scoring, and what the final valuation looks like.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.app.integrations.blocket_client import BlocketClient
from backend.app.integrations.tradera_client import TraderaClient
from backend.app.services.comparable_scoring import score_comparable_relevance
from backend.app.services.market_data_service import MarketDataService, build_search_query, strip_color_words
from backend.app.services.market_service import MarketService
from backend.app.services.new_price_service import NewPriceService
from backend.app.services.pricing_service import MIN_RELEVANCE_SCORE, PricingService
from backend.app.schemas.product_identification import ProductIdentificationResult

SEP = "─" * 70


def _fmt_price(price, currency="SEK"):
    if price is None:
        return "—"
    return f"{price:,.0f} {currency}".replace(",", " ")


def _score_label(score: float, hard_reject: bool) -> str:
    if hard_reject:
        return "REJECT"
    if score >= 0.75:
        return f"✓ {score:.2f}"
    if score >= MIN_RELEVANCE_SCORE:
        return f"~ {score:.2f}"
    return f"✗ {score:.2f}"


def run(brand: str, model: str, category: str | None = None):
    print(f"\n{SEP}")
    print(f"  DIAGNOSE: {brand} {model}  [{category or 'no category'}]")
    print(SEP)

    # ── New price ─────────────────────────────────────────────────────────────
    print("\n[1] NEW PRICE")
    svc = NewPriceService()
    np = svc.get_new_price(brand, model, category)
    print(f"    Primary  ({np.get('source', '?')}): {_fmt_price(np.get('estimated_new_price'), np.get('currency', 'SEK'))}")
    cse = np.get("cse_comparison")
    if cse:
        print(f"    CSE      ({cse.get('source', '?')}): {_fmt_price(cse.get('estimated_new_price'), cse.get('currency', 'SEK'))}")
    else:
        print("    CSE: not configured / no result")

    # ── Raw market fetch ───────────────────────────────────────────────────────
    print("\n[2] RAW MARKET FETCH")
    mds = MarketDataService()
    clean_model = strip_color_words(model)
    exact_query = build_search_query(brand, clean_model)

    blocket_raw = BlocketClient().search(exact_query)
    print(f"    Blocket  ({exact_query!r}): {len(blocket_raw)} listings")

    tradera_client = TraderaClient()
    if tradera_client.is_configured:
        tradera_raw = tradera_client.search(exact_query)
        print(f"    Tradera  ({exact_query!r}): {len(tradera_raw)} listings")
    else:
        print("    Tradera: not configured")

    # ── All comparables after merge/dedupe (as dicts, via MarketService) ─────
    all_comparables = MarketService().get_comparables(brand, model, category=category)
    print(f"\n[3] MERGED COMPARABLES: {len(all_comparables)} total")

    # ── Scoring ───────────────────────────────────────────────────────────────
    print("\n[4] SCORING  (✓=pass  ~=marginal  ✗=below threshold  REJECT=hard reject)")
    fake_identification = ProductIdentificationResult(
        brand=brand,
        model=model,
        category=category,
        confidence=0.9,
        line=None,
        variant=None,
        candidate_models=[],
        needs_more_images=False,
        requested_additional_angles=[],
        reasoning_summary="",
        source="manual",
        request_id="diagnose",
    )
    passed = []
    for comp in all_comparables:
        score_result = score_comparable_relevance(comp, fake_identification)
        label = _score_label(score_result.score, score_result.hard_reject)
        status = "SOLD" if comp.get("listing_type") == "sold" else "active"
        price_str = _fmt_price(comp.get("price"), comp.get("currency", "SEK"))
        reasons = ", ".join(score_result.reasons[:3])
        title = (comp.get("title") or "")[:50]
        print(f"    {label:>8}  [{status:6}]  {price_str:>10}  {comp.get('source','?'):8}  {title}")
        if not score_result.hard_reject and score_result.score >= MIN_RELEVANCE_SCORE:
            passed.append(comp)

    print(f"\n    → {len(passed)} / {len(all_comparables)} pass scoring threshold ({MIN_RELEVANCE_SCORE})")

    # ── Pricing ───────────────────────────────────────────────────────────────
    print("\n[5] PRICING RESULT")
    ps = PricingService()
    pricing = ps.calculate_valuation(
        product_identification=fake_identification,
        used_market_comparables=all_comparables,
        new_price_estimate=np,
    )
    status = pricing.get("status", "?")
    print(f"    Status: {status}")
    if status == "ok":
        v = pricing.get("valuation", {})
        print(f"    Range:  {_fmt_price(v.get('low_estimate'))} – {_fmt_price(v.get('high_estimate'))}")
        print(f"    Fair:   {_fmt_price(v.get('fair_estimate'))}")
        print(f"    Conf:   {v.get('confidence', 0):.0%}")
    else:
        reasons = pricing.get("reasons", [])
        print(f"    Reasons: {', '.join(reasons)}")

    print(f"\n{SEP}\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 1:
        print("Usage: python automation/diagnose.py <brand> <model> [category]")
        print('  e.g: python automation/diagnose.py DJI "Osmo Action 5 Pro" camera')
        sys.exit(1)

    if len(args) == 1:
        # Try to split "brand model" from a single argument
        parts = args[0].split(None, 1)
        brand_arg = parts[0]
        model_arg = parts[1] if len(parts) > 1 else parts[0]
        category_arg = None
    elif len(args) == 2:
        brand_arg, model_arg = args[0], args[1]
        category_arg = None
    else:
        brand_arg, model_arg, category_arg = args[0], args[1], args[2]

    run(brand_arg, model_arg, category_arg)
