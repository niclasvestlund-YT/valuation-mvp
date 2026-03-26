def normalize_product_name(value: str | None) -> str | None:
    if not value:
        return None

    cleaned = " ".join(value.replace("_", " ").split())
    known_names = {
        "apple": "Apple",
        "asus": "ASUS",
        "bose": "Bose",
        "canon": "Canon",
        "dell": "Dell",
        "dji": "DJI",
        "generic": "Generic",
        "google": "Google",
        "gopro": "GoPro",
        "hp": "HP",
        "huawei": "Huawei",
        "jbl": "JBL",
        "lenovo": "Lenovo",
        "lg": "LG",
        "microsoft": "Microsoft",
        "nintendo": "Nintendo",
        "oneplus": "OnePlus",
        "rolex": "Rolex",
        "samsung": "Samsung",
        "sony": "Sony",
        "xiaomi": "Xiaomi",
        "iphone 13": "iPhone 13",
        "macbook air m2": "MacBook Air M2",
        "wh-1000xm4": "WH-1000XM4",
        "eos r6": "EOS R6",
        "datejust 41": "Datejust 41",
        "marketplace item": "Marketplace Item",
    }

    if cleaned.lower() in known_names:
        return known_names[cleaned.lower()]

    known_words = {
        "dji": "DJI", "hp": "HP", "lg": "LG", "jbl": "JBL", "asus": "ASUS",
        "gopro": "GoPro", "oneplus": "OnePlus", "iphone": "iPhone",
        "ipad": "iPad", "imac": "iMac", "macbook": "MacBook", "airpods": "AirPods",
    }

    parts = []

    for part in cleaned.split(" "):
        lower_part = part.lower()
        if lower_part in known_words:
            parts.append(known_words[lower_part])
            continue

        if any(char.isdigit() for char in part):
            parts.append(part.upper() if part.isalpha() else part)
            continue

        if part.islower() or part.isupper():
            parts.append(part.capitalize())
        else:
            parts.append(part)

    return " ".join(parts)


# Brand alias mapping for product key normalization
_BRAND_ALIASES = {
    "dji innovation": "dji",
    "apple inc": "apple",
    "apple inc.": "apple",
    "samsung electronics": "samsung",
    "sony corporation": "sony",
    "lg electronics": "lg",
}

import re as _re


def normalize_product_key(brand: str, model: str) -> str:
    """Normalize brand + model into a canonical key.

    "Sony", "WH-1000XM5" -> "sony_wh-1000xm5"
    "Apple", "iPhone 15 Pro" -> "apple_iphone-15-pro"
    "DJI Innovation", "Osmo Pocket 3" -> "dji_osmo-pocket-3"
    """
    b = (brand or "").strip().lower()
    b = _BRAND_ALIASES.get(b, b)
    # Keep only alphanumeric and hyphens
    b = _re.sub(r"[^a-z0-9]", "", b)

    m = (model or "").strip().lower()
    # Replace spaces and underscores with hyphens
    m = _re.sub(r"[\s_]+", "-", m)
    # Keep only alphanumeric, hyphens, and dots
    m = _re.sub(r"[^a-z0-9.\-]", "", m)
    # Collapse multiple hyphens
    m = _re.sub(r"-{2,}", "-", m)
    m = m.strip("-")

    if not b and not m:
        return "unknown"
    if not b:
        return m
    if not m:
        return b
    return f"{b}_{m}"
