import re
import logging
from ..models import MarketListing, VisionResult

logger = logging.getLogger(__name__)

# Title keywords that indicate accessories, parts, or broken items — not the product itself
# Variant suffixes that turn one model into a different (typically more expensive) product.
# "iPhone 13" → "iPhone 13 Pro" is a different item, not a match.
VARIANT_SUFFIXES = {"pro", "max", "mini", "plus", "ultra", "air", "lite", "fe", "s", "e"}

JUNK_KEYWORDS = {
    "öronkuddar", "ear pad", "earpads", "earpad",
    "öronkudde", "hörselkåpa", "hörselkåpor",
    "fodral", "case", "väska", "bag",
    "kabel", "cable", "laddkabel",
    "reservdel", "delar", "parts", "part", "del",
    "defekt", "trasig", "broken", "för delar",
    "ställning", "stand", "hållare",
    "skin", "sticker", "skins",
    "pcb", "board", "circuit",
    "silikon", "silicon", "headband sleeve", "pannbandshylsa",
    "sweat cover", "carrying case only",
}

# Minimum credible price for a used electronics product listing
# Anything below this is almost certainly an accessory or broken part
MIN_USED_PRICE_SEK = 300


def score_listings(
    listings: list[MarketListing],
    vision: VisionResult,
    new_price: float | None,
) -> list[MarketListing]:
    model = vision.model or ""
    brand = vision.brand or ""

    # Pre-filter: remove junk before scoring
    clean = []
    for listing in listings:
        reason = _junk_reason(listing.title, model, listing.price)
        if reason:
            logger.info(f"Rejected [{listing.price:.0f} kr] {listing.title!r} — {reason}")
        else:
            clean.append(listing)

    logger.info(
        f"Scoring: {len(listings)} raw → {len(clean)} after junk filter "
        f"({len(listings) - len(clean)} removed)"
    )
    if clean:
        logger.info("Kept listings:")
        for l in clean:
            logger.info(f"  [{l.price:.0f} kr]  {l.title}")

    for listing in clean:
        listing.relevance_score = _compute_score(listing, vision, new_price)

    result = [item for item in clean if item.relevance_score >= 0.25]
    logger.info(f"After relevance threshold: {len(result)} listings")
    return result


def _junk_reason(title: str, model: str, price: float) -> str | None:
    """Return a rejection reason string, or None if the listing looks legit."""
    t = title.lower()

    # Price floor — below this is almost certainly an accessory or broken item
    if price < MIN_USED_PRICE_SEK:
        return f"price {price:.0f} kr < minimum {MIN_USED_PRICE_SEK} kr"

    # Junk keyword in title
    for kw in JUNK_KEYWORDS:
        if kw in t:
            return f"junk keyword: {kw!r}"

    # Wrong model number from same family
    if model and _is_wrong_model(t, model):
        return f"wrong model (title has different version of {model})"

    return None


def _is_wrong_model(title_lower: str, model: str) -> bool:
    """
    Detect when the title contains a different model from the same brand line.
    E.g. model='WH-1000XM4':
      'WH-1000XM3' → True  (sibling version)
      'WH-CH720N'  → True  (different WH- product)
      'WH-1000XM4' → False (correct)
    """
    model_norm = model.upper()

    # Check 1: sibling version — same family prefix, different trailing number.
    # "WH-1000XM4" → family="WH-1000XM", version="4"
    m = re.search(r'^(.*?)(\d+)$', model)
    if m:
        family_prefix = m.group(1)   # "WH-1000XM"
        correct_version = m.group(2) # "4"
        if len(family_prefix) >= 3:
            pattern = re.escape(family_prefix) + r'(\d+)'
            for v in re.findall(pattern, title_lower, re.IGNORECASE):
                if v != correct_version:
                    return True

    # Check 2: same brand-line prefix (e.g. "WH-") but clearly different model code.
    # Catches "WH-CH720N" when model is "WH-1000XM4".
    brand_prefix_match = re.match(r'^([A-Za-z]{2,4}-)', model)
    if brand_prefix_match:
        brand_prefix = brand_prefix_match.group(1)  # "WH-"
        # Find all codes in title starting with same prefix
        found_codes = re.findall(
            re.escape(brand_prefix) + r'[A-Z0-9-]+',
            title_lower,
            re.IGNORECASE,
        )
        for code in found_codes:
            code_norm = code.upper()
            # Accept if code exactly matches or is a prefix of our model (or vice versa)
            if code_norm == model_norm:
                continue
            if model_norm.startswith(code_norm) or code_norm.startswith(model_norm):
                continue
            # Otherwise this is a different model — reject
            return True

    # Check 3: model is present but immediately followed by a variant suffix,
    # indicating a different product. E.g. model="iPhone 13", title has "iPhone 13 Pro".
    model_lower_str = model.lower()
    for match in re.finditer(re.escape(model_lower_str), title_lower):
        after = title_lower[match.end():].strip()
        first_token = after.split()[0].rstrip(".,") if after.split() else ""
        if first_token in VARIANT_SUFFIXES:
            return True

    return False


def _compute_score(listing: MarketListing, vision: VisionResult, new_price: float | None) -> float:
    title_match = _title_match(listing.title, vision)
    price_ok = _price_reasonableness(listing.price, new_price)
    recency = 0.7  # assume recent; Tradera/Blocket listings are current

    score = title_match * 0.5 + price_ok * 0.3 + recency * 0.2
    return round(min(score, 1.0), 4)


def _title_match(title: str, vision: VisionResult) -> float:
    words = vision.product_name.lower().split()
    title_lower = title.lower()
    if not words:
        return 0.0
    matched = sum(1 for w in words if w in title_lower)
    base = matched / len(words)

    # Strong bonus for exact model number in title — only when it's not a nearby variant.
    # Use word-boundary matching to avoid "iPhone 13" matching "iPhone 130".
    if (
        vision.model
        and re.search(r"\b" + re.escape(vision.model.lower()) + r"\b", title_lower)
        and not _is_wrong_model(title_lower, vision.model)
    ):
        base = min(base + 0.4, 1.0)
    elif vision.brand and vision.brand.lower() in title_lower:
        # Brand matches but no exact model — keep base, no bonus
        pass

    return round(base, 4)


def _price_reasonableness(price: float, new_price: float | None) -> float:
    # Hard floor: below MIN_USED_PRICE_SEK was already rejected in junk filter,
    # but guard here too in case scoring is called without pre-filtering
    if price < MIN_USED_PRICE_SEK:
        return 0.0

    if new_price is None or new_price <= 0:
        # No reference price — give neutral score; junk is already filtered
        return 0.5

    ratio = price / new_price
    # Used price should be 10–95% of new price
    if 0.10 <= ratio <= 0.95:
        return 1.0
    # Priced above new — suspicious (could be error or new-in-box premium)
    if ratio > 0.95:
        return 0.3
    return 0.0
