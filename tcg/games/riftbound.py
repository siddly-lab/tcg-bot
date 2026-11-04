"""Riftbound: sort TCGplayer products into the buckets the pack math uses.

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
    "Ultimate": "Ultimate", "Special": "Special versions with unknown odds (left out)",
}


RUNE_NAME = re.compile(r"^(Fury|Calm|Mind|Body|Chaos|Order) Rune\b")


from . import ext, has_unknown_label  # noqa: E402

# Version labels whose odds we know. Anything else (for example "Heartsteel Overnumbered") is left out.
KNOWN_LABELS = {"alternate art", "overnumbered", "signature", "ultimate", "full art"}


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


SEALED_LABELS = {"box": "Booster box", "case": "Case (6 boxes)", "pack": "Booster pack",
                 "sleeved_pack": "Sleeved booster pack", "other": "Other sealed"}


def is_sealed(p: dict) -> bool:
    return ext(p, "Rarity") is None and ext(p, "Number") is None and not p.get("extendedData")


def card_name(name: str) -> str:
    return clean_name(name)


def sets_from_groups(groups: list[dict], products: dict[int, list[dict]], cfg: dict) -> list[dict]:
    """Riftbound sets are listed by hand in the config (there are few, and each needs its MSRP)."""
    out = []
    for g in groups:
        n = g["name"].strip().lower()
        for s in cfg["sets"]:
            if n in [m.lower() for m in s["match"]] or n == s["name"].lower():
                out.append({**s, "group_id": g["groupId"], "era": None, "modeled": True,
                            "release": s.get("release") or (g.get("publishedOn") or "")[:10]})
    return out


def unknown_sets(groups, products, cfg, known_ids):
    """Groups that sell a booster display but aren't in the config yet."""
    out = []
    for g in groups:
        if g["groupId"] in known_ids:
            continue
        if any(is_sealed(p) and sealed_type(p["name"]) == "box" for p in products.get(g["groupId"], [])):
            out.append({"name": g["name"], "published": g.get("publishedOn")})
    return out


BUCKET_PRINTING = {"AltArt": "Foil", "Overnumbered": "Foil", "Signature": "Foil", "Ultimate": "Foil"}


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
    if re.match(r"^R\d+a?$", number) or RUNE_NAME.match(name):
        alt = number.split("/")[0].endswith("a") or rarity == "Showcase" or "alternate art" in low
        return "RuneAlt" if alt else "Rune"
    if number.upper().startswith("T") or " // " in name:
        return "Token"
    if rarity in (None, "None", "Promo"):
        return None
    if "special art" in low or re.match(r"^SP\d", number):
        return "Special"
    if has_unknown_label(name, KNOWN_LABELS):
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
