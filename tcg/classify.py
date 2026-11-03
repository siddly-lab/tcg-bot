"""Sort TCGplayer products into the buckets the pack math uses.

Rules come from how TCGplayer names Riftbound products, checked against the live feed:
  - Sealed products have no Rarity field ("Origins - Booster Display").
  - Showcase cards say what they are in the name: "(Alternate Art)", "(Overnumbered)",
    "(Heartsteel Overnumbered)", "(Signature)", "(Ultimate)". Signatures carry a "*" number.
  - Runes are numbered R01..R06; alternate-art runes R02a; promo runes R02b.
  - Tokens are numbered T01 and often have " // " in the name.
"""
from __future__ import annotations

import re

BASE_RARITIES = ("Common", "Uncommon", "Rare", "Epic")
PACK_BUCKETS = ("Common", "Uncommon", "Rare", "Epic", "Rune", "RuneAlt", "Token",
                "AltArt", "Overnumbered", "Signature", "Ultimate")
LABELS = {
    "Common": "Commons", "Uncommon": "Uncommons", "Rare": "Rares", "Epic": "Epics",
    "Rune": "Runes", "RuneAlt": "Alternate-art runes", "Token": "Tokens",
    "AltArt": "Alternate arts", "Overnumbered": "Overnumbered", "Signature": "Signatures",
    "Ultimate": "Ultimate", "Special": "Special art (not in normal packs)",
}


def ext(p: dict, key: str):
    for e in p.get("extendedData") or []:
        if e.get("name") == key:
            return e.get("value")
    return None


def sealed_type(name: str) -> str:
    n = name.lower()
    if "booster display case" in n or n.endswith("display case"):
        return "case"
    if "booster display" in n or "booster box" in n:
        return "box"
    if "sleeved booster pack" in n and "bundle" not in n:
        return "sleeved_pack"
    if n.endswith("booster pack"):
        return "pack"
    return "other"


SEALED_LABELS = {"box": "Booster box", "case": "Booster box case (6 boxes)", "pack": "Booster pack",
                 "sleeved_pack": "Sleeved booster pack", "other": "Other sealed"}


def classify_card(p: dict) -> str | None:
    """Return the bucket for a single card, or None if it never comes out of a normal booster."""
    name = p.get("name") or ""
    low = name.lower()
    rarity = ext(p, "Rarity")
    number = (ext(p, "Number") or "").strip()
    if "oversized" in low or "serial numbered" in low:
        return None
    if re.match(r"^R\d+b$", number):          # promo runes
        return None
    if re.match(r"^R\d+a?$", number) or (re.search(r"\brune\b", low) and number.upper().startswith("R")):
        return "RuneAlt" if number.endswith("a") or rarity == "Showcase" else "Rune"
    if number.upper().startswith("T") or " // " in name:
        return "Token"
    if rarity in (None, "None", "Promo"):
        return None
    if "special art" in low or re.match(r"^SP\d", number):
        return "Special"
    if "signature" in low or number.endswith("*") or re.match(r"^\d+\*", number):
        return "Signature"
    if "(ultimate" in low or rarity == "Ultimate":
        return "Ultimate"
    if "overnumbered" in low:
        return "Overnumbered"
    if "alternate art" in low or rarity == "Showcase":
        return "AltArt"
    if rarity in BASE_RARITIES:
        return rarity
    return None


def clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip()
