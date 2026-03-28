"""
VALOR Prisassistent — conversation flow + envelope enrichment.

Pure rule-based logic. No ML, no LLM, no DB access, no pgvector.
Extracted from api/value.py so tests can import without heavy dependencies.

Contains:
- Conversation flow: build_assistant_context()
- Envelope enrichment: enrich_envelope(), build_user_fields()
- Constants: STATUS_TITLES, STATUS_MESSAGES, REASON_DETAILS
"""

from __future__ import annotations

from typing import Any

from backend.app.schemas.assistant import AssistantContext, QuickReply

# ─── Confirmation normalization ───

_YES_SYNONYMS = frozenset({"yes", "ja", "japp", "jep", "stämmer", "korrekt", "rätt", "correct"})
_NO_SYNONYMS = frozenset({"no", "nej", "nope", "fel", "wrong", "incorrect"})


def normalize_confirmation(raw: str | None) -> str | None:
    """Normalize free-text confirmation to 'yes' | 'no' | None."""
    if raw is None:
        return None
    cleaned = raw.strip().lower()
    if cleaned in _YES_SYNONYMS or cleaned == "yes":
        return "yes"
    if cleaned in _NO_SYNONYMS or cleaned == "no":
        return "no"
    return None  # Unrecognized — ignore


# ─── Quick reply constants ───

CONDITION_QUICK_REPLIES = [
    QuickReply(label="Som ny", action="set_condition", payload={"condition": "excellent"}),
    QuickReply(label="Bra skick", action="set_condition", payload={"condition": "good"}),
    QuickReply(label="Okej skick", action="set_condition", payload={"condition": "fair"}),
    QuickReply(label="Tydligt slitage", action="set_condition", payload={"condition": "poor"}),
    QuickReply(label="Defekt", action="set_condition", payload={"condition": "poor"}),
]

BUNDLE_QUICK_REPLIES = [
    QuickReply(label="Bara enheten", action="set_bundle", payload={"bundle": "unit_only"}),
    QuickReply(label="Med fodral/väska", action="set_bundle", payload={"bundle": "with_case"}),
    QuickReply(label="Med extra tillbehör", action="set_bundle", payload={"bundle": "combo_kit"}),
    QuickReply(label="Komplett kit (allt medföljer)", action="set_bundle", payload={"bundle": "full_kit"}),
]

SHIPPING_QUICK_REPLIES = [
    QuickReply(label="Kan skickas", action="set_shipping", payload={"shipping": "can_ship"}),
    QuickReply(label="Endast lokal affär", action="set_shipping", payload={"shipping": "local_only"}),
    QuickReply(label="Båda funkar", action="set_shipping", payload={"shipping": "either"}),
]

GOAL_QUICK_REPLIES = [
    QuickReply(label="Sälja snabbt", action="set_goal", payload={"goal": "sell_fast"}),
    QuickReply(label="Få högsta pris", action="set_goal", payload={"goal": "max_price"}),
    QuickReply(label="Lagom balans", action="set_goal", payload={"goal": "balanced"}),
]

# Categories where bundle/accessory selection matters for valuation accuracy.
# Start narrow: only camera products where combo kits are common.
# ─── Strategy text per goal ───

GOAL_STRATEGIES: dict[str, str] = {
    "sell_fast": (
        "Prissätt nära den nedre delen av spannet. "
        "Säljer oftast inom ett par dagar om priset ligger under genomsnittet."
    ),
    "max_price": (
        "Börja nära den övre delen av spannet och var beredd att vänta. "
        "Bra bilder och tydlig beskrivning ökar chansen."
    ),
    "balanced": (
        "Lägg dig nära mitten av spannet — ett bra utgångspris som ger "
        "rimlig säljtid utan att lämna pengar på bordet."
    ),
}

BUNDLE_ELIGIBLE_CATEGORIES = frozenset({"camera"})

# Brands where bundle kits are especially common and affect pricing significantly.
BUNDLE_ELIGIBLE_BRANDS = frozenset({"dji", "gopro"})

# Minimum query length for product matching (Bug 3: garbage input guard)
MIN_QUERY_LENGTH = 4

# Confidence threshold for skipping confirmation (Bug 2: high-confidence skip)
HIGH_CONFIDENCE_SKIP_THRESHOLD = 0.9

# Varied fallback messages to avoid repetition (Bug 4)
_FALLBACK_MESSAGES = [
    "Jag kan hjälpa dig värdera en produkt.",
    "Ladda upp en bild så hjälper jag dig att ta reda på vad den är värd.",
    "Vill du veta vad din pryl är värd? Fota den så kör vi.",
]


# ─── Helpers ───

def is_valid_product_query(query: str | None) -> bool:
    """Check if a string is long enough to be a plausible product name.

    Rejects garbage like 'tes', 'ab', single chars.
    """
    if not query:
        return False
    cleaned = query.strip()
    return len(cleaned) >= MIN_QUERY_LENGTH


def get_product_display_name(data: dict[str, Any] | None) -> str:
    """Extract a human-readable product name from ValueData fields."""
    if not data:
        return "produkten"
    parts = [p for p in [data.get("brand"), data.get("line"), data.get("model")] if p]
    return " ".join(parts) if parts else "produkten"


def is_bundle_eligible(data: dict[str, Any] | None) -> bool:
    """Check if the product should get a bundle question.

    Only fires for categories/brands where bundles materially affect price.
    """
    if not data:
        return False
    category = (data.get("category") or "").lower().strip()
    brand = (data.get("brand") or "").lower().strip()
    return category in BUNDLE_ELIGIBLE_CATEGORIES or brand in BUNDLE_ELIGIBLE_BRANDS


# ─── Main flow logic ───

def build_assistant_context(
    status: str,
    data: dict[str, Any] | None,
    confirmation: str | None,
    has_images: bool,
    condition: str | None = None,
    bundle: str | None = None,
    shipping: str | None = None,
    goal: str | None = None,
    fallback_count: int = 0,
) -> AssistantContext | None:
    """Build conversation-phase context from response status + user input.

    Pure rule-based logic — no ML, no LLM, no DB.
    Returns None for degraded/error statuses (no guidance possible).

    Flow: confirm → condition → bundle (if eligible) → shipping → goal → ready

    Bug fixes applied:
    - Bug 1: confirmation="yes" requires data to have brand/model, otherwise re-ask
    - Bug 2: high confidence (>0.9) skips confirmation and goes straight to condition
    - Bug 4: fallback_count varies the unsupported message
    - Bug 5: condition only asked AFTER confirmation, never during
    """
    # ── No guidance for error states ──
    if status in {"degraded", "error"}:
        return None

    product_name = get_product_display_name(data)

    # ── Bug 1 fix: if user confirmed but data was completely lost, re-ask ──
    if confirmation == "yes" and data is None:
        return AssistantContext(
            phase="confirming",
            prompt="Något gick fel — vi tappade produkten. Kan du bekräfta igen?",
            quick_replies=[
                QuickReply(label="Ja, det stämmer", action="confirm_yes", payload={"confirmation": "yes"}),
                QuickReply(label="Nej, fel modell", action="confirm_no", payload={"confirmation": "no"}),
            ],
        )

    # ── User confirmed: condition → bundle (if eligible) → shipping → goal → ready ──
    if confirmation == "yes":
        # Bug 5 fix: condition is only asked here (after confirmation), never elsewhere
        if not condition:
            return AssistantContext(
                phase="awaiting_condition",
                prompt=f"Hur skulle du beskriva skicket på {product_name}?",
                quick_replies=list(CONDITION_QUICK_REPLIES),
            )
        if not bundle and is_bundle_eligible(data):
            return AssistantContext(
                phase="awaiting_bundle",
                prompt=f"Vad ingår i din försäljning av {product_name}?",
                quick_replies=list(BUNDLE_QUICK_REPLIES),
            )
        if not shipping:
            return AssistantContext(
                phase="awaiting_shipping",
                prompt="Hur vill du sälja?",
                quick_replies=list(SHIPPING_QUICK_REPLIES),
            )
        if not goal:
            return AssistantContext(
                phase="awaiting_goal",
                prompt="Vad är viktigast för dig?",
                quick_replies=list(GOAL_QUICK_REPLIES),
            )
        strategy = GOAL_STRATEGIES.get(goal)
        return AssistantContext(
            phase="ready",
            prompt="Här är din värdering.",
            quick_replies=[
                QuickReply(label="Ny värdering", action="start_over"),
                QuickReply(label="Det var fel produkt", action="confirm_no", payload={"confirmation": "no"}),
            ],
            strategy_summary=strategy,
        )

    # ── User rejected: guide to correction ──
    if confirmation == "no":
        return AssistantContext(
            phase="correcting",
            prompt="Okej! Skriv in rätt modell eller ta en ny bild.",
            quick_replies=[
                QuickReply(label="Skriv modell manuellt", action="manual_input"),
                QuickReply(label="Ta ny bild", action="add_images"),
                QuickReply(label="Börja om", action="start_over"),
            ],
        )

    # ── No images and no confirmation — out of scope (Bug 4: vary text) ──
    if not has_images and confirmation is None:
        msg_idx = min(fallback_count, len(_FALLBACK_MESSAGES) - 1)
        return AssistantContext(
            phase="unsupported",
            prompt=_FALLBACK_MESSAGES[msg_idx],
            quick_replies=[
                QuickReply(label="Fotografera en produkt", action="start_over"),
            ],
            guardrail_message="Ladda upp en bild på produkten du vill värdera så hjälper jag dig.",
        )

    # ── Valuation succeeded — ask for confirmation ──
    if status in {"ok", "depreciation_estimate"}:
        # Bug 2 fix: skip confirmation for high-confidence results
        confidence = float((data or {}).get("confidence") or 0)
        if confidence >= HIGH_CONFIDENCE_SKIP_THRESHOLD:
            # High confidence — skip straight to condition question
            if not condition:
                return AssistantContext(
                    phase="awaiting_condition",
                    prompt=f"Vi är {int(confidence * 100)}% säkra att det är {product_name}. Hur ser skicket ut?",
                    quick_replies=list(CONDITION_QUICK_REPLIES),
                )
            # If condition already set, treat as confirmed and continue flow
            return build_assistant_context(
                status=status, data=data, confirmation="yes",
                has_images=has_images, condition=condition,
                bundle=bundle, shipping=shipping, goal=goal,
            )

        return AssistantContext(
            phase="confirming",
            prompt=f"Vi identifierade {product_name}. Stämmer det?",
            quick_replies=[
                QuickReply(label="Ja, det stämmer", action="confirm_yes", payload={"confirmation": "yes"}),
                QuickReply(label="Nej, fel modell", action="confirm_no", payload={"confirmation": "no"}),
            ],
        )

    # ── Ambiguous model — guide toward more info ──
    if status == "ambiguous_model":
        angles = (data or {}).get("requested_additional_angles") or []
        angle_hint = f" Försök visa {', '.join(angles[:3])}." if angles else ""
        return AssistantContext(
            phase="correcting",
            prompt=f"Vi är osäkra på exakt modell.{angle_hint}",
            quick_replies=[
                QuickReply(label="Ta ny bild", action="add_images"),
                QuickReply(label="Skriv modell manuellt", action="manual_input"),
                QuickReply(label="Börja om", action="start_over"),
            ],
        )

    # ── Insufficient evidence — gentle guidance ──
    if status == "insufficient_evidence":
        return AssistantContext(
            phase="correcting",
            prompt=f"Vi kunde identifiera {product_name}, men hittade inte tillräckligt med marknadsdata.",
            quick_replies=[
                QuickReply(label="Prova igen", action="start_over"),
                QuickReply(label="Skriv modell manuellt", action="manual_input"),
            ],
        )

    return None  # No assistant context for unrecognized statuses


# ═══════════════════════════════════════════════════════════════════════
# Envelope enrichment — pure string/dict logic, no DB
# ═══════════════════════════════════════════════════════════════════════

STATUS_TITLES = {
    "ok": "Begagnatvärde uppskattat",
    "ambiguous_model": "Fler bilder behövs",
    "insufficient_evidence": "För svagt marknadsunderlag",
    "degraded": "Tillfälligt systemproblem",
    "error": "Kunde inte värdera enheten",
}

STATUS_MESSAGES = {
    "ok": "Det här är en uppskattning av andrahandsvärdet, baserad på jämförbara annonser och tydligt underlag.",
    "ambiguous_model": "Vi behöver säkrare produktidentifiering innan vi visar ett begagnatvärde.",
    "insufficient_evidence": "Produkten kan vara rätt identifierad, men underlaget från andrahandsmarknaden räcker inte för en trovärdig värdering.",
    "degraded": "Det här är ett tillfälligt systemproblem, inte ett tillförlitligt värderingsresultat.",
    "error": "Begäran kunde inte slutföras.",
}

REASON_DETAILS = {
    "missing_brand_or_model": "Exakt varumärke eller modell kunde inte bekräftas.",
    "needs_more_images": "Bilderna visar inte tillräckligt många detaljer för säker identifiering.",
    "exact_model_confidence_too_low": "Vi är ännu inte tillräckligt säkra på den exakta modellen.",
    "multiple_plausible_models": "Det finns fortfarande flera rimliga modellkandidater.",
    "no_relevant_comparables": "Inga relevanta andrahandsannonser klarade relevansfiltren.",
    "not_enough_relevant_comparables": "För få relevanta andrahandsannonser överlevde filtreringen.",
    "average_relevance_too_low": "Jämförelseannonserna matchade produkten för svagt.",
    "no_sold_comparables": "Det saknas tillräckligt starka sålda annonser för att förankra ett begagnatvärde.",
    "cannot_value_from_new_price_only": "Nypris kan bara användas som stödkontext, inte som ensam grund för begagnatvärde.",
    "valuation_pipeline_failure": "Värderingsflödet misslyckades oväntat.",
    "unexpected_pricing_status": "Värderingslagret returnerade ett oväntat tillstånd.",
    "value_endpoint_failure": "API:t misslyckades innan ett tillförlitligt värderingssvar kunde skickas.",
}


def _build_ok_user_fields(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    data = payload.get("data") or {}
    valuation = data.get("valuation") or {}
    evidence_summary = valuation.get("evidence_summary")
    explanation = (
        str(evidence_summary)
        if evidence_summary
        else "Vi kunde identifiera produkten och hitta tillräckligt starka jämförelser från andrahandsmarknaden."
    )
    return (
        "Begagnatvärdet är klart",
        explanation,
        "Jämför gärna med skick, lagring och tillbehör innan du sätter ett slutpris.",
    )


def _build_ambiguous_user_fields(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    data = payload.get("data") or {}
    new_price = (data.get("market_data") or {}).get("new_price") or {}
    has_new_price = bool(new_price.get("estimated_new_price")) or bool(new_price.get("sources"))
    requested_angles = list(data.get("requested_additional_angles") or [])
    angle_text = (
        f"Ta gärna bilder på {', '.join(requested_angles[:4])}."
        if requested_angles
        else "Ta gärna fler bilder med modelltext, portar eller baksida."
    )
    explanation = "Vi behöver säkrare produktidentifiering innan vi visar ett begagnatvärde."
    if has_new_price:
        explanation += " Vi kunde däremot hämta nypriskontext som stöd medan vi väntar med själva begagnatvärdet."
    return (
        "Vi behöver säkrare modellträff",
        explanation,
        angle_text,
    )


def _build_insufficient_user_fields(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    snapshot = payload.get("market_snapshot") or {}
    data = payload.get("data") or {}
    preliminary_estimate = data.get("preliminary_estimate") or {}
    fetched = int(snapshot.get("fetched_count") or 0)
    relevant = int(snapshot.get("relevant_count") or 0)
    sold = int(snapshot.get("sold_count") or 0)

    if preliminary_estimate:
        signal_count = int(preliminary_estimate.get("supporting_signal_count") or 0)
        explanation = (
            f"Vi kan visa en grov uppskattning eftersom produkten ser rätt ut, nypriskontext finns och {signal_count} marknadssignal"
            f"{'' if signal_count == 1 else 'er'} pekar åt samma håll. Underlaget räcker däremot inte för ett vanligt begagnatvärde."
        )
        return (
            "Grov uppskattning finns, men inte full värdering",
            explanation,
            "Använd uppskattningen som orientering och kontrollera gärna fler sålda annonser innan du sätter pris.",
        )

    if fetched and relevant == 0:
        explanation = f"Vi hittade {fetched} annonser, men ingen var tillräckligt nära rätt produkt för ett tryggt begagnatvärde."
    elif fetched and relevant:
        explanation = f"Vi hittade {fetched} annonser, men bara {relevant} var tillräckligt relevanta och {sold} såg ut som sålda träffar."
    else:
        explanation = "Produkten kan vara rätt identifierad, men underlaget från andrahandsmarknaden är för svagt för en trygg värdering."
    return (
        "Underlaget räcker inte för begagnatvärde",
        explanation,
        "Prova gärna tydligare produktbilder eller försök igen senare när fler relevanta annonser finns.",
    )


def _build_degraded_user_fields(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    return (
        "Tillfälligt problem i tjänsten",
        "Det här är ett systemproblem i värderingsflödet, inte ett resultat för själva produkten.",
        "Försök igen om en liten stund med samma bilder.",
    )


def _build_error_user_fields(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    return (
        "Begäran kunde inte behandlas",
        "Vi kunde inte läsa eller behandla underlaget i det här försöket.",
        "Kontrollera bilderna och försök igen.",
    )


def build_user_fields(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    """Select user-facing title, explanation, and recommended action by status."""
    status = str(payload.get("status") or "error")
    if status == "ok":
        return _build_ok_user_fields(payload)
    if status == "ambiguous_model":
        return _build_ambiguous_user_fields(payload)
    if status == "insufficient_evidence":
        return _build_insufficient_user_fields(payload)
    if status == "degraded":
        return _build_degraded_user_fields(payload)
    return _build_error_user_fields(payload)


def enrich_envelope(
    payload: dict[str, Any],
    confirmation: str | None = None,
    has_images: bool = True,
    condition: str | None = None,
    bundle: str | None = None,
    shipping: str | None = None,
    goal: str | None = None,
) -> dict[str, Any]:
    """Enrich a raw valuation payload with user-facing text and assistant context.

    Pure logic — no DB, no network, no pgvector. Safe to call from tests.
    """
    status = str(payload.get("status") or "error")
    reasons = [str(reason) for reason in payload.get("reasons", []) if reason]
    payload["warnings"] = list(dict.fromkeys(str(warning) for warning in payload.get("warnings", []) if warning))
    payload["reasons"] = list(dict.fromkeys(reasons))
    payload["status_title"] = STATUS_TITLES.get(status, STATUS_TITLES["error"])
    payload["status_message"] = STATUS_MESSAGES.get(status, STATUS_MESSAGES["error"])
    user_status_title, user_explanation, recommended_action = build_user_fields(payload)
    payload["user_status_title"] = user_status_title
    payload["user_explanation"] = user_explanation
    payload["recommended_action"] = recommended_action
    payload["reason_details"] = [
        REASON_DETAILS.get(reason, reason.replace("_", " ").capitalize())
        for reason in payload["reasons"]
    ]
    # ── Assistant context (additive, never breaks existing behavior) ──
    assistant_ctx = build_assistant_context(
        status=status,
        data=payload.get("data"),
        confirmation=confirmation,
        has_images=has_images,
        condition=condition,
        bundle=bundle,
        shipping=shipping,
        goal=goal,
    )
    if assistant_ctx:
        payload["assistant_context"] = assistant_ctx.model_dump()
    return payload
