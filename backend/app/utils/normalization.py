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
