from dataclasses import dataclass, field
import re


POISON_PATTERNS = {
    "for parts": "listing_for_parts",
    "parts only": "listing_for_parts",
    "broken": "listing_broken",
    "defect": "listing_defect",
    "defective": "listing_defect",
    "icloud locked": "listing_locked",
    "activation locked": "listing_locked",
    "locked": "listing_locked",
    "empty box": "listing_empty_box",
    "box only": "listing_empty_box",
    "case only": "listing_case_only",
    "charger only": "listing_charger_only",
    "replacement part": "listing_replacement_parts",
    "replacement parts": "listing_replacement_parts",
    "spare part": "listing_replacement_parts",
    "spare parts": "listing_replacement_parts",
    "body only": "listing_body_only",
    # Swedish
    "reservdelar": "listing_replacement_parts",
    "reservdel": "listing_replacement_parts",
    "trasig": "listing_broken",
    "säljes trasig": "listing_broken",
    "icloud lås": "listing_locked",
    "aktiveringslas": "listing_locked",
    "tom förpackning": "listing_empty_box",
    "tom ask": "listing_empty_box",
}

ACCESSORY_MISMATCH_PATTERNS = {
    "case only",
    "charger only",
    "strap only",
    "ear pads only",
    # Swedish accessory-only listings
    "laddare only",
    "endast laddare",
    "endast fodral",
    "endast rem",
}

BUNDLE_MISMATCH_PATTERNS = {
    "with lens",
    "kit lens",
}

OSMO_FAMILY_TOKENS = {"action", "pocket", "mobile"}
OSMO_BUNDLE_TOKENS = {"adventure", "bundle", "combo", "creator", "kit"}
OSMO_VERSION_QUALIFIERS = {"mini", "plus", "pro", "ultra"}
CAMERA_EXTRA_BUNDLE_TOKENS = {
    "sandisk",
    "battery",
    "batteri",
    "batterier",
    "mic",
    "mikrofon",
    "microphone",
    "selfie",
    "tripod",
    "stativ",
    "microsd",
    "minneskort",
    # Swedish bundle/accessory signals
    "tillbehor",   # tillbehör — accessories included
    "laddare",     # charger included
    "fodral",      # case included
    "hållare",     # mount/holder included
    "hallare",     # normalized form
    "linsskydd",   # lens cover
    "vattentat",   # waterproof housing
}


@dataclass(frozen=True)
class ComparableScore:
    score: float
    reasons: list[str] = field(default_factory=list)
    hard_reject: bool = False


@dataclass(frozen=True)
class ComparableAdjustment:
    score_cap: float | None = None
    score_delta: float = 0.0
    reasons: list[str] = field(default_factory=list)
    hard_reject: bool = False


def normalize_listing_text(value: str | None) -> str:
    return " ".join((value or "").lower().replace("-", " ").split())


def tokenize_listing_text(value: str | None) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize_listing_text(value))


_STORAGE_SIZES = {32, 64, 128, 256, 512, 1024}


def _extract_osmo_signals(value: str | None) -> dict | None:
    tokens = tokenize_listing_text(value)
    token_set = set(tokens)
    if "osmo" not in token_set:
        return None

    # Only treat small numbers as generation/version — exclude storage sizes (256 gb etc.)
    numeric_versions = {
        token for token in token_set
        if token.isdigit() and int(token) not in _STORAGE_SIZES and int(token) <= 20
    }
    qualifier_versions = {token for token in token_set if token in OSMO_VERSION_QUALIFIERS}
    bundle_tokens = {token for token in token_set if token in OSMO_BUNDLE_TOKENS}
    family = next((token for token in OSMO_FAMILY_TOKENS if token in token_set), None)
    return {
        "family": family,
        "numeric_versions": numeric_versions,
        "qualifier_versions": qualifier_versions,
        "bundle_tokens": bundle_tokens,
    }


def _osmo_adjustment(title: str, *, line: str, model: str, variant: str) -> ComparableAdjustment:
    target_text = " ".join(part for part in [line, model, variant] if part)
    target = _extract_osmo_signals(target_text)
    listing = _extract_osmo_signals(title)

    if not target or not listing:
        return ComparableAdjustment()

    reasons: list[str] = []
    score_cap: float | None = None

    if target["family"] and listing["family"] and target["family"] != listing["family"]:
        return ComparableAdjustment(
            reasons=["osmo_family_mismatch"],
            hard_reject=True,
        )

    target_numeric_versions = target["numeric_versions"]
    listing_numeric_versions = listing["numeric_versions"]
    target_qualifier_versions = target["qualifier_versions"]
    listing_qualifier_versions = listing["qualifier_versions"]
    target_bundle_tokens = target["bundle_tokens"]
    listing_bundle_tokens = listing["bundle_tokens"]

    if target_numeric_versions and listing_numeric_versions and target_numeric_versions != listing_numeric_versions:
        return ComparableAdjustment(
            reasons=["osmo_generation_mismatch"],
            hard_reject=True,
        )

    if target_numeric_versions and not listing_numeric_versions:
        reasons.append("osmo_generation_missing_in_listing")
        score_cap = 0.58
    elif not target_numeric_versions and listing_numeric_versions:
        reasons.append("osmo_generation_specific_for_broad_target")
        score_cap = 0.52

    if target_qualifier_versions != listing_qualifier_versions:
        if target_qualifier_versions and listing_qualifier_versions:
            reasons.append("osmo_variant_qualifier_mismatch")
            score_cap = min(score_cap or 1.0, 0.58)
        elif not target_qualifier_versions and listing_qualifier_versions:
            reasons.append("osmo_variant_specific_for_plain_target")
            score_cap = min(score_cap or 1.0, 0.6)

    if listing_bundle_tokens and not target_bundle_tokens:
        reasons.append("bundle_variant_for_plain_target")
        score_cap = min(score_cap or 1.0, 0.68)

    return ComparableAdjustment(score_cap=score_cap, reasons=reasons)


def _contains_pattern(title: str, pattern: str) -> bool:
    return bool(re.search(r"\b" + re.escape(pattern) + r"\b", title))


def _poison_reasons(title: str) -> list[str]:
    reasons: list[str] = []

    for pattern, reason in POISON_PATTERNS.items():
        if _contains_pattern(title, pattern):
            reasons.append(reason)

    if "accessory" in title and "mismatch" in title:
        reasons.append("listing_accessory_mismatch")

    if "bundle" in title and "mismatch" in title:
        reasons.append("listing_bundle_mismatch")

    return reasons


def _is_bundle_mismatch(title: str, category: str) -> bool:
    normalized_category = normalize_listing_text(category)
    if "camera" not in normalized_category:
        return False

    return any(pattern in title for pattern in BUNDLE_MISMATCH_PATTERNS)


def _has_camera_bundle_extras(title: str, category: str) -> bool:
    normalized_category = normalize_listing_text(category)
    if "camera" not in normalized_category:
        return False

    title_tokens = set(tokenize_listing_text(title))
    return bool(title_tokens & CAMERA_EXTRA_BUNDLE_TOKENS)


def score_comparable_relevance(comparable: dict, identification) -> ComparableScore:
    title = normalize_listing_text(str(comparable.get("title", "")))
    brand = normalize_listing_text(getattr(identification, "brand", None))
    line = normalize_listing_text(getattr(identification, "line", None))
    model = normalize_listing_text(getattr(identification, "model", None))
    variant = normalize_listing_text(getattr(identification, "variant", None))
    category = normalize_listing_text(getattr(identification, "category", None))
    candidate_models = [
        normalize_listing_text(candidate)
        for candidate in getattr(identification, "candidate_models", [])
        if candidate
    ]

    reasons: list[str] = []
    hard_reject_reasons = _poison_reasons(title)
    if hard_reject_reasons:
        return ComparableScore(score=0.0, reasons=hard_reject_reasons, hard_reject=True)

    if any(pattern in title for pattern in ACCESSORY_MISMATCH_PATTERNS):
        return ComparableScore(score=0.0, reasons=["listing_accessory_mismatch"], hard_reject=True)

    if _is_bundle_mismatch(title, category):
        return ComparableScore(score=0.0, reasons=["listing_bundle_mismatch"], hard_reject=True)

    if model and model in candidate_models:
        candidate_models = [candidate for candidate in candidate_models if candidate != model]

    osmo_adjustment = _osmo_adjustment(
        title,
        line=line,
        model=model,
        variant=variant,
    )
    if osmo_adjustment.hard_reject:
        return ComparableScore(score=0.0, reasons=osmo_adjustment.reasons, hard_reject=True)

    model_tokens = tokenize_listing_text(model) if model else []
    title_token_set = set(tokenize_listing_text(title))

    if model and model in title:
        score = 0.72
        reasons.append("exact_model_match")
    elif model_tokens and len(model_tokens) >= 3 and all(t in title_token_set for t in model_tokens):
        # All model tokens present but in different order — treat as strong match
        score = 0.68
        reasons.append("exact_model_match")
    elif "osmo" in model_tokens:
        # Relaxed match: many sellers omit the "Osmo" prefix
        # e.g. "DJI action 5 pro kamera" should match target "Osmo Action 5 Pro"
        core_tokens = [t for t in model_tokens if t != "osmo"]
        if len(core_tokens) >= 3 and all(t in title_token_set for t in core_tokens):
            score = 0.65
            reasons.append("exact_model_match")
        else:
            score = 0.0
            if brand and brand in title:
                score += 0.12
                reasons.append("brand_match")
            if line and line in title:
                score += 0.14
                reasons.append("line_match")
            if variant and variant in title:
                score += 0.05
                reasons.append("variant_match")
            if model:
                reasons.append("missing_exact_model_match")
    else:
        score = 0.0
        if brand and brand in title:
            score += 0.12
            reasons.append("brand_match")

        if line and line in title:
            score += 0.14
            reasons.append("line_match")

        if variant and variant in title:
            score += 0.05
            reasons.append("variant_match")

        if model:
            reasons.append("missing_exact_model_match")

    matched_alternative = next((candidate for candidate in candidate_models if candidate and candidate in title), None)
    if matched_alternative:
        reasons.append("matched_alternative_candidate_model")
        return ComparableScore(score=0.0, reasons=reasons, hard_reject=True)

    reasons.extend(osmo_adjustment.reasons)

    if score >= 0.72:
        if brand and brand in title:
            score += 0.1
            reasons.append("brand_match")

        if line and line in title:
            score += 0.08
            reasons.append("line_match")

        if variant and variant in title:
            score += 0.06
            reasons.append("variant_match")

    if osmo_adjustment.score_delta:
        score += osmo_adjustment.score_delta
    if osmo_adjustment.score_cap is not None:
        score = min(score, osmo_adjustment.score_cap)

    if _has_camera_bundle_extras(title, category):
        reasons.append("bundle_variant_for_plain_target")
        score = min(score, 0.68)

    if comparable.get("listing_type") == "sold":
        reasons.append("sold_listing")
    else:
        reasons.append("active_listing")

    return ComparableScore(
        score=round(min(score, 1.0), 2),
        reasons=list(dict.fromkeys(reasons)),
        hard_reject=False,
    )


def listing_weight(comparable: dict) -> float:
    return 1.25 if comparable.get("listing_type") == "sold" else 0.85
